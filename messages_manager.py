"""
Messages management module for Telegram Userbot.
Handles reading, adding, removing, and listing rotation messages from messages.txt.
Full support for rich text and Telegram Premium Custom Emojis (<tg-emoji emoji-id="...">).
"""

import re
from pathlib import Path
from typing import List, Tuple
from telethon.extensions import html

import config
from state_manager import state

MESSAGES_FILE = config.MESSAGES_FILE


def load_messages() -> List[str]:
    """Loads message templates from messages.txt separated by '---'."""
    if not MESSAGES_FILE.exists():
        return []

    with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    raw_blocks = content.split("---")
    messages = [block.strip() for block in raw_blocks if block.strip()]
    return messages


def add_message(text: str) -> Tuple[bool, str, int]:
    """
    Appends a new raw message block to messages.txt.
    Returns (success, message, total_count).
    """
    clean_text = text.strip()
    if not clean_text:
        return False, "Xabar matni bo'sh bo'lishi mumkin emas.", len(load_messages())

    current_msgs = load_messages()
    try:
        separator = "\n---\n" if MESSAGES_FILE.exists() and current_msgs else ""
        with open(MESSAGES_FILE, "a", encoding="utf-8") as f:
            f.write(f"{separator}{clean_text}\n")
        updated = load_messages()
        return True, "Yangi xabar shabloni muvaffaqiyatli qo'shildi!", len(updated)
    except Exception as e:
        return False, f"Faylga yozishda xatolik yuz berdi: {e}", len(current_msgs)


def add_message_from_telegram(message_obj) -> Tuple[bool, str, int, int]:
    """
    Converts a Telegram Message object (with its custom emojis, bold, italics, links)
    into clean HTML representation and appends it to messages.txt.
    
    Returns:
        (success: bool, status_message: str, total_count: int, custom_emojis_count: int)
    """
    try:
        # Convert message to HTML preserving all Custom Emoji entities
        full_html = html.unparse(message_obj.message, message_obj.entities)
        
        # Strip '/add_message' command from the start
        clean_html = re.sub(r"^\s*/add_message(?:\s+|\n+)", "", full_html, count=1).strip()
        
        if not clean_html:
            return False, "Xabar matni bo'sh bo'lishi mumkin emas.", len(load_messages()), 0

        # Count custom emojis
        custom_cnt = 0
        if message_obj.entities:
            custom_cnt = sum(1 for e in message_obj.entities if hasattr(e, "document_id"))

        current_msgs = load_messages()
        separator = "\n---\n" if MESSAGES_FILE.exists() and current_msgs else ""
        with open(MESSAGES_FILE, "a", encoding="utf-8") as f:
            f.write(f"{separator}{clean_html}\n")

        updated = load_messages()
        return True, "Yangi xabar muvaffaqiyatli saqlandi!", len(updated), custom_cnt

    except Exception as e:
        return False, f"Xabarni saqlashda xatolik: {e}", len(load_messages()), 0


def remove_message(index_1based: int) -> Tuple[bool, str, int]:
    """
    Removes a message by its 1-based index and rewrites messages.txt.
    Returns (success, message, total_count).
    """
    messages = load_messages()
    if not messages:
        return False, "messages.txt faylida xabarlar mavjud emas.", 0

    if index_1based < 1 or index_1based > len(messages):
        return False, f"Noto'g'ri indeks. 1 dan {len(messages)} gacha bo'lgan son kiriting.", len(messages)

    target_idx = index_1based - 1
    # Strip HTML tags for preview
    raw_preview = re.sub(r"<[^>]+>", "", messages[target_idx])
    deleted_preview = raw_preview[:40].replace("\n", " ") + "..."
    del messages[target_idx]

    try:
        new_content = "\n---\n".join(messages) + ("\n" if messages else "")
        with open(MESSAGES_FILE, "w", encoding="utf-8") as f:
            f.write(new_content)

        if state.message_index >= len(messages) and len(messages) > 0:
            state.message_index = 0

        return True, f"Xabar #{index_1based} o'chirildi: \"{deleted_preview}\"", len(messages)
    except Exception as e:
        return False, f"Faylni yangilashda xatolik: {e}", len(messages)


def format_messages_list() -> str:
    """Formats all messages with their index numbers for Telegram display."""
    messages = load_messages()
    if not messages:
        return "⚠️ Xabarlar ro'yxati bo'sh.\n`/add_message <matn>` orqali yangi xabar qo'shing."

    current_idx = state.message_index % len(messages)
    text = f"📝 **Xabarlar shablonlari** (Jami: {len(messages)} ta):\n\n"

    for idx, msg in enumerate(messages, start=1):
        is_active = " 👈 [Navbatdagi]" if (idx - 1) == current_idx else ""
        # Strip HTML tags for list display
        plain_text = re.sub(r"<[^>]+>", "", msg)
        preview = plain_text if len(plain_text) <= 120 else (plain_text[:117] + "...")
        preview = preview.replace("\n", " ").strip()
        text += f"**[{idx}]**{is_active}\n_{preview}_\n\n"

    text += "💡 *Navbatdagi xabarni o'zgartirish uchun: `/set_message <raqam>`*"
    return text
