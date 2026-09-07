"""
Admin router for Aiogram 3.x.
Provides system monitoring, user management, banning/unbanning,
broadcasting announcements, and API key status checks.
"""

from datetime import datetime
from typing import Optional
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from loguru import logger

import config
from bot.keyboards import (
    get_admin_main_inline_keyboard,
    get_user_actions_keyboard,
    get_users_pagination_keyboard,
)
from core.key_manager import key_manager
from core.scheduler import scheduler_manager
from core.session_manager import decrypt_phone, session_manager
from db import crud
from db.database import get_db

router = Router(name="admin")


def is_admin(telegram_id: int) -> bool:
    """Verifies whether the user is configured in ADMIN_IDS."""
    return telegram_id in config.ADMIN_IDS


@router.message(Command("admin", "admin_panel", "panel"))
async def cmd_admin_panel(message: Message):
    """Admin Dashboard entry point."""
    if not is_admin(message.from_user.id):
        return

    text = (
        "👑 **ADMIN BOSHQARUV PANELI**\n\n"
        "Quyidagi bo'limlardan birini tanlang yoki to'g'ridan-to'g'ri buyruqlardan foydalaning:\n\n"
        "• `/admin_stats` — Tizim statistikasi\n"
        "• `/admin_users` — Foydalanuvchilar ro'yxati\n"
        "• `/admin_user <id>` — Foydalanuvchi ma'lumotlari\n"
        "• `/admin_ban <id>` — Foydalanuvchini bloklash\n"
        "• `/admin_unban <id>` — Blokdan chiqarish\n"
        "• `/admin_broadcast <xabar>` — Hammaga xabar yuborish\n"
        "• `/admin_key_status` — API kalitlari holati\n"
        "• `/admin_restart_user <id>` — Sessiyani qayta ishga tushirish\n"
    )
    await message.answer(text, reply_markup=get_admin_main_inline_keyboard(), parse_mode="Markdown")


@router.message(Command("admin_stats"))
@router.callback_query(F.data == "admin_stats")
async def handle_admin_stats(event: Message | CallbackQuery):
    """Displays comprehensive SaaS operational metrics."""
    user_id = event.from_user.id
    if not is_admin(user_id):
        return

    async with get_db() as session:
        stats = await crud.get_system_stats(session)

    # Active userbots in memory
    active_in_mem = sum(
        1 for c in session_manager._active_clients.values() if c and c.is_connected()
    )

    text = (
        "📊 **TIZIMNING TO'LIQ STATISTIKASI**\n"
        "────────────────────────────\n"
        f"👥 **Jami ro'yxatdan o'tganlar:** `{stats['total_users']}` ta\n"
        f"🟢 **Faol foydalanuvchilar:** `{stats['active_users']}` ta\n"
        f"🔴 **Bloklangan foydalanuvchilar:** `{stats['banned_users']}` ta\n"
        f"⚡ **Xotirada ishlayotgan userbotlar:** `{active_in_mem}` ta\n"
        f"👥 **Jami target guruhlar:** `{stats['total_groups']}` ta\n"
        f"📝 **Jami xabarlar shablonlari:** `{stats['total_messages']}` ta\n"
        "────────────────────────────"
    )

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=get_admin_main_inline_keyboard(), parse_mode="Markdown")
        await event.answer()
    else:
        await event.answer(text, reply_markup=get_admin_main_inline_keyboard(), parse_mode="Markdown")


@router.message(Command("admin_users"))
async def cmd_admin_users(message: Message):
    """Displays first page of users."""
    if not is_admin(message.from_user.id):
        return
    await render_users_page(message, offset=0)


@router.callback_query(F.data.startswith("admin_users_"))
async def cb_admin_users_page(callback: CallbackQuery):
    """Handles pagination for users list."""
    if not is_admin(callback.from_user.id):
        return
    offset = int(callback.data.split("_")[-1])
    await render_users_page(callback.message, offset=offset, edit=True)
    await callback.answer()


async def render_users_page(message: Message, offset: int = 0, edit: bool = False):
    limit = 10
    async with get_db() as session:
        users = await crud.list_users(session, limit=limit + 1, offset=offset)

    has_next = len(users) > limit
    page_users = users[:limit]

    if not page_users:
        text = "📭 Foydalanuvchilar ro'yxati bo'sh."
        if edit:
            await message.edit_text(text, reply_markup=get_admin_main_inline_keyboard())
        else:
            await message.answer(text, reply_markup=get_admin_main_inline_keyboard())
        return

    lines = [f"👥 **Foydalanuvchilar Ro'yxati** ({offset + 1} - {offset + len(page_users)}):\n"]
    for u in page_users:
        status_emoji = "🔴 [Banned]" if u.is_banned else ("🟢 [Active]" if u.is_active else "⚪ [Inactive]")
        uname = f"@{u.username}" if u.username else "No username"
        is_running = session_manager.is_user_running(u.telegram_id)
        run_mark = "⚡" if is_running else "💤"
        lines.append(f"• `{u.telegram_id}` | {uname} | {status_emoji} {run_mark}")

    lines.append("\n💡 *Batafsil ma'lumot uchun:* `/admin_user <telegram_id>`")
    text = "\n".join(lines)

    kb = get_users_pagination_keyboard(offset, has_next)
    if edit:
        await message.edit_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await message.answer(text, reply_markup=kb, parse_mode="Markdown")


