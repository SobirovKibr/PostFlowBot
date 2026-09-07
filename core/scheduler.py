"""
Multi-User Broadcast Scheduler module for Telegram Userbot SaaS.
Uses APScheduler (AsyncIOScheduler) to manage independent, per-user broadcast jobs,
operating hour window checks, message rotation, and sticker rotation.
"""

import asyncio
import random
from datetime import datetime, timedelta
from typing import Callable, Optional
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger
from telethon import TelegramClient

import config
from core.session_manager import session_manager
from core.sender import send_to_group
from core import sticker_helper
from db.database import get_db
from db import crud


class MultiUserScheduler:
    """Manages APScheduler jobs for each active onboarded user."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone=config.DEFAULT_TIMEZONE)
        self._is_running = False

    def start(self):
        """Starts APScheduler daemon."""
        if not self._is_running:
            self.scheduler.start()
            self._is_running = True
            logger.info("MultiUserScheduler started.")

    def shutdown(self):
        """Shuts down scheduler gracefully."""
        if self._is_running:
            try:
                self.scheduler.shutdown(wait=False)
            except Exception as e:
                logger.warning(f"Error shutting down scheduler: {e}")
            self._is_running = False
            logger.info("MultiUserScheduler stopped.")

    def get_job_id(self, telegram_id: int) -> str:
        return f"broadcast_user_{telegram_id}"

    def is_user_scheduled(self, telegram_id: int) -> bool:
        job = self.scheduler.get_job(self.get_job_id(telegram_id))
        return job is not None

    def get_next_run_time(self, telegram_id: int) -> Optional[datetime]:
        job = self.scheduler.get_job(self.get_job_id(telegram_id))
        if job and job.next_run_time:
            return job.next_run_time
        return None

    def is_within_operating_hours(self, start_str: str, end_str: str, tz_str: str) -> bool:
        """Checks if current time falls within user's configured working window."""
        try:
            tz = pytz.timezone(tz_str)
        except Exception:
            tz = pytz.timezone(config.DEFAULT_TIMEZONE)

        now = datetime.now(tz).time()
        try:
            s_time = datetime.strptime(start_str.strip(), "%H:%M").time()
            e_time = datetime.strptime(end_str.strip(), "%H:%M").time()
        except Exception:
            return True

        if s_time <= e_time:
            return s_time <= now <= e_time
        else:
            # Crosses midnight (e.g. 22:00 to 06:00)
            return now >= s_time or now <= e_time

    async def sync_user_job(self, telegram_id: int):
        """
        Reads user's active state from DB and schedules, updates, or unschedules their job.
        """
        async with get_db() as session:
            user = await crud.get_user_by_telegram_id(session, telegram_id)
            if not user or not user.is_active or user.is_banned:
                self.remove_user_job(telegram_id)
                return

            state = await crud.get_or_create_state(session, user.id)
            job_id = self.get_job_id(telegram_id)

            if state.is_sending:
                interval_minutes = max(1, state.interval_minutes)
                jitter_secs = random.randint(0, config.ROUND_JITTER_SECONDS)
                first_run = datetime.now(pytz.timezone(state.timezone or config.DEFAULT_TIMEZONE)) + timedelta(seconds=jitter_secs)

                self.scheduler.add_job(
                    func=self.execute_user_broadcast,
                    trigger="interval",
                    minutes=interval_minutes,
                    id=job_id,
                    args=[telegram_id],
                    replace_existing=True,
                    next_run_time=first_run,
                )
                logger.info(
                    f"[SCHEDULER] Scheduled broadcast job for user {telegram_id} "
                    f"every {interval_minutes}m (Next run: {first_run.strftime('%H:%M:%S')})"
                )
            else:
                self.remove_user_job(telegram_id)

    def remove_user_job(self, telegram_id: int):
        """Removes user's broadcast job if present."""
        job_id = self.get_job_id(telegram_id)
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info(f"[SCHEDULER] Removed broadcast job for user {telegram_id}")

    async def execute_user_broadcast(self, telegram_id: int, manual: bool = False, reply_cb: Optional[Callable] = None):
        """
        Performs one full broadcast round to all target groups configured by the user.
        """
        logger.info(f"[BROADCAST] Starting round for user {telegram_id} (manual={manual})...")

        # 1. Fetch user data & client
        client = session_manager.get_client(telegram_id)
        if not client or not client.is_connected():
            # Try to start session
            client = await session_manager.start_user_session(telegram_id)
            if not client:
                msg = "⚠️ Userbot sessiyasi faol emas yoki ulanib bo'lmadi."
                logger.error(f"[BROADCAST] {msg} (User {telegram_id})")
                if reply_cb:
                    await reply_cb(msg)
                return

        async with get_db() as session:
            user = await crud.get_user_by_telegram_id(session, telegram_id)
            if not user or not user.is_active or user.is_banned:
                logger.warning(f"[BROADCAST] User {telegram_id} is inactive or banned. Aborting.")
                return

            state = await crud.get_or_create_state(session, user.id)

            # Check operating window if not manual
            if not manual and not self.is_within_operating_hours(state.start_time, state.end_time, state.timezone):
                logger.info(
                    f"[BROADCAST] User {telegram_id} is outside operating hours "
                    f"({state.start_time} - {state.end_time}). Skipping round."
                )
                return

            groups = await crud.get_user_groups(session, user.id)
            if not groups:
                msg = "⚠️ Target guruhlar ro'yxati bo'sh. Xabar yuborish uchun `/add_group` buyrug'idan foydalaning."
                logger.warning(f"[BROADCAST] {msg} (User {telegram_id})")
                if reply_cb:
                    await reply_cb(msg)
                return

            messages = await crud.get_user_messages(session, user.id)
            if not messages:
                msg = "⚠️ Xabarlar shablonlari mavjud emas. Xabar qo'shish uchun `/add_message` buyrug'idan foydalaning."
                logger.warning(f"[BROADCAST] {msg} (User {telegram_id})")
                if reply_cb:
                    await reply_cb(msg)
                return

            # Rotate message
            msg_count = len(messages)
            current_msg_idx = state.current_message_index % msg_count
            current_message = messages[current_msg_idx].text

            # Update next message index
            state.current_message_index = (current_msg_idx + 1) % msg_count

            # Prepare optional sticker
            sticker_doc = None
            if state.send_sticker:
                active_sticker = sticker_helper.get_user_active_sticker(
                    telegram_id=telegram_id,
                    current_set_name=state.sticker_set_name,
                    sticker_index=state.current_sticker_index,
                )
                if active_sticker:
                    try:
                        sticker_doc = sticker_helper.prepare_input_document(active_sticker)
                    except Exception as s_err:
                        logger.warning(f"Could not prepare sticker for user {telegram_id}: {s_err}")
                # Increment sticker index
                state.current_sticker_index += 1

            await session.commit()

        sticker_txt = "Yoqilgan" if state.send_sticker else "O'chirilgan"
        if reply_cb:
            await reply_cb(
                f"🚀 **Xabar yuborish boshlandi!**\n"
                f"👥 Guruhlar soni: `{len(groups)}` ta\n"
                f"📝 Xabar shabloni: `#{current_msg_idx + 1}`\n"
                f"🎨 Stiker: {sticker_txt}"
            )

        success_count = 0
        fail_count = 0

        for grp in groups:
            ok = await send_to_group(
                client=client,
                group_identifier=grp.group_identifier,
                message_text=current_message,
                sticker_doc=sticker_doc,
                send_sticker=state.send_sticker,
                min_delay=config.MIN_DELAY_BETWEEN_GROUPS,
                max_delay=config.MAX_DELAY_BETWEEN_GROUPS,
            )
            if ok:
                success_count += 1
            else:
                fail_count += 1

        summary = (
            f"✅ **Yuborish yakunlandi!**\n"
            f"🎯 Muvaffaqiyatli: `{success_count}` ta\n"
            f"⚠️ Yetib bormadi: `{fail_count}` ta\n"
            f"📊 Jami guruhlar: `{len(groups)}` ta"
        )
        logger.info(f"[BROADCAST] Round completed for user {telegram_id}: {success_count} ok, {fail_count} failed")

        if reply_cb:
            await reply_cb(summary)

    async def trigger_user_send_now(self, telegram_id: int, reply_cb: Optional[Callable] = None):
        """Immediately executes a broadcast round triggered by user."""
        asyncio.create_task(
            self.execute_user_broadcast(telegram_id=telegram_id, manual=True, reply_cb=reply_cb)
        )


# Global MultiUserScheduler instance
scheduler_manager = MultiUserScheduler()
