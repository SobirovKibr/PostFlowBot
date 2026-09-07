"""
Sticker management module for Telegram Userbot.
Loads sticker sets from stickers.json, selects rotating stickers,
and interfaces with Telethon for sticker transmission.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from telethon import TelegramClient
from telethon.errors import FileReferenceExpiredError
from telethon.tl import functions, types

from logger import logger
from state_manager import state

STICKERS_FILE = Path(__file__).resolve().parent / "stickers.json"


def load_stickers_catalog() -> Dict[str, Any]:
    """Loads sticker sets catalog from stickers.json."""
    if not STICKERS_FILE.exists():
        return {}
    try:
        with open(STICKERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read {STICKERS_FILE}: {e}")
        return {}


def get_available_sticker_sets() -> List[Dict[str, Any]]:
    """Returns list of loaded sticker set summaries."""
    catalog = load_stickers_catalog()
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


def get_active_sticker() -> Optional[Dict[str, Any]]:
    """
    Returns the current sticker dictionary to send for this round based on state.
    Returns None if stickers are not configured or no sticker sets exist.
    """
    catalog = load_stickers_catalog()
    if not catalog:
        return None

    # Determine which set to use
    chosen_set_name = state.current_sticker_set
    if not chosen_set_name or chosen_set_name not in catalog:
        # Fallback to the first set in the catalog
        chosen_set_name = next(iter(catalog.keys()))
        state.current_sticker_set = chosen_set_name

    sticker_set = catalog.get(chosen_set_name, {})
    stickers = sticker_set.get("stickers", [])
    if not stickers:
        return None

    current_idx = state.sticker_index % len(stickers)
    sticker_info = dict(stickers[current_idx])
    sticker_info["set_short_name"] = chosen_set_name
    sticker_info["index_in_set"] = current_idx + 1
    sticker_info["total_in_set"] = len(stickers)
    return sticker_info


async def prepare_input_document(
    client: TelegramClient,
    sticker_info: Dict[str, Any]
) -> types.InputDocument:
    """
    Creates an InputDocument from saved sticker info.
    If the file reference is expired, it queries Telegram to refresh it.
    """
    doc_id = sticker_info["id"]
    access_hash = sticker_info["access_hash"]
    file_ref_hex = sticker_info.get("file_reference_hex", "")
    file_ref = bytes.fromhex(file_ref_hex) if file_ref_hex else b""

    return types.InputDocument(
        id=doc_id,
        access_hash=access_hash,
        file_reference=file_ref,
    )


async def refresh_sticker_document(
    client: TelegramClient,
    set_short_name: str,
    doc_id: int
) -> Optional[types.Document]:
    """
    Fetches the latest Document object directly from Telegram servers
    when a file reference expires.
    """
    try:
        logger.info(f"Refreshing expired file reference for sticker {doc_id} from set '{set_short_name}'...")
        res = await client(functions.messages.GetStickerSetRequest(
            stickerset=types.InputStickerSetShortName(short_name=set_short_name),
            hash=0
        ))
        for doc in res.documents:
            if doc.id == doc_id:
                return doc
    except Exception as e:
        logger.error(f"Failed to refresh sticker set '{set_short_name}': {e}")
    return None


def extract_sticker_attributes(doc: types.Document) -> str:
    """Extracts emoji representation for sticker document."""
    for attr in doc.attributes:
        if isinstance(attr, types.DocumentAttributeSticker):
            return attr.alt or "🎨"
    return "🎨"


async def resync_stickers_from_telegram(
    client: TelegramClient,
    target_set: Optional[str] = None
) -> Tuple[bool, str, int, int]:
    """
    Directly queries Telegram servers for installed sticker sets,
    fetches all sticker documents, and updates stickers.json.

    Returns:
        (success: bool, status_message: str, sets_count: int, stickers_count: int)
    """
    try:
        logger.info("[RESYNC] Querying installed sticker sets from Telegram...")
        res = await client(functions.messages.GetAllStickersRequest(hash=0))
        if not res.sets:
            return False, "Akkauntingizda o'rnatilgan stiker to'plamlari topilmadi.", 0, 0

        installed_sets = res.sets
        selected_sets = []

        if target_set:
            selected_sets = [s for s in installed_sets if s.short_name.lower() == target_set.lower()]
            if not selected_sets:
                return False, f"'{target_set}' nomli stiker to'plami akkauntingizda topilmadi.", len(installed_sets), 0
        else:
            selected_sets = installed_sets

        catalog = load_stickers_catalog()
        total_stickers_saved = 0

        for s in selected_sets:
            try:
                full_set = await client(functions.messages.GetStickerSetRequest(
                    stickerset=types.InputStickerSetShortName(short_name=s.short_name),
                    hash=0
                ))
            except Exception as e:
                logger.warning(f"[RESYNC] Could not fetch set '{s.short_name}': {e}")
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

        # Atomically write to stickers.json
        tmp_file = STICKERS_FILE.with_suffix(".tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2, ensure_ascii=False)
        tmp_file.replace(STICKERS_FILE)

        # Set default active set if none chosen yet
        if not state.current_sticker_set and catalog:
            state.current_sticker_set = next(iter(catalog.keys()))

        return True, "Stikerlar muvaffaqiyatli sinxronizatsiya qilindi!", len(catalog), total_stickers_saved

    except Exception as e:
        logger.error(f"[RESYNC ERROR] Failed to resync stickers: {e}", exc_info=True)
        return False, f"Sinxronizatsiyada xatolik yuz berdi: {e}", 0, 0

