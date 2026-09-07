"""
Keyboards module for Aiogram 3.x Onboarding and Admin Bot.
"""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)


def get_phone_keyboard() -> ReplyKeyboardMarkup:
    """Keyboard requesting user's contact with a cancel option."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Kontaktni yuborish", request_contact=True)],
            [KeyboardButton(text="❌ Bekor qilish")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Simple cancel keyboard for OTP and 2FA input states."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Bekor qilish")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def get_remove_keyboard() -> ReplyKeyboardRemove:
    """Removes reply keyboard."""
    return ReplyKeyboardRemove()


def get_admin_main_inline_keyboard() -> InlineKeyboardMarkup:
    """Admin dashboard quick navigation buttons."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Tizim Statistikasi", callback_data="admin_stats"),
                InlineKeyboardButton(text="👥 Foydalanuvchilar", callback_data="admin_users_0"),
            ],
            [
                InlineKeyboardButton(text="🔑 API Kalitlar Holati", callback_data="admin_keys"),
                InlineKeyboardButton(text="📢 Umumiy Xabar", callback_data="admin_broadcast_prompt"),
            ],
        ]
    )


def get_user_actions_keyboard(telegram_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    """Inline keyboard for managing a specific user."""
    ban_button = (
        InlineKeyboardButton(text="🟢 Blokdan chiqarish", callback_data=f"unban_{telegram_id}")
        if is_banned
        else InlineKeyboardButton(text="🔴 Bloklash (Ban)", callback_data=f"ban_{telegram_id}")
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                ban_button,
                InlineKeyboardButton(text="🔄 Sessiyani qayta yuklash", callback_data=f"restart_{telegram_id}"),
            ],
            [
                InlineKeyboardButton(text="⬅️ Ro'yxatga qaytish", callback_data="admin_users_0"),
            ],
        ]
    )


def get_users_pagination_keyboard(offset: int, has_next: bool) -> InlineKeyboardMarkup:
    """Pagination navigation buttons for users list."""
    buttons = []
    if offset >= 10:
        buttons.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data=f"admin_users_{offset - 10}"))
    if has_next:
        buttons.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data=f"admin_users_{offset + 10}"))

    return InlineKeyboardMarkup(inline_keyboard=[buttons] if buttons else [])