@router.message(Command("admin_user"))
async def cmd_admin_user_detail(message: Message):
    """Shows in-depth user information."""
    if not is_admin(message.from_user.id):
        return

    parts = message.text.strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("⚠️ **Foydalanish:** `/admin_user <telegram_id>`")
        return

    target_tg_id = int(parts[1])
    async with get_db() as session:
        user = await crud.get_user_by_telegram_id(session, target_tg_id)
        if not user:
            await message.answer(f"⚠️ Foydalanuvchi topilmadi: `{target_tg_id}`")
            return

        groups = await crud.get_user_groups(session, user.id)
        messages = await crud.get_user_messages(session, user.id)
        state = await crud.get_or_create_state(session, user.id)

    phone_decrypted = decrypt_phone(user.phone)
    is_running = session_manager.is_user_running(target_tg_id)
    is_sched = scheduler_manager.is_user_scheduled(target_tg_id)

    key_label = config.API_KEYS[user.api_key_index]["label"] if user.api_key_index < len(config.API_KEYS) else f"Key #{user.api_key_index}"

    status_txt = "🔴 Bloklangan" if user.is_banned else ("🟢 Faol" if user.is_active else "⚪ Nofaol")
    live_txt = "🟢 Ishlayapti" if is_running else "💤 To'xtagan"
    sched_txt = "🟢 Jadvalda" if is_sched else "⏸️ Jadvalda emas"
    sending_txt = "✅ Yoqilgan" if state.is_sending else "⏸️ O'chirilgan"

    detail_text = (
        f"👤 **FOYDALANUVCHI MA'LUMOTLARI**\n"
        f"────────────────────────────\n"
        f"• **Telegram ID:** `{user.telegram_id}`\n"
        f"• **Username:** @{user.username or 'Mavjud emas'}\n"
        f"• **Telefon:** `{phone_decrypted}`\n"
        f"• **API Kalit:** `{key_label}` (Index: {user.api_key_index})\n"
        f"• **Holati:** {status_txt}\n"
        f"• **Userbot Live:** {live_txt}\n"
        f"• **Jadval (Scheduler):** {sched_txt}\n"
        f"• **Avto-yuborish:** {sending_txt}\n"
        f"• **Oraliq (Interval):** `{state.interval_minutes}` daqiqa\n"
        f"• **Ish vaqti:** `{state.start_time}` — `{state.end_time}`\n"
        f"• **Target Guruhlar:** `{len(groups)}` ta\n"
        f"• **Xabarlar:** `{len(messages)}` ta\n"
        f"• **Ro'yxatdan o'tgan:** `{user.created_at.strftime('%Y-%m-%d %H:%M')}`\n"
        f"• **Oxirgi faollik:** `{user.last_seen.strftime('%Y-%m-%d %H:%M')}`\n"
        f"────────────────────────────"
    )

    await message.answer(
        detail_text,
        reply_markup=get_user_actions_keyboard(user.telegram_id, user.is_banned),
        parse_mode="Markdown",
    )


@router.message(Command("admin_ban"))
async def cmd_admin_ban(message: Message):
    """Bans a user, terminates their live userbot session, and cancels scheduler job."""
    if not is_admin(message.from_user.id):
        return

    parts = message.text.strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("⚠️ **Foydalanish:** `/admin_ban <telegram_id>`")
        return

    target_id = int(parts[1])
    await execute_ban(message, target_id)


