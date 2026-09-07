"""
Scheduler module for Telegram Userbot.
Manages continuous background broadcast loop, message and sticker rotation,
operating window enforcement, and on-demand manual broadcasting.
"""

import asyncio
import random
import time
from datetime import datetime
from typing import Any, Callable, Optional, Tuple
from telethon import TelegramClient

from groups_manager import load_groups
from logger import logger
from messages_manager import load_messages
from sender import send_message_to_group, send_sticker_to_group
from state_manager import state
import stickers_manager

# Lock to ensure only one broadcast round runs at a time
broadcast_lock = asyncio.Lock()

# Event used to immediately wake up scheduler (e.g. on /start_sending or interval update)
scheduler_wakeup_event = asyncio.Event()


async def execute_broadcast_round(
    client: TelegramClient,
    is_manual: bool = False
) -> Tuple[int, int, int]:
    """
    Executes a single broadcast round across all target groups.
    Sends the current rotating message, followed optionally by a rotating sticker.

    Returns:
        Tuple[int, int, int]: (success_count, fail_count, total_groups)
    """
    async with broadcast_lock:
        groups = load_groups()
        messages = load_messages()

        if not groups:
            logger.warning("[BROADCAST] Target groups list is empty (groups.txt).")
            return 0, 0, 0

        if not messages:
            logger.warning("[BROADCAST] Messages template list is empty (messages.txt).")
            return 0, 0, 0

        # Rotate message
        msg_idx = state.message_index % len(messages)
        current_message = messages[msg_idx]
        preview = current_message[:60].replace("\n", " ") + ("..." if len(current_message) > 60 else "")

        # Prepare sticker if enabled
        active_sticker = None
        if state.sticker_enabled:
            active_sticker = stickers_manager.get_active_sticker()

        tz = state.timezone
        now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        round_type = "MANUAL (/send_now)" if is_manual else "SCHEDULED"

        logger.info("=" * 65)
        logger.info(f"--- STARTING {round_type} BROADCAST ROUND ---")
        logger.info(f"Local Time: {now_str} ({state.timezone_str})")
        logger.info(f"Total Groups: {len(groups)}")
        logger.info(f"Message Template #{msg_idx + 1}/{len(messages)}: \"{preview}\"")
        if active_sticker:
            logger.info(
                f"Sticker: Set '{active_sticker.get('set_short_name')}' "
                f"(#{active_sticker.get('index_in_set')}/{active_sticker.get('total_in_set')}) "
                f"Emoji: {active_sticker.get('emoji', '🎨')}"
            )
        else:
            logger.info("Sticker Sending: DISABLED (or no stickers.json loaded)")
        logger.info("=" * 65)

        success_count = 0
        fail_count = 0

        min_delay = int(state._data.get("min_delay_between_groups", 25))
        max_delay = int(state._data.get("max_delay_between_groups", 55))

        for idx, target in enumerate(groups, start=1):
            # Check operating hours during broadcast (unless manual)
            if not is_manual:
                is_open, _ = state.is_within_operating_hours()
                if not is_open:
                    logger.warning("[WINDOW CLOSED] Operating hours ended during broadcasting. Pausing round.")
                    break

            logger.info(f"[{idx}/{len(groups)}] Broadcasting to: {target}")
            
            # 1. Send Text Message
            msg_ok = await send_message_to_group(client, target, current_message)
            
            # 2. Send Sticker if enabled and message succeeded
            sticker_ok = True
            if msg_ok and active_sticker:
                await asyncio.sleep(2.5)  # Natural human pause between text and sticker
                sticker_ok = await send_sticker_to_group(client, target, active_sticker)

            if msg_ok:
                success_count += 1
            else:
                fail_count += 1

            # Anti-ban delay between groups
            if idx < len(groups):
                delay = random.uniform(min_delay, max_delay)
                logger.info(f"[ANTI-BAN] Sleeping {delay:.1f}s before next group...")
                await asyncio.sleep(delay)

        # Update persistent rotation indexes
        state.message_index = (state.message_index + 1) % len(messages)
        if active_sticker:
            state.sticker_index += 1
        state.last_run_timestamp = time.time()

        logger.info("=" * 65)
        logger.info(
            f"--- FINISHED {round_type} ROUND | "
            f"Success: {success_count} | Failed: {fail_count} | Total: {len(groups)} ---"
        )
        logger.info("=" * 65)

        return success_count, fail_count, len(groups)


