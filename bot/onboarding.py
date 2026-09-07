"""
Onboarding router for Aiogram 3.x.
Handles multi-step FSM onboarding:
1. Phone number collection & validation
2. Redundant API key selection (primary -> fallback)
3. Telegram OTP verification
4. Optional 2FA password verification
5. Database registration & Fernet encryption
6. Immediate startup of the user's personal userbot
"""

import asyncio
import re
from datetime import datetime, timedelta
from typing import Dict, List
from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from loguru import logger
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)

import config
import strings
from bot.keyboards import get_cancel_keyboard, get_phone_keyboard, get_remove_keyboard
from core.commands import register_saved_message_handlers
from core.key_manager import key_manager
from core.scheduler import scheduler_manager
from core.session_manager import encrypt_phone, get_user_session_path, session_manager
from db import crud
from db.database import get_db

router = Router(name="onboarding")


class OnboardingState(StatesGroup):
    waiting_for_phone = State()
    waiting_for_otp = State()
    waiting_for_2fa = State()


# Active temporary login clients awaiting OTP / 2FA completion
pending_login_clients: Dict[int, TelegramClient] = {}

# Rate limit tracking: telegram_id -> list of attempt timestamps
user_attempt_timestamps: Dict[int, List[datetime]] = {}


def is_rate_limited(telegram_id: int) -> bool:
    """Checks if a user exceeded onboarding rate limits (max 3/hour)."""
    now = datetime.utcnow()
    one_hour_ago = now - timedelta(hours=1)
    timestamps = user_attempt_timestamps.get(telegram_id, [])
    valid_timestamps = [t for t in timestamps if t > one_hour_ago]
    user_attempt_timestamps[telegram_id] = valid_timestamps
    return len(valid_timestamps) >= config.MAX_ONBOARDING_ATTEMPTS_PER_HOUR


def record_attempt(telegram_id: int):
    """Records an onboarding attempt timestamp."""
    now = datetime.utcnow()
    if telegram_id not in user_attempt_timestamps:
        user_attempt_timestamps[telegram_id] = []
    user_attempt_timestamps[telegram_id].append(now)


async def cleanup_pending_client(telegram_id: int):
    """Safely disconnects and removes any temporary Telethon client."""
    client = pending_login_clients.pop(telegram_id, None)
    if client and client.is_connected():
        try:
            await client.disconnect()
        except Exception:
            pass


