"""
Sticker Helper module for Multi-User Telegram Userbot SaaS.
Manages per-user sticker sets, storage in users/{telegram_id}/stickers.json,
rotation index, and Telegram sync.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from loguru import logger
from telethon import TelegramClient
from telethon.tl import functions, types

import config
from core.session_manager import get_user_dir


def get_user_stickers_path(telegram_id: int) -> Path:
    """Returns path to user's stickers.json file."""
    return get_user_dir(telegram_id) / "stickers.json"


def load_user_stickers(telegram_id: int) -> Dict[str, Any]:
    """Loads user's sticker sets. Falls back to global stickers.json if available."""
    user_file = get_user_stickers_path(telegram_id)
    if user_file.exists():
        try:
            with open(user_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read stickers for user {telegram_id}: {e}")

    # Global fallback if present
    global_file = config.BASE_DIR / "stickers.json"
    if global_file.exists():
        try:
            with open(global_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_user_stickers(telegram_id: int, catalog: Dict[str, Any]):
    """Saves sticker sets catalog atomically to user's directory."""
    user_file = get_user_stickers_path(telegram_id)
    tmp_file = user_file.with_suffix(".tmp")
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    tmp_file.replace(user_file)


def get_user_available_sets(telegram_id: int) -> List[Dict[str, Any]]:
    """Returns summary list of sticker sets for a user."""
    catalog = load_user_stickers(telegram_id)
    result = []
    for short_name, data in catalog.items():
        result.append({
            "short_name": short_name,
            "title": data.get("title", short_name),
            "count": len(data.get("stickers", [])),
            "is_animated": data.get("is_animated", False),
            "is_video": data.get("is_video", False),
        })
    return result


def get_user_active_sticker(telegram_id: int, current_set_name: Optional[str], sticker_index: int) -> Optional[Dict[str, Any]]:
    """
    Returns the sticker dictionary for the current round based on index.
    """
    catalog = load_user_stickers(telegram_id)
    if not catalog:
        return None

    chosen_set = current_set_name
    if not chosen_set or chosen_set not in catalog:
        chosen_set = next(iter(catalog.keys()))

    stickers = catalog.get(chosen_set, {}).get("stickers", [])
    if not stickers:
        return None

    current_idx = sticker_index % len(stickers)
    info = dict(stickers[current_idx])
    info["set_short_name"] = chosen_set
    info["index_in_set"] = current_idx + 1
    info["total_in_set"] = len(stickers)
    return info


def prepare_input_document(sticker_info: Dict[str, Any]) -> types.InputDocument:
    """Creates an InputDocument from saved sticker metadata."""
    doc_id = sticker_info["id"]
    access_hash = sticker_info["access_hash"]
    file_ref_hex = sticker_info.get("file_reference_hex", "")
    file_ref = bytes.fromhex(file_ref_hex) if file_ref_hex else b""

    return types.InputDocument(
        id=doc_id,
        access_hash=access_hash,
        file_reference=file_ref,
    )


def extract_sticker_attributes(doc: types.Document) -> str:
    """Extracts representative emoji for a sticker document."""
    for attr in doc.attributes:
        if isinstance(attr, types.DocumentAttributeSticker):
            return attr.alt or "🎨"
    return "🎨"


async def resync_user_stickers(
    client: TelegramClient,
    telegram_id: int,
    target_set: Optional[str] = None,
) -> Tuple[bool, str, int, int]:
    """
    Fetches sticker sets from Telegram for the user and saves them in user directory.
    """
    try:
        logger.info(f"[STICKERS] Querying installed stickers for user {telegram_id}...")
        res = await client(functions.messages.GetAllStickersRequest(hash=0))
        if not res.sets:
            return False, "Akkauntingizda o'rnatilgan stiker to'plamlari topilmadi.", 0, 0

        installed_sets = res.sets
        selected_sets = (
            [s for s in installed_sets if s.short_name.lower() == target_set.lower()]
            if target_set
            else installed_sets
        )

        if not selected_sets:
            return False, f"'{target_set}' nomli stiker to'plami topilmadi.", len(installed_sets), 0

        catalog = load_user_stickers(telegram_id)
        total_stickers_saved = 0

        for s in selected_sets:
            try:
                full_set = await client(functions.messages.GetStickerSetRequest(
                    stickerset=types.InputStickerSetShortName(short_name=s.short_name),
                    hash=0
                ))
            except Exception as e:
                logger.warning(f"[STICKERS] Could not fetch set '{s.short_name}' for user {telegram_id}: {e}")
                continue

            stickers_data = []
            for doc in full_set.documents:
                emoji = extract_sticker_attributes(doc)
                file_ref_hex = doc.file_reference.hex() if doc.file_reference else ""
                stickers_data.append({
                    "id": doc.id,
                    "access_hash": doc.access_hash,
                    "file_reference_hex": file_ref_hex,
                    "emoji": emoji,
                    "mime_type": doc.mime_type,
                })

            catalog[s.short_name] = {
                "title": s.title,
                "short_name": s.short_name,
                "count": len(stickers_data),
                "is_animated": any(doc.get("mime_type") == "application/x-tgsticker" for doc in stickers_data),
                "is_video": any("video" in doc.get("mime_type", "") for doc in stickers_data),
                "stickers": stickers_data,
            }
            total_stickers_saved += len(stickers_data)

        save_user_stickers(telegram_id, catalog)
        logger.info(f"[STICKERS] Saved {total_stickers_saved} stickers in {len(selected_sets)} sets for user {telegram_id}")
        return True, "Stikerlar muvaffaqiyatli sinxronizatsiya qilindi!", len(catalog), total_stickers_saved

    except Exception as e:
        logger.error(f"[STICKERS] Error resyncing stickers for user {telegram_id}: {e}")
        return False, f"Sinxronizatsiyada xatolik yuz berdi: {e}", 0, 0