@router.callback_query(F.data.startswith("ban_"))
async def cb_admin_ban(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    target_id = int(callback.data.split("_")[-1])
    await execute_ban(callback.message, target_id)
    await callback.answer("Foydalanuvchi bloklandi.")


async def execute_ban(message: Message, target_id: int):
    async with get_db() as session:
        ok = await crud.set_user_ban_status(session, target_id, is_banned=True)
        await session.commit()

    if not ok:
        await message.answer(f"⚠️ Foydalanuvchi topilmadi: `{target_id}`")
        return

    # Disconnect live session and remove scheduler job
    await session_manager.stop_user_session(target_id)
    scheduler_manager.remove_user_job(target_id)

    logger.warning(f"[ADMIN BAN] User {target_id} was banned by admin.")
    await message.answer(f"🔴 **Foydalanuvchi `{target_id}` muvaffaqiyatli bloklandi.**\nSessiyasi va jadvali to'xtatildi.")


@router.message(Command("admin_unban"))
async def cmd_admin_unban(message: Message):
    """Unbans a user and resumes their scheduler job if active."""
    if not is_admin(message.from_user.id):
        return

    parts = message.text.strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("⚠️ **Foydalanish:** `/admin_unban <telegram_id>`")
        return

    target_id = int(parts[1])
    await execute_unban(message, target_id)


@router.callback_query(F.data.startswith("unban_"))
async def cb_admin_unban(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    target_id = int(callback.data.split("_")[-1])
    await execute_unban(callback.message, target_id)
    await callback.answer("Blokdan chiqarildi.")


async def execute_unban(message: Message, target_id: int):
    async with get_db() as session:
        ok = await crud.set_user_ban_status(session, target_id, is_banned=False)
        await session.commit()

    if not ok:
        await message.answer(f"⚠️ Foydalanuvchi topilmadi: `{target_id}`")
        return

    # Reconnect user session
    await session_manager.start_user_session(target_id)
    await scheduler_manager.sync_user_job(target_id)

    logger.info(f"[ADMIN UNBAN] User {target_id} unbanned by admin.")
    await message.answer(f"🟢 **Foydalanuvchi `{target_id}` blokdan chiqarildi.**\nUserbot qayta faollashtirildi.")


@router.message(Command("admin_restart_user"))
async def cmd_admin_restart_user(message: Message):
    """Restarts a user's Telethon userbot instance."""
    if not is_admin(message.from_user.id):
        return

    parts = message.text.strip().split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("⚠️ **Foydalanish:** `/admin_restart_user <telegram_id>`")
        return

    target_id = int(parts[1])
    await execute_restart_user(message, target_id)


@router.callback_query(F.data.startswith("restart_"))
async def cb_admin_restart_user(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return
    target_id = int(callback.data.split("_")[-1])
    await execute_restart_user(callback.message, target_id)
    await callback.answer("Sessiya qayta yuklandi.")


async def execute_restart_user(message: Message, target_id: int):
    await session_manager.stop_user_session(target_id)
    client = await session_manager.start_user_session(target_id)
    if client:
        await scheduler_manager.sync_user_job(target_id)
        await message.answer(f"✅ **Foydalanuvchi `{target_id}` userboti qayta ishga tushirildi!**")
    else:
        await message.answer(f"⚠️ Userbotni ishga tushirib bo'lmadi (sessiya fayli yo'q yoki avtorizatsiyadan o'tmagan).")


@router.message(Command("admin_key_status"))
@router.callback_query(F.data == "admin_keys")
async def cmd_admin_key_status(event: Message | CallbackQuery):
    """Performs live health-check on Primary and Fallback Telegram API credentials."""
    if not is_admin(event.from_user.id):
        return

    progress = await (event.message.edit_text if isinstance(event, CallbackQuery) else event.answer)(
        "⏳ **API kalitlari holati tekshirilmoqda...**"
    )

    results = await key_manager.health_check_keys()
    lines = ["🔑 **TELEGRAM API KALITLARI HOLATI**\n────────────────────────────\n"]
    for res in results:
        status_icon = "🟢" if res["status"] == "Active" else "🔴"
        lines.append(f"{status_icon} **{res['label']} (ID: `{res['api_id']}`)**")
        lines.append(f"• Holat: `{res['status']}`")
        if res.get("error"):
            lines.append(f"• Xatolik: `{res['error']}`")
        lines.append("")

    lines.append("────────────────────────────")
    output_text = "\n".join(lines)

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(output_text, reply_markup=get_admin_main_inline_keyboard(), parse_mode="Markdown")
        await event.answer()
    else:
        await event.answer(output_text, reply_markup=get_admin_main_inline_keyboard(), parse_mode="Markdown")


@router.message(Command("admin_broadcast"))
async def cmd_admin_broadcast(message: Message):
    """Broadcasts a global message from admin to all registered users via bot."""
    if not is_admin(message.from_user.id):
        return

    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer("⚠️ **Foydalanish:** `/admin_broadcast <xabar matni>`")
        return

    broadcast_text = f"📢 **ADMIN XABARI:**\n\n{parts[1].strip()}"

    async with get_db() as session:
        users = await crud.get_all_active_users(session)

    sent = 0
    failed = 0
    status_msg = await message.answer(f"⏳ `{len(users)}` ta foydalanuvchiga yuborilmoqda...")

    for u in users:
        try:
            await message.bot.send_message(u.telegram_id, broadcast_text, parse_mode="Markdown")
            sent += 1
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"✅ **E'lon yuborildi!**\n\n🎯 Yetkazildi: `{sent}` ta\n⚠️ Yetkazilmadi: `{failed}` ta",
        parse_mode="Markdown",
    )