@router.message(Command("cancel"))
@router.message(F.text == "❌ Bekor qilish")
async def cancel_onboarding(message: Message, state: FSMContext):
    """Cancels active onboarding flow."""
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
    await cleanup_pending_client(message.from_user.id)
    await message.answer(strings.CANCELLED, reply_markup=get_remove_keyboard())


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Entry point for /start command in the bot."""
    telegram_id = message.from_user.id

    # Check rate limit
    if is_rate_limited(telegram_id):
        await message.answer(strings.RATE_LIMITED)
        return

    # Check if user is already registered and has active session
    async with get_db() as session:
        user = await crud.get_user_by_telegram_id(session, telegram_id)
        if user and user.is_active and not user.is_banned:
            if session_manager.is_user_running(telegram_id):
                await message.answer(strings.ALREADY_REGISTERED, parse_mode="Markdown")
                return

    # Cleanup any stale state or client
    await state.clear()
    await cleanup_pending_client(telegram_id)

    await state.set_state(OnboardingState.waiting_for_phone)
    await message.answer(
        strings.WELCOME,
        reply_markup=get_phone_keyboard(),
        parse_mode="Markdown",
    )


@router.message(OnboardingState.waiting_for_phone, F.contact)
async def process_phone_contact(message: Message, state: FSMContext):
    """Handles phone number shared via Contact button."""
    phone = message.contact.phone_number
    await handle_phone_submission(phone, message, state)


@router.message(OnboardingState.waiting_for_phone, F.text)
async def process_phone_text(message: Message, state: FSMContext):
    """Handles phone number entered as manual text."""
    phone = message.text.strip()
    await handle_phone_submission(phone, message, state)


async def handle_phone_submission(raw_phone: str, message: Message, state: FSMContext):
    """Validates phone number and initiates Telethon code request."""
    telegram_id = message.from_user.id

    if is_rate_limited(telegram_id):
        await message.answer(strings.RATE_LIMITED)
        await state.clear()
        return

    # Format and clean phone number
    cleaned = re.sub(r"[^\d+]", "", raw_phone)
    if not cleaned.startswith("+"):
        cleaned = "+" + cleaned

    if not re.match(r"^\+[1-9]\d{7,14}$", cleaned):
        await message.answer(strings.INVALID_PHONE, parse_mode="Markdown")
        return

    record_attempt(telegram_id)
    progress_msg = await message.answer("⏳ **Telegram serverlariga ulanmoqda...**", parse_mode="Markdown")

    session_path = get_user_session_path(telegram_id)

    # Connect client using redundant key architecture
    client, key_index = await key_manager.try_connect(session_path)
    if not client:
        await progress_msg.edit_text(
            "⚠️ **Xatolik:** Telegram serverlariga ulanib bo'lmadi. Iltimos, birozdan so'ng qayta urinib ko'ring.",
            parse_mode="Markdown",
        )
        return

    try:
        sent_code = await client.send_code_request(cleaned)
        pending_login_clients[telegram_id] = client

        await state.update_data(
            phone=cleaned,
            phone_code_hash=sent_code.phone_code_hash,
            api_key_index=key_index,
            otp_attempts=0,
            two_fa_attempts=0,
        )
        await state.set_state(OnboardingState.waiting_for_otp)

        await progress_msg.delete()
        await message.answer(
            strings.ASK_OTP,
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )

    except FloodWaitError as e:
        await cleanup_pending_client(telegram_id)
        await state.clear()
        await progress_msg.edit_text(
            f"⛔ **Telegram cheklovi:** Juda ko'p urinish. Iltimos, {e.seconds} soniyadan so'ng qayta urinib ko'ring.",
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"[ONBOARDING] Failed to send code request for {cleaned}: {e}")
        await cleanup_pending_client(telegram_id)
        await state.clear()
        await progress_msg.edit_text(
            f"⚠️ **Xatolik yuz berdi:** {e}\nIltimos, qaytadan /start bosing.",
            parse_mode="Markdown",
        )


@router.message(OnboardingState.waiting_for_otp, F.text)
async def process_otp(message: Message, state: FSMContext):
    """Processes incoming OTP verification code."""
    telegram_id = message.from_user.id
    # Strip dots, spaces, dashes, commas, etc., to extract clean code
    raw_code = re.sub(r"[\s\.\-_,/:*~#]", "", message.text.strip())

    client = pending_login_clients.get(telegram_id)
    if not client or not client.is_connected():
        await message.answer("⚠️ Sessiya uzildi. Iltimos, qaytadan /start bosing.")
        await state.clear()
        return

    data = await state.get_data()
    phone = data.get("phone")
    phone_code_hash = data.get("phone_code_hash")
    attempts = data.get("otp_attempts", 0) + 1

    try:
        await client.sign_in(phone=phone, code=raw_code, phone_code_hash=phone_code_hash)
        # Authentication successful!
        await finalize_onboarding(message, state, client, phone, data.get("api_key_index", 0))

    except SessionPasswordNeededError:
        # User has 2FA enabled
        await state.update_data(otp_attempts=attempts)
        await state.set_state(OnboardingState.waiting_for_2fa)
        await message.answer(
            strings.ASK_2FA.format(attempts=3),
            reply_markup=get_cancel_keyboard(),
            parse_mode="Markdown",
        )

    except PhoneCodeInvalidError:
        if attempts >= 3:
            await cleanup_pending_client(telegram_id)
            await state.clear()
            await message.answer(
                "❌ **Kod 3 marta noto'g'ri kiritildi.** Jarayon bekor qilindi. Qayta boshlash: /start",
                reply_markup=get_remove_keyboard(),
                parse_mode="Markdown",
            )
        else:
            await state.update_data(otp_attempts=attempts)
            await message.answer(
                strings.INVALID_OTP.format(attempts=3 - attempts),
                reply_markup=get_cancel_keyboard(),
                parse_mode="Markdown",
            )

    except PhoneCodeExpiredError:
        await cleanup_pending_client(telegram_id)
        await state.clear()
        await message.answer(strings.EXPIRED_OTP, reply_markup=get_remove_keyboard(), parse_mode="Markdown")

    except FloodWaitError as e:
        await cleanup_pending_client(telegram_id)
        await state.clear()
        await message.answer(f"⛔ Telegram cheklovi: {e.seconds}s kuting.", reply_markup=get_remove_keyboard())

    except Exception as e:
        logger.error(f"[ONBOARDING] Sign-in error for user {telegram_id}: {e}")
        await cleanup_pending_client(telegram_id)
        await state.clear()
        await message.answer(f"⚠️ Xatolik yuz berdi: {e}\nQaytadan boshlash: /start", reply_markup=get_remove_keyboard())


@router.message(OnboardingState.waiting_for_2fa, F.text)
async def process_2fa(message: Message, state: FSMContext):
    """Processes 2FA password verification."""
    telegram_id = message.from_user.id
    password = message.text.strip()

    client = pending_login_clients.get(telegram_id)
    if not client or not client.is_connected():
        await message.answer("⚠️ Sessiya uzildi. Iltimos, qaytadan /start bosing.")
        await state.clear()
        return

    data = await state.get_data()
    phone = data.get("phone")
    attempts = data.get("two_fa_attempts", 0) + 1

    try:
        await client.sign_in(password=password)
        # 2FA successful!
        await finalize_onboarding(message, state, client, phone, data.get("api_key_index", 0))

    except PasswordHashInvalidError:
        if attempts >= 3:
            await cleanup_pending_client(telegram_id)
            await state.clear()
            await message.answer(
                "❌ **Parol 3 marta noto'g'ri kiritildi.** Jarayon bekor qilindi. Qayta boshlash: /start",
                reply_markup=get_remove_keyboard(),
                parse_mode="Markdown",
            )
        else:
            await state.update_data(two_fa_attempts=attempts)
            await message.answer(
                strings.INVALID_2FA.format(attempts=3 - attempts),
                reply_markup=get_cancel_keyboard(),
                parse_mode="Markdown",
            )

    except FloodWaitError as e:
        await cleanup_pending_client(telegram_id)
        await state.clear()
        await message.answer(f"⛔ Telegram cheklovi: {e.seconds}s kuting.", reply_markup=get_remove_keyboard())

    except Exception as e:
        logger.error(f"[ONBOARDING] 2FA error for user {telegram_id}: {e}")
        await cleanup_pending_client(telegram_id)
        await state.clear()
        await message.answer(f"⚠️ Xatolik yuz berdi: {e}\nQaytadan boshlash: /start", reply_markup=get_remove_keyboard())


async def finalize_onboarding(
    message: Message,
    state: FSMContext,
    client: TelegramClient,
    phone: str,
    api_key_index: int,
):
    """Completes registration, registers background listeners, and updates DB."""
    telegram_id = message.from_user.id
    username = message.from_user.username
    is_admin = telegram_id in config.ADMIN_IDS

    # Remove from pending dictionary
    pending_login_clients.pop(telegram_id, None)

    # Encrypt phone number
    encrypted_phone = encrypt_phone(phone)

    # Save user into DB
    async with get_db() as session:
        user = await crud.get_user_by_telegram_id(session, telegram_id)
        if not user:
            user = await crud.create_user(
                session=session,
                telegram_id=telegram_id,
                username=username,
                encrypted_phone=encrypted_phone,
                api_key_index=api_key_index,
                is_admin=is_admin,
            )
        else:
            user.phone = encrypted_phone
            user.api_key_index = api_key_index
            user.username = username
            user.is_active = True
            user.is_banned = False
            user.is_admin = is_admin
        await session.commit()

    # Store active client in session manager
    session_manager._active_clients[telegram_id] = client

    # Register Saved Messages listener & background poller
    await register_saved_message_handlers(client, telegram_id)

    # Sync scheduler job
    await scheduler_manager.sync_user_job(telegram_id)

    await state.clear()
    logger.info(f"[ONBOARDING SUCCESS] User {telegram_id} registered and userbot started successfully!")

    await message.answer(
        strings.ONBOARDING_SUCCESS,
        reply_markup=get_remove_keyboard(),
        parse_mode="Markdown",
    )