async def trigger_manual_send(
    client: TelegramClient,
    status_callback: Optional[Callable[[str], Any]] = None
) -> Tuple[bool, str]:
    """
    Triggered when user executes /send_now in Saved Messages.
    Runs an immediate broadcast round outside the normal schedule.
    """
    if broadcast_lock.locked():
        return False, "⚠️ Hozirda allaqachon xabar yuborish jarayoni ketmoqda. Iltimos, kuting."

    if status_callback:
        await status_callback("🚀 Guruhlarga darhol xabar yuborish boshlandi...")

    success, failed, total = await execute_broadcast_round(client, is_manual=True)

    result_text = (
        f"🏁 **Qo'lda yuborish yakunlandi!**\n\n"
        f"✅ Muvaffaqiyatli: `{success}` ta\n"
        f"❌ Xatolik: `{failed}` ta\n"
        f"📊 Jami guruhlar: `{total}` ta"
    )

    if status_callback:
        await status_callback(result_text)

    return True, result_text


async def run_scheduler(client: TelegramClient):
    """
    Continuous background loop for scheduled broadcasts.
    Monitors state.is_scheduler_running and operating hours window.
    """
    logger.info("Auto-sending background scheduler initialized.")

    while True:
        try:
            # 1. Check if user paused sending via /stop_sending
            if not state.is_scheduler_running:
                logger.info("[SCHEDULER PAUSED] Scheduler is paused (/stop_sending). Waiting for /start_sending...")
                state.next_run_timestamp = None
                # Wait until awakened by /start_sending or check every 30s
                try:
                    await asyncio.wait_for(scheduler_wakeup_event.wait(), timeout=30.0)
                    scheduler_wakeup_event.clear()
                except asyncio.TimeoutError:
                    continue

            # 2. Check operating hours
            is_open, seconds_until_open = state.is_within_operating_hours()
            if not is_open:
                state.next_run_timestamp = time.time() + seconds_until_open
                hours = seconds_until_open // 3600
                mins = (seconds_until_open % 3600) // 60
                secs = seconds_until_open % 60
                logger.info(
                    f"[SCHEDULE SLEEP] Outside active window ({state.start_time_str} - {state.end_time_str} {state.timezone_str}). "
                    f"Sleeping {hours:02d}h {mins:02d}m {secs:02d}s until window opens..."
                )
                try:
                    await asyncio.wait_for(scheduler_wakeup_event.wait(), timeout=min(seconds_until_open, 300))
                    scheduler_wakeup_event.clear()
                except asyncio.TimeoutError:
                    pass
                continue

            # 3. Check groups and messages availability
            groups = load_groups()
            messages = load_messages()
            if not groups or not messages:
                logger.warning("[SCHEDULER IDLE] Target groups or messages are empty. Sleeping 60s...")
                await asyncio.sleep(60)
                continue

            # 4. Execute scheduled round
            await execute_broadcast_round(client, is_manual=False)

            # 5. Calculate sleep interval for next scheduled round
            base_seconds = state.interval_minutes * 60.0
            jitter_range = float(state._data.get("round_jitter_seconds", 60))
            jitter = random.uniform(-jitter_range, jitter_range)
            sleep_duration = max(30.0, base_seconds + jitter)

            state.next_run_timestamp = time.time() + sleep_duration
            next_dt = datetime.fromtimestamp(state.next_run_timestamp, tz=state.timezone)

            logger.info(
                f"[NEXT ROUND] Scheduled in {sleep_duration / 60:.1f} minutes "
                f"at {next_dt.strftime('%H:%M:%S')} ({state.timezone_str}). Sleeping..."
            )

            # Sleep until next round or until awakened by a command
            try:
                await asyncio.wait_for(scheduler_wakeup_event.wait(), timeout=sleep_duration)
                scheduler_wakeup_event.clear()
            except asyncio.TimeoutError:
                pass

        except asyncio.CancelledError:
            logger.info("Scheduler task cancelled. Exiting loop.")
            break
        except Exception as e:
            logger.error(f"[SCHEDULER ERROR] Unexpected error in loop: {type(e).__name__} - {e}", exc_info=True)
            await asyncio.sleep(60)
