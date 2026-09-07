"""
Commands handler module for Multi-User Telegram Userbot SaaS.
Listens to and polls incoming messages in each user's own 'Saved Messages' chat,
supporting both real-time event updates and background synchronization polling.
Updates database state directly and synchronizes with the scheduler.
"""

import asyncio
import html as html_lib
import re
from datetime import datetime
from typing import Dict, Optional, Set
from loguru import logger
from telethon import TelegramClient, events
from telethon.extensions import html

import config
from core import sticker_helper
from core.scheduler import scheduler_manager
from db.database import get_db
from db import crud

HELP_TEXT = """
🤖 **USERBOT BOSHQARUV PANELI (SAVED MESSAGES)**

⚡ **Jadval Boshqaruvi (Scheduler):**
• `/start_sending` — Avtomatik yuborishni ishga tushirish
• `/stop_sending` — Avtomatik yuborishni pauzaga qo'yish
• `/status` — Userbotning joriy holatini ko'rish
• `/send_now` — Barcha guruhlarga zudlik bilan bitta xabar yuborish

👥 **Guruhlar Boshqaruvi:**
• `/add_group <username/id>` — Guruh qo'shish (masalan: `/add_group @mening_guruhim`)
• `/remove_group <username/id>` — Guruhni ro'yxatdan o'chirish
• `/list_groups` — Barcha target guruhlarni ko'rish

📝 **Xabarlar Boshqaruvi:**
• `/add_message <matn>` — Yangi xabar shabloni qo'shish (Premium emojilarni qo'llab-quvvatlaydi)
• `/list_messages` — Barcha saqlangan xabarlarni ko'rish
• `/remove_message <raqam>` — Xabarni raqami bo'yicha o'chirish
• `/set_message <raqam>` — Navbatdagi yuboriladigan xabarni belgilash

🎨 **Stikerlar Boshqaruvi (Premium):**
• `/sticker_on` — Xabardan so'ng stiker yuborishni yoqish
• `/sticker_off` — Stiker yuborishni o'chirish
• `/list_stickers` — Mavjud stiker to'plamlarini ko'rish
• `/set_sticker_set <nomi>` — Faol stiker to'plamini almashtirish
• `/resync_stickers` — Stikerlarni Telegram serveridan qayta yuklash

⏱️ **Vaqt va Oraliq Sozlamalari:**
• `/set_interval <daqiqa>` — Yuborish oralig'i (masalan: `/set_interval 30`)
• `/set_window <HH:MM> <HH:MM>` — Ish vaqti oralig'i (masalan: `/set_window 09:00 21:00`)

ℹ️ **Yordam:**
• `/help` — Ushbu buyruqlar ro'yxatini ko'rish
"""

# Track processed message IDs per user to prevent duplicate executions
user_processed_ids: Dict[int, Set[int]] = {}
user_poller_tasks: Dict[int, asyncio.Task] = {}


