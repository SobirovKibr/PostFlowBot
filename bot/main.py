"""
Main Application Entrypoint for Multi-User Telegram Userbot SaaS.
Initializes Database, validates API keys, starts userbots, schedules jobs,
and runs the Aiogram 3.x Telegram Bot with graceful shutdown.
"""

import asyncio
import signal
import sys
from pathlib import Path

# Add project root directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from loguru import logger
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

import config
from bot.admin import router as admin_router
from bot.onboarding import router as onboarding_router
from core.key_manager import key_manager
from core.scheduler import scheduler_manager
from core.session_manager import session_manager
from db import crud
from db.database import get_db, init_db

# Configure Loguru
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
)
logger.add(
    config.BASE_DIR / "saas_userbot.log",
    rotation="20 MB",
    retention="14 days",
    level="DEBUG",
    encoding="utf-8",
)


async def print_startup_banner():
    """Prints a clear, informative startup banner."""
    print("=" * 65)
    print("🚀 MULTI-USER TELEGRAM USERBOT SAAS PLATFORM")
    print("=" * 65)
    print(f"📁 Base Directory:      {config.BASE_DIR}")
    print(f"🗄️ Database:            {config.DATABASE_URL.split('@')[-1] if '@' in config.DATABASE_URL else config.DATABASE_URL}")
    print(f"👑 Admin IDs:           {config.ADMIN_IDS}")
    print(f"🔑 Redundant API Keys:  {len(config.API_KEYS)} configured")
    for idx, k in enumerate(config.API_KEYS):
        print(f"   [{idx}] {k['label']}: api_id={k['api_id']}")
    print("=" * 65)


async def on_startup(bot: Bot):
    """Startup routine: initialize DB, test keys, and load active userbots."""
    try:
        me = await bot.get_me()
        if me.username:
            config.BOT_USERNAME = me.username
            logger.info(f"Bot identity resolved: @{me.username}")
    except Exception as e:
        logger.warning(f"Could not resolve bot username: {e}")

    await print_startup_banner()

    # 1. Initialize Database
    logger.info("Initializing database schema...")
    await init_db()
    logger.info("Database initialized successfully.")

    # 2. Check API Key health
    logger.info("Checking Telegram API Keys connectivity...")
    key_statuses = await key_manager.health_check_keys()
    for s in key_statuses:
        status_str = f"ONLINE" if s["status"] == "Active" else f"OFFLINE ({s.get('error')})"
        logger.info(f"-> Key [{s['label']} - {s['api_id']}]: {status_str}")

    # 3. Start MultiUser Scheduler
    scheduler_manager.start()

    # 4. Load all active users from database and start their userbots
    async with get_db() as session:
        active_users = await crud.get_all_active_users(session)
        logger.info(f"Discovered {len(active_users)} registered active user(s) in database.")

        started_count = 0
        for user in active_users:
            try:
                client = await session_manager.start_user_session(
                    telegram_id=user.telegram_id,
                    api_key_index=user.api_key_index,
                )
                if client:
                    started_count += 1
                    # Schedule broadcast job if state is active
                    await scheduler_manager.sync_user_job(user.telegram_id)
            except Exception as e:
                logger.error(f"Failed to auto-start userbot for user {user.telegram_id}: {e}")

        logger.info(f"Started {started_count}/{len(active_users)} userbot session(s).")


async def on_shutdown(bot: Bot):
    """Graceful shutdown routine."""
    logger.info("Initiating graceful shutdown sequence...")

    # Stop scheduler
    scheduler_manager.shutdown()

    # Disconnect all active user Telethon clients
    await session_manager.stop_all()

    # Close bot session
    await bot.session.close()
    logger.info("System shut down cleanly.")


async def main():
    if not config.BOT_TOKEN:
        logger.critical(
            "CRITICAL: BOT_TOKEN is missing! Please provide BOT_TOKEN in your .env file:\n"
            "BOT_TOKEN=\"your_bot_token_here\""
        )
        sys.exit(1)

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Include routers
    dp.include_router(admin_router)
    dp.include_router(onboarding_router)

    # Startup & Shutdown hooks
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Signal handlers
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda: asyncio.create_task(dp.stop_polling()))
        except NotImplementedError:
            pass

    logger.info("Starting Aiogram bot polling...")
    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        await on_shutdown(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Process terminated.")
