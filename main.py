"""
Entry point for Telegram Automated Scheduler Userbot with Saved Messages Control & Stickers.
Initializes Telethon MTProto Client, registers Saved Messages control commands,
displays startup configuration summary, and runs background scheduler.
"""

import asyncio
import signal
import sys
from telethon import TelegramClient

from commands import poll_saved_messages, register_command_handlers
import config
from groups_manager import load_groups
from logger import logger
from messages_manager import load_messages
from scheduler import run_scheduler
from state_manager import state
import stickers_manager


def print_banner(me):
    """Prints application banner and configuration summary on startup."""
    groups = load_groups()
    messages = load_messages()
    sets = stickers_manager.get_available_sticker_sets()

    sticker_status = "O'chirilgan (OFF)"
    if state.sticker_enabled:
        s_name = state.current_sticker_set or (sets[0]["short_name"] if sets else "Yo'q")
        sticker_status = f"Yoqilgan (ON) [To'plam: {s_name}]"

    banner = rf"""
======================================================================
  _____    _                                _   _               ____        _   
 |_   _|__| | ___  __ _ _ __ __ _ _ __ ___ | | | |___  ___ _ __| __ )  ___ | |_ 
   | |/ _ \ |/ _ \/ _` | '__/ _` | '_ ` _ \| | | / __|/ _ \ '__|  _ \ / _ \| __|
   | |  __/ |  __/ (_| | | | (_| | | | | | | |_| \__ \  __/ |  | |_) | (_) | |_ 
   |_|\___|_|\___|\__, |_|  \__,_|_| |_| |_|\___/|___/\___|_|  |____/ \___/ \__|
                  |___/                                                         
======================================================================
[+] Telegram Userbot Scheduled Broadcaster (Telethon MTProto)
[+] Saved Messages Control System Active: Send /help to Saved Messages
----------------------------------------------------------------------
 Akkaunt Ma'lumotlari:
  - Foydalanuvchi      : {me.first_name} (@{me.username or 'NoUsername'}) [ID: {me.id}]
  - Telefon            : {config.PHONE_NUMBER}
  - API ID             : {config.API_ID}
  - Sessiya Fayli      : {config.SESSION_NAME}.session

 Ish Sozlamalari (state.json):
  - Holat (Scheduler)  : {'Faol (Running)' if state.is_scheduler_running else 'Toxtatilgan (Paused)'}
  - Vaqt Mintaqasi     : {state.timezone_str}
  - Faol Ish Vaqti     : {state.start_time_str} - {state.end_time_str}
  - Oraliq (Interval)  : {state.interval_minutes} daqiqa (Jitter: +/-{state._data.get('round_jitter_seconds', 60)}s)
  - Guruhlararo Kutilma: {state._data.get('min_delay_between_groups', 25)}s - {state._data.get('max_delay_between_groups', 55)}s
  - Target Guruhlar    : {len(groups)} ta guruh (groups.txt)
  - Xabarlar Shablonlari: {len(messages)} ta xabar (messages.txt)
  - Stiker Yuborish    : {sticker_status} ({len(sets)} to'plam stickers.json da)
======================================================================
"""
    print(banner)


async def main():
    """Main application lifecycle runner."""
    errors = config.validate_config()
    if errors:
        for err in errors:
            logger.error(f"[CONFIG ERROR] {err}")
        print("\nPlease fix the above configuration errors in your .env file and restart.")
        sys.exit(1)

    logger.info("Initializing Telegram MTProto Client...")

    client = TelegramClient(
        session=config.SESSION_NAME,
        api_id=config.API_ID,
        api_hash=config.API_HASH,
    )

    try:
        await client.start(phone=config.PHONE_NUMBER)
    except Exception as e:
        logger.critical(f"Failed to authenticate with Telegram: {e}", exc_info=True)
        sys.exit(1)

    me = await client.get_me()
    print_banner(me)
    logger.info(f"Bot successfully authenticated as {me.first_name} [ID: {me.id}]")

    # Register event listener and reliable poller for Saved Messages commands
    register_command_handlers(client, me.id)
    poller_task = asyncio.create_task(poll_saved_messages(client))
    logger.info("Saved Messages command listener & poller registered successfully.")

    # Start background broadcasting loop
    scheduler_task = asyncio.create_task(run_scheduler(client))

    loop = asyncio.get_running_loop()

    def handle_shutdown(sig_name):
        logger.info(f"Received shutdown signal {sig_name}. Stopping userbot...")
        scheduler_task.cancel()
        poller_task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig.name: handle_shutdown(s))
        except NotImplementedError:
            pass

    try:
        await asyncio.gather(
            scheduler_task,
            poller_task,
            client.run_until_disconnected(),
            return_exceptions=True
        )
    except asyncio.CancelledError:
        logger.info("Main lifecycle cancelled.")
    finally:
        logger.info("Closing Telegram client connection...")
        await client.disconnect()
        logger.info("Userbot shutdown complete. Goodbye!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProcess interrupted. Exiting...")