async def process_user_command(client: TelegramClient, telegram_id: int, message):
    """Processes a single command message and replies back to Saved Messages."""
    raw_text = (message.text or "").strip()
    if not raw_text.startswith("/"):
        return

    parts = raw_text.split(maxsplit=1)
    command_word = parts[0].lower().split("@")[0]
    args = parts[1].strip() if len(parts) > 1 else ""

    logger.info(f"[USER CMD] User {telegram_id} | {command_word} | MsgID: {message.id}")

    async def reply(text: str):
        try:
            sent_msg = await client.send_message("me", text, reply_to=message.id)
            if telegram_id in user_processed_ids:
                user_processed_ids[telegram_id].add(sent_msg.id)
        except Exception as e:
            logger.error(f"Failed to reply to Saved Messages for user {telegram_id}: {e}")

    async with get_db() as session:
        user = await crud.get_user_by_telegram_id(session, telegram_id)
        if not user or not user.is_active or user.is_banned:
            await reply("⚠️ Hisobingiz faol emas yoki ma'muriyat tomonidan bloklangan.")
            return

        state = await crud.get_or_create_state(session, user.id)

        # 1. Scheduler Control
        if command_word == "/start_sending":
            state.is_sending = True
            await session.commit()
            await scheduler_manager.sync_user_job(telegram_id)
            await reply("✅ **Avto-yuboruvchi jadval ishga tushirildi!**\nNavbatdagi yuborish belgilangan oraliq bo'yicha amalga oshiriladi.")

        elif command_word == "/stop_sending":
            state.is_sending = False
            await session.commit()
            await scheduler_manager.sync_user_job(telegram_id)
            await reply("⏸️ **Avto-yuboruvchi jadval to'xtatildi (Paused).**\nQayta ishga tushirish: `/start_sending`")

        elif command_word in ("/status", "/hello"):
            groups = await crud.get_user_groups(session, user.id)
            messages = await crud.get_user_messages(session, user.id)
            is_open = scheduler_manager.is_within_operating_hours(state.start_time, state.end_time, state.timezone)
            next_run = scheduler_manager.get_next_run_time(telegram_id)

            sched_status = "🟢 **Faol (Ishlamoqda)**" if state.is_sending else "⏸️ **To'xtatilgan (Pauza)**"
            window_status = "🟢 Oyna ichida (Aktiv)" if is_open else "🔴 Oyna tashqarisida (Ish vaqti emas)"
            next_run_str = next_run.strftime("%Y-%m-%d %H:%M:%S") if (next_run and state.is_sending) else "Rejalashtirilmagan"
            current_msg_num = (state.current_message_index % len(messages) + 1) if messages else 0

            sticker_status = "❌ O'chirilgan (OFF)"
            if state.send_sticker:
                stk_set = state.sticker_set_name or "Birlamchi"
                sticker_status = f"✅ Yoqilgan (ON) [To'plam: `{stk_set}`, Indeks: #{state.current_sticker_index + 1}]"

            status_msg = (
                f"📊 **USERBOT JORIY HOLATI**\n"
                f"────────────────────────────\n"
                f"• **Holat:** {sched_status}\n"
                f"• **Faol Vaqt Oralig'i:** `{state.start_time}` — `{state.end_time}` ({state.timezone})\n"
                f"• **Oyna Holati:** {window_status}\n"
                f"• **Oraliq (Interval):** `{state.interval_minutes}` daqiqa\n"
                f"• **Keyingi Yuborish:** `{next_run_str}`\n"
                f"• **Target Guruhlar:** `{len(groups)}` ta\n"
                f"• **Xabarlar Shablonlari:** `{len(messages)}` ta (Navbatdagi: `#{current_msg_num}`)\n"
                f"• **Stiker Yuborish:** {sticker_status}\n"
                f"• **Guruhlararo Kechikish:** `{config.MIN_DELAY_BETWEEN_GROUPS}s - {config.MAX_DELAY_BETWEEN_GROUPS}s`\n"
                f"────────────────────────────\n"
                f"💡 *Barcha buyruqlar: `/help`*"
            )
            await reply(status_msg)

        elif command_word == "/send_now":
            await reply("⚡ **Zudlik bilan yuborish buyrug'i qabul qilindi...**")
            await scheduler_manager.trigger_user_send_now(telegram_id, reply_cb=reply)

        # 2. Group Management
        elif command_word == "/add_group":
            if not args:
                await reply("⚠️ **Foydalanish:** `/add_group <username yoki chat_id>`\nMasalan: `/add_group @my_target_group`")
                return
            ok, msg_text, total = await crud.add_group(session, user.id, args)
            await session.commit()
            prefix = "✅" if ok else "⚠️"
            await reply(f"{prefix} {msg_text}\n📊 Jami guruhlar: `{total}` ta")

        elif command_word == "/remove_group":
            if not args:
                await reply("⚠️ **Foydalanish:** `/remove_group <username yoki chat_id>`")
                return
            ok, msg_text, total = await crud.remove_group(session, user.id, args)
            await session.commit()
            prefix = "🗑️" if ok else "⚠️"
            await reply(f"{prefix} {msg_text}\n📊 Qolgan guruhlar: `{total}` ta")

        elif command_word == "/list_groups":
            groups = await crud.get_user_groups(session, user.id)
            if not groups:
                await reply("📭 Target guruhlar ro'yxati bo'sh.\nGuruh qo'shish: `/add_group @username`")
                return
            lines = [f"📋 **Target Guruhlar** (Jami: {len(groups)} ta):\n"]
            for idx, g in enumerate(groups, 1):
                title_part = f" — {g.title}" if g.title else ""
                lines.append(f"{idx}. `{g.group_identifier}`{title_part}")
            lines.append("\n💡 *Guruh o'chirish:* `/remove_group <username/id>`")
            await reply("\n".join(lines))

        # 3. Message Management (with full Telegram Premium custom emoji support)
        elif command_word == "/add_message":
            target_msg_obj = message
            clean_html = ""

            # Check if command is replying to another message
            reply_to = await message.get_reply_message()
            if reply_to and reply_to.message:
                target_msg_obj = reply_to
                clean_html = html.unparse(target_msg_obj.message, target_msg_obj.entities).strip()
            else:
                full_html = html.unparse(message.message, message.entities)
                clean_html = re.sub(r"^\s*/add_message(?:\s+|\n+)", "", full_html, count=1).strip()

            if not clean_html:
                await reply(
                    "⚠️ **Foydalanish:** `/add_message <xabar matni>`\n"
                    "yoki biror xabarga javoban (reply) `/add_message` deb yuboring.\n"
                    "Telegram Premium emojilar, qalin va kursiv shriftlar to'liq saqlanadi."
                )
                return

            custom_cnt = 0
            if target_msg_obj.entities:
                custom_cnt = sum(1 for e in target_msg_obj.entities if hasattr(e, "document_id"))

            ok, msg_text, total = await crud.add_message(session, user.id, clean_html)
            await session.commit()

            emoji_note = f"\n💎 **Telegram Premium emojilar:** `{custom_cnt}` ta aniqlandi va saqlandi" if custom_cnt > 0 else ""
            await reply(f"✅ **{msg_text}**{emoji_note}\n📊 Jami xabarlar: `{total}` ta")

        elif command_word == "/list_messages":
            messages = await crud.get_user_messages(session, user.id)
            if not messages:
                await reply("📭 Xabarlar ro'yxati bo'sh.\nXabar qo'shish: `/add_message <matn>`")
                return

            lines = [f"📝 **Aylanma Xabarlar Shablonlari** (Jami: {len(messages)} ta):\n"]
            for idx, m in enumerate(messages, 1):
                clean_preview = re.sub(r"<[^>]+>", "", m.text).replace("\n", " ")
                if len(clean_preview) > 60:
                    clean_preview = clean_preview[:60] + "..."
                active_mark = " 👈 [Navbatdagi]" if idx == (state.current_message_index % len(messages) + 1) else ""
                lines.append(f"**#{idx}**{active_mark}: {clean_preview}")

            lines.append("\n💡 *O'chirish:* `/remove_message <raqam>`")
            lines.append("💡 *Navbatni belgilash:* `/set_message <raqam>`")
            await reply("\n".join(lines))

        elif command_word == "/remove_message":
            if not args or not args.isdigit():
                await reply("⚠️ **Foydalanish:** `/remove_message <raqam>`\nMasalan: `/remove_message 1`")
                return
            ok, msg_text, total = await crud.remove_message_by_index(session, user.id, int(args))
            await session.commit()
            prefix = "🗑️" if ok else "⚠️"
            await reply(f"{prefix} {msg_text}\n📊 Qolgan xabarlar: `{total}` ta")

        elif command_word == "/set_message":
            if not args or not args.isdigit():
                await reply("⚠️ **Foydalanish:** `/set_message <raqam>`")
                return
            messages = await crud.get_user_messages(session, user.id)
            idx = int(args)
            if idx < 1 or idx > len(messages):
                await reply(f"⚠️ Noto'g'ri raqam. 1 dan {len(messages)} gacha son kiriting.")
                return
            state.current_message_index = idx - 1
            await session.commit()
            await reply(f"✅ Navbatdagi yuboriladigan xabar **#{idx}** qilib belgilandi.")

        # 4. Sticker Management
        elif command_word == "/sticker_on":
            state.send_sticker = True
            await session.commit()
            await reply("✅ **Stiker yuborish yoqildi!**\nHar bir xabardan so'ng mos stiker yuboriladi.")

        elif command_word == "/sticker_off":
            state.send_sticker = False
            await session.commit()
            await reply("❌ **Stiker yuborish o'chirildi.**\nFaqat matnli xabarlar yuboriladi.")

        elif command_word == "/list_stickers":
            sets = sticker_helper.get_user_available_sets(telegram_id)
            if not sets:
                await reply(
                    "⚠️ Stiker to'plamlari topilmadi.\n"
                    "Telegram akkauntingizdagi stikerlarni yuklab olish uchun:\n"
                    "`/resync_stickers` buyrug'ini yuboring."
                )
                return
            lines = [f"🎨 **Yuklangan Stiker To'plamlari** (Jami: {len(sets)} ta):\n"]
            current_active = state.sticker_set_name or sets[0]["short_name"]
            for s in sets:
                mark = " 👈 **[Faol]**" if s["short_name"] == current_active else ""
                lines.append(f"• `{s['short_name']}` — \"{s['title']}\" ({s['count']} ta stiker){mark}")
            lines.append("\n💡 *To'plamni almashtirish:* `/set_sticker_set <nomi>`")
            await reply("\n".join(lines))

        elif command_word == "/set_sticker_set":
            if not args:
                await reply("⚠️ **Foydalanish:** `/set_sticker_set <to'plam_nomi>`\nRo'yxat uchun: `/list_stickers`")
                return
            catalog = sticker_helper.load_user_stickers(telegram_id)
            if args not in catalog:
                await reply(f"⚠️ `{args}` nomli to'plam topilmadi. Avval `/list_stickers` orqali tekshiring.")
                return
            state.sticker_set_name = args
            state.current_sticker_index = 0
            await session.commit()
            await reply(f"✅ Faol stiker to'plami o'zgartirildi: `{args}`")

        elif command_word in ("/resync_stickers", "/sync_stickers"):
            await reply("🔄 **Telegram serverlaridan stikerlar sinxronizatsiya qilinmoqda...**\nIltimos, bir oz kuting.")
            ok, res_text, sets_cnt, stk_cnt = await sticker_helper.resync_user_stickers(
                client=client,
                telegram_id=telegram_id,
                target_set=args if args else None,
            )
            if ok:
                await reply(
                    f"✅ **Stikerlar muvaffaqiyatli sinxronlandi!**\n\n"
                    f"📦 To'plamlar: `{sets_cnt}` ta\n"
                    f"🎨 Stikerlar: `{stk_cnt}` ta\n\n"
                    f"• Ro'yxat: `/list_stickers`\n"
                    f"• Yoqish: `/sticker_on`"
                )
            else:
                await reply(f"⚠️ {res_text}")

        # 5. Timing Settings
        elif command_word == "/set_interval":
            try:
                val = int(args)
                if val < 1:
                    raise ValueError
                state.interval_minutes = val
                await session.commit()
                await scheduler_manager.sync_user_job(telegram_id)
                await reply(f"⏱️ **Yuborish oralig'i `{val}` daqiqaga o'zgartirildi!**")
            except (ValueError, IndexError):
                await reply("⚠️ **Foydalanish:** `/set_interval <daqiqa>`\nMasalan: `/set_interval 30`")

        elif command_word == "/set_window":
            parts_window = args.split()
            if len(parts_window) != 2:
                await reply("⚠️ **Foydalanish:** `/set_window <boshlanish> <tugash>`\nMasalan: `/set_window 09:00 21:00`")
                return
            s_str, e_str = parts_window[0].strip(), parts_window[1].strip()
            try:
                datetime.strptime(s_str, "%H:%M")
                datetime.strptime(e_str, "%H:%M")
                state.start_time = s_str
                state.end_time = e_str
                await session.commit()
                await reply(f"🕒 **Faol ish vaqti oralig'i belgilandi:** `{s_str}` dan `{e_str}` gacha ({state.timezone})")
            except ValueError:
                await reply("⚠️ Noto'g'ri vaqt formati. `HH:MM` ko'rinishida kiriting (masalan: `09:00 21:00`).")

        # 6. Help Menu
        elif command_word == "/help":
            await reply(HELP_TEXT)

        else:
            await reply(f"⚠️ Noma'lum buyruq: `{command_word}`\nBarcha buyruqlar ro'yxati: `/help`")


