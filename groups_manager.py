"""
Groups management module for Telegram Userbot.
Handles reading, adding, removing, and listing target groups from groups.txt.
"""

from pathlib import Path
from typing import List, Tuple, Union

import config

GROUPS_FILE = config.GROUPS_FILE


def clean_target(target: str) -> str:
    """Cleans up group input (removes URLs, trailing slashes, spaces)."""
    t = target.strip()
    if "t.me/" in t:
        t = t.split("t.me/")[-1].strip("/")
    return t


def load_groups() -> List[Union[str, int]]:
    """Loads all active groups from groups.txt."""
    if not GROUPS_FILE.exists():
        return []

    groups = []
    with open(GROUPS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            clean = line.strip()
            if not clean or clean.startswith("#"):
                continue
            clean = clean_target(clean)
            if (clean.startswith("-") and clean[1:].isdigit()) or clean.isdigit():
                groups.append(int(clean))
            else:
                groups.append(clean)
    return groups


def add_group(raw_target: str) -> Tuple[bool, str, int]:
    """
    Adds a new target group to groups.txt.
    Returns (success, message, total_count).
    """
    target = clean_target(raw_target)
    if not target:
        return False, "Target group identifier cannot be empty.", len(load_groups())

    current_groups = load_groups()
    # Check for duplicates
    for g in current_groups:
        if str(g).lower() == target.lower():
            return False, f"Guruh allaqachon mavjud: {target}", len(current_groups)

    # Append to groups.txt
    try:
        with open(GROUPS_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n{target}")
        updated_groups = load_groups()
        return True, f"Guruh muvaffaqiyatli qo'shildi: {target}", len(updated_groups)
    except Exception as e:
        return False, f"Faylga yozishda xatolik: {e}", len(current_groups)


def remove_group(raw_target: str) -> Tuple[bool, str, int]:
    """
    Removes a target group from groups.txt.
    Returns (success, message, total_count).
    """
    target = clean_target(raw_target)
    if not target:
        return False, "Target group identifier cannot be empty.", len(load_groups())

    if not GROUPS_FILE.exists():
        return False, "groups.txt fayli mavjud emas.", 0

    with open(GROUPS_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

    found = False
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue

        c = clean_target(stripped)
        if c.lower() == target.lower():
            found = True
            # Skip this line (removed)
            continue
        new_lines.append(line)

    if not found:
        return False, f"Bunday guruh ro'yxatda topilmadi: {target}", len(load_groups())

    with open(GROUPS_FILE, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    remaining = load_groups()
    return True, f"Guruh ro'yxatdan o'chirildi: {target}", len(remaining)


def format_groups_list() -> str:
    """Formats the target groups list for Telegram reply."""
    groups = load_groups()
    if not groups:
        return "⚠️ Target guruhlar ro'yxati bo'sh.\n`/add_group <username>` orqali guruh qo'shing."

    text = f"📋 **Target guruhlar ro'yxati** (Jami: {len(groups)} ta):\n\n"
    for idx, g in enumerate(groups, start=1):
        text += f"`{idx}.` `{g}`\n"
    return text
