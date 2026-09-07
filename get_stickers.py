"""
Standalone helper script to inspect, extract, and export Telegram sticker sets (including Premium stickers).
Supports both multi-user SaaS environments (per user folder) and single-user setups.

Usage:
    python3 get_stickers.py --user <telegram_id>           (export for a specific user)
    python3 get_stickers.py --user <telegram_id> --all     (export all sets for user)
    python3 get_stickers.py --user <telegram_id> --set <name>
    python3 get_stickers.py --all                          (interactive or default session)
"""

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path
from telethon import TelegramClient
from telethon.tl import functions, types

import config
from core.key_manager import key_manager
from core.session_manager import get_user_session_path, get_user_dir


def extract_sticker_attributes(doc: types.Document) -> str:
    for attr in doc.attributes:
        if isinstance(attr, types.DocumentAttributeSticker):
            return attr.alt or "🎨"
    return "🎨"


async def export_stickers_for_user(
    telegram_id: int,
    set_filter: str = "all",
    api_key_index: int = 0,
):
    session_base = get_user_session_path(telegram_id)
    orig_session = Path(f"{session_base}.session")

    if not orig_session.exists():
        # Fallback to root session if exists
        root_session = config.BASE_DIR / "userbot_session.session"
        if root_session.exists():
            orig_session = root_session
        else:
            print(f"[-] Error: Session file for user {telegram_id} not found at {orig_session}")
            return

    # Use a temporary session copy to prevent database lock conflicts with running userbot
    temp_session_base = str(get_user_dir(telegram_id) / "temp_stickers_session")
    temp_session_file = Path(f"{temp_session_base}.session")
    shutil.copy(orig_session, temp_session_file)

    key_data = key_manager.get_key(api_key_index)

    print(f"\n[+] Connecting as user {telegram_id} (API Key: {key_data['label']})...")
    client = TelegramClient(
        session=temp_session_base,
        api_id=key_data["api_id"],
        api_hash=key_data["api_hash"],
    )

    output_file = get_user_dir(telegram_id) / "stickers.json"

    try:
        await client.connect()
        if not await client.is_user_authorized():
            print(f"[-] Session for user {telegram_id} is not authorized.")
            return

        me = await client.get_me()
        print(f"[+] Authenticated: {me.first_name} (@{me.username or 'NoUsername'}) [ID: {me.id}]")

        print("[*] Fetching installed sticker sets from Telegram...")
        all_stickers_res = await client(functions.messages.GetAllStickersRequest(hash=0))

        if not all_stickers_res.sets:
            print("[-] No sticker sets found on this account.")
            return

        installed_sets = all_stickers_res.sets
        print(f"\n[+] Discovered {len(installed_sets)} sticker set(s):")
        print("-" * 75)
        for idx, s in enumerate(installed_sets, start=1):
            print(f" [{idx:2d}] Short Name: {s.short_name:<28} | Count: {s.count:3d} | Title: {s.title}")
        print("-" * 75)

        selected_sets = []
        if set_filter == "all":
            selected_sets = installed_sets
        else:
            if set_filter.isdigit():
                idx_chosen = int(set_filter) - 1
                if 0 <= idx_chosen < len(installed_sets):
                    selected_sets = [installed_sets[idx_chosen]]
            else:
                matching = [s for s in installed_sets if s.short_name.lower() == set_filter.lower()]
                if matching:
                    selected_sets = matching
                else:
                    print(f"[-] Error: Could not find sticker set matching '{set_filter}'.")
                    return

        # Load existing catalog if present
        existing_catalog = {}
        if output_file.exists():
            try:
                with open(output_file, "r", encoding="utf-8") as f:
                    existing_catalog = json.load(f)
            except Exception:
                existing_catalog = {}

        for s in selected_sets:
            print(f"\n======================================================================")
            print(f" Fetching: '{s.title}' ({s.short_name})")
            print(f"======================================================================")

            try:
                full_set = await client(functions.messages.GetStickerSetRequest(
                    stickerset=types.InputStickerSetShortName(short_name=s.short_name),
                    hash=0
                ))
            except Exception as e:
                print(f"[-] Failed to fetch set {s.short_name}: {e}")
                continue

            stickers_data = []
            print(f"Total Stickers: {len(full_set.documents)}\n")
            print(f"{'#':<4} | {'Emoji':<6} | {'Document ID':<20} | {'Access Hash':<20}")
            print("-" * 65)

            for i, doc in enumerate(full_set.documents, start=1):
                emoji = extract_sticker_attributes(doc)
                file_ref_hex = doc.file_reference.hex() if doc.file_reference else ""
                print(f"#{i:<3} | {emoji:<6} | {doc.id:<20} | {doc.access_hash:<20}")
                stickers_data.append({
                    "id": doc.id,
                    "access_hash": doc.access_hash,
                    "file_reference_hex": file_ref_hex,
                    "emoji": emoji,
                    "mime_type": doc.mime_type,
                })

            existing_catalog[s.short_name] = {
                "title": s.title,
                "short_name": s.short_name,
                "count": len(stickers_data),
                "is_animated": any(doc.get("mime_type") == "application/x-tgsticker" for doc in stickers_data),
                "is_video": any("video" in doc.get("mime_type", "") for doc in stickers_data),
                "stickers": stickers_data,
            }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(existing_catalog, f, indent=2, ensure_ascii=False)

        # Also copy to root stickers.json if this is the first or main user
        root_stickers = config.BASE_DIR / "stickers.json"
        with open(root_stickers, "w", encoding="utf-8") as f:
            json.dump(existing_catalog, f, indent=2, ensure_ascii=False)

        print(f"\n[+] Successfully saved {len(selected_sets)} sticker set(s) to: {output_file}")
        print(f"[+] Total sticker sets now in catalog: {len(existing_catalog)}\n")

    finally:
        await client.disconnect()
        if temp_session_file.exists():
            temp_session_file.unlink(missing_ok=True)
        journal = Path(f"{temp_session_base}.session-journal")
        if journal.exists():
            journal.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Export Telegram sticker sets to stickers.json.")
    parser.add_argument("--user", type=int, default=8983737418, help="Telegram ID of the target user")
    parser.add_argument("--all", action="store_true", help="Export all installed sticker sets")
    parser.add_argument("--set", type=str, help="Short name or index of a specific sticker set")
    parser.add_argument("--key", type=int, default=0, help="API Key index (0: Primary, 1: Fallback)")
    args = parser.parse_args()

    filter_choice = "all"
    if args.set:
        filter_choice = args.set
    elif args.all:
        filter_choice = "all"

    try:
        asyncio.run(export_stickers_for_user(
            telegram_id=args.user,
            set_filter=filter_choice,
            api_key_index=args.key,
        ))
    except KeyboardInterrupt:
        print("\nOperation cancelled.")


if __name__ == "__main__":
    main()