async def poll_user_saved_messages(client: TelegramClient, telegram_id: int):
    """
    Continuous background poller for Saved Messages commands.
    Ensures commands sent from Telegram Desktop/Mobile are executed reliably.
    """
    logger.info(f"Started Saved Messages poller for user {telegram_id}.")
    if telegram_id not in user_processed_ids:
        user_processed_ids[telegram_id] = set()

    # Preload recent messages to prevent running old history
    try:
        init_msgs = await client.get_messages("me", limit=10)
        for m in init_msgs:
            user_processed_ids[telegram_id].add(m.id)
    except Exception as e:
        logger.warning(f"Failed to fetch initial Saved Messages for user {telegram_id}: {e}")

    while True:
        try:
            recent_msgs = await client.get_messages("me", limit=10)
            for msg in reversed(recent_msgs):
                if msg.id not in user_processed_ids[telegram_id]:
                    user_processed_ids[telegram_id].add(msg.id)
                    text = (msg.text or "").strip()
                    if text.startswith("/"):
                        await process_user_command(client, telegram_id, msg)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in Saved Messages poller (User {telegram_id}): {e}")

        await asyncio.sleep(1.5)


async def register_saved_message_handlers(client: TelegramClient, telegram_id: int):
    """
    Registers the NewMessage event handler and launches background poller.
    """
    if telegram_id not in user_processed_ids:
        user_processed_ids[telegram_id] = set()

    @client.on(events.NewMessage(chats="me"))
    async def on_saved_message(event: events.NewMessage.Event):
        if event.id in user_processed_ids[telegram_id]:
            return
        user_processed_ids[telegram_id].add(event.id)
        if (event.raw_text or "").strip().startswith("/"):
            await process_user_command(client, telegram_id, event.message)

    # Cancel existing poller task if any
    old_task = user_poller_tasks.get(telegram_id)
    if old_task and not old_task.done():
        old_task.cancel()

    user_poller_tasks[telegram_id] = asyncio.create_task(
        poll_user_saved_messages(client, telegram_id)
    )
    logger.info(f"Registered Saved Messages handlers & launched poller for user {telegram_id}")
