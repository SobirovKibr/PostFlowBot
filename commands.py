"""
Commands handler module for Telegram Userbot.
Listens to and polls incoming messages in the user's own 'Saved Messages' chat,
supporting both real-time event updates and high-reliability synchronization polling.
"""

import asyncio
from datetime import datetime
from typing import Set
from telethon import TelegramClient, events

from groups_manager import add_group, format_groups_list, load_groups, remove_group
from logger import logger
from messages_manager import (
    add_message,
    add_message_from_telegram,
    format_messages_list,
    load_messages,
    remove_message,
)
from scheduler import scheduler_wakeup_event, trigger_manual_send
from state_manager import state
import stickers_manager

HELP_TEXT = """
🤖 **TELEGRAM USERBOT BOSHQARUV PANELI (SAVED MESSAGES)**

⚡ **Jadval Boshqaruvi (Scheduler):**
• `/start_sending` — Avtomatik yuborishni boshlash
• `/stop_sending` — Avtomatik yuborishni pauzaga qo'yish
• `/status` — Botning joriy holatini ko'rish
• `/send_now` — Barcha guruhlarga zudlik bilan hozir xabar yuborish

👥 **Guruhlar Boshqaruvi:**
• `/add_group <username/id>` — Guruh qo'shish (masalan: `/add_group @mygroup`)
• `/remove_group <username/id>` — Guruhni ro'yxatdan o'chirish
• `/list_groups` — Barcha saqlangan target guruhlarni ko'rish

📝 **Xabarlar Boshqaruvi:**
• `/add_message <matn>` — Yangi aylanma xabar qo'shish
• `/list_messages` — Barcha xabarlarni raqami bilan ko'rish
• `/remove_message <raqam>` — Xabarni raqami bo'yicha o'chirish
• `/set_message <raqam>` — Navbatdagi yuboriladigan xabarni belgilash

🎨 **Stikerlar Boshqaruvi (Premium):**
• `/sticker_on` — Xabardan so'ng stiker yuborishni yoqish
• `/sticker_off` — Stiker yuborishni o'chirish
• `/list_stickers` — `stickers.json` dan yuklangan to'plamlarni ko'rish
• `/set_sticker_set <nomi>` — Boshqa stiker to'plamiga o'tish
• `/resync_stickers` — Akkauntdagi stikerlarni Telegramdan qayta yuklash (resync)

⏱️ **Vaqt va Oraliq Sozlamalari:**
• `/set_interval <daqiqa>` — Yuborish oralig'ini o'zgartirish (masalan: `/set_interval 30`)
• `/set_window <HH:MM> <HH:MM>` — Ish vaqti oralig'ini belgilash (masalan: `/set_window 09:00 21:00`)
• `/set_delay <soniya>` — Guruhlararo kutilma vaqtini belgilash (masalan: `/set_delay 3` yoki `/set_delay 3 5`)

ℹ️ **Yordam:**
• `/help` — Ushbu buyruqlar ro'yxatini chiqarish
"""

# Track processed message IDs to avoid executing commands twice
processed_message_ids: Set[int] = set()


async def process_command(client: TelegramClient, message):
    """Processes a single command message and replies back to Saved Messages."""
    raw_text = (message.text or "").strip()
    if not raw_text.startswith("/"):
        return

    parts = raw_text.split(maxsplit=1)
    command_word = parts[0].lower().split("@")[0]
    args = parts[1].strip() if len(parts) > 1 else ""

    logger.info(f"[COMMAND EXEC] {command_word} | MsgID: {message.id} | Args: {args[:50]}")

    async def reply(text: str):
        try:
            sent_msg = await client.send_message("me", text, reply_to=message.id)
            processed_message_ids.add(sent_msg.id)
        except Exception as e:
            logger.error(f"Failed to reply to Saved Messages: {e}")

    # 1. Scheduler Control
    if command_word == "/start_sending":
        state.is_scheduler_running = True
        scheduler_wakeup_event.set()
        await reply("✅ **Avto-yuboruvchi jadval ishga tushirildi!**\nNavbatdagi yuborish jadval bo'yicha amalga oshiriladi.")

    elif command_word == "/stop_sending":
        state.is_scheduler_running = False
        await reply("⏸️ **Avto-yuboruvchi jadval to'xtatildi (Paused).**\nQayta yoqish uchun: `/start_sending`")

    elif command_word in ("/status", "/hello"):
        groups = load_groups()
        messages = load_messages()
        is_open, seconds_until = state.is_within_operating_hours()

        sched_status = "🟢 **Faol (Running)**" if state.is_scheduler_running else "⏸️ **To'xtatilgan (Paused)**"
        
        if is_open:
            window_status = "🟢 Oyna ichida (Aktiv)"
        else:
            h = seconds_until // 3600
            m = (seconds_until % 3600) // 60
            window_status = f"🔴 Oyna tashqarisida ({h}s {m}d dan so'ng boshlanadi)"

        next_run_str = "Rejalashtirilmagan"
        if state.next_run_timestamp and state.is_scheduler_running:
            next_dt = datetime.fromtimestamp(state.next_run_timestamp, tz=state.timezone)
            next_run_str = next_dt.strftime("%Y-%m-%d %H:%M:%S")

        current_msg_num = (state.message_index % len(messages) + 1) if messages else 0

        sticker_status = "❌ O'chirilgan (OFF)"
        if state.sticker_enabled:
            sticker_set_name = state.current_sticker_set or "Birlamchi to'plam"
            sticker_status = f"✅ Yoqilgan (ON) [To'plam: `{sticker_set_name}`, Indeks: #{state.sticker_index + 1}]"

        status_msg = (
            f"📊 **USERBOT JORIY HOLATI**\n"
            f"────────────────────────────\n"
            f"• **Holat:** {sched_status}\n"
            f"• **Faol Vaqt Oralig'i:** `{state.start_time_str}` — `{state.end_time_str}` ({state.timezone_str})\n"
            f"• **Oyna Holati:** {window_status}\n"
            f"• **Oraliq (Interval):** `{state.interval_minutes}` daqiqa (±{state._data.get('round_jitter_seconds', 60)}s)\n"
            f"• **Keyingi Yuborish:** `{next_run_str}`\n"
            f"• **Target Guruhlar:** `{len(groups)}` ta\n"
            f"• **Xabarlar Shablonlari:** `{len(messages)}` ta (Navbatdagi: `#{current_msg_num}`)\n"
            f"• **Stiker Yuborish:** {sticker_status}\n"
            f"• **Guruhlar Oralig'i Kechikish:** `{state._data.get('min_delay_between_groups', 25)}s - {state._data.get('max_delay_between_groups', 55)}s`\n"
            f"────────────────────────────\n"
            f"💡 *Barcha buyruqlar ro'yxati: `/help`*"
        )
        await reply(status_msg)

    # 2. Manual Send
    elif command_word == "/send_now":
        async def reply_callback(msg_text: str):
            await reply(msg_text)

        asyncio.create_task(trigger_manual_send(client, reply_callback))

    # 3. Group Management
    elif command_word == "/add_group":
        if not args:
            await reply("⚠️ **Foydalanish:** `/add_group <username yoki chat_id>`\nMasalan: `/add_group @my_group`")
            return
        ok, msg, total = add_group(args)
        prefix = "✅" if ok else "⚠️"
        await reply(f"{prefix} {msg}\n📊 Jami guruhlar soni: `{total}` ta")

    elif command_word == "/remove_group":
        if not args:
            await reply("⚠️ **Foydalanish:** `/remove_group <username yoki chat_id>`")
            return
        ok, msg, total = remove_group(args)
        prefix = "🗑️" if ok else "⚠️"
        await reply(f"{prefix} {msg}\n📊 Qolgan guruhlar soni: `{total}` ta")

    elif command_word == "/list_groups":
        await reply(format_groups_list())

    # 4. Message Management
    elif command_word == "/add_message":
        if not args:
            await reply("⚠️ **Foydalanish:** `/add_message <xabar matni>`\nXabaringiz bir necha qatordan iborat bo'lishi va Telegram Premium emojilarni o'z ichiga olishi mumkin.")
            return
        ok, msg, total, custom_cnt = add_message_from_telegram(message)
        if ok:
            emoji_info = f"\n💎 **Telegram Premium emojilar:** `{custom_cnt}` ta aniqlandi va saqlandi" if custom_cnt > 0 else ""
            await reply(f"✅ **{msg}**{emoji_info}\n📊 Jami xabarlar soni: `{total}` ta")
        else:
            await reply(f"⚠️ {msg}")

    elif command_word == "/list_messages":
        await reply(format_messages_list())

    elif command_word == "/remove_message":
        if not args or not args.isdigit():
            await reply("⚠️ **Foydalanish:** `/remove_message <raqam>`\nMasalan: `/remove_message 2`")
            return
        idx = int(args)
        ok, msg, total = remove_message(idx)
        prefix = "🗑️" if ok else "⚠️"
        await reply(f"{prefix} {msg}\n📊 Qolgan xabarlar soni: `{total}` ta")

    elif command_word == "/set_message":
        if not args or not args.isdigit():
            await reply("⚠️ **Foydalanish:** `/set_message <raqam>`\nMasalan: `/set_message 1`")
            return
        idx = int(args)
        messages = load_messages()
        if idx < 1 or idx > len(messages):
            await reply(f"⚠️ Noto'g'ri indeks. 1 dan {len(messages)} gacha bo'lgan son kiriting.")
            return
        state.message_index = idx - 1
        preview = messages[idx - 1][:60].replace("\n", " ") + "..."
        await reply(f"✅ Navbatdagi yuboriladigan xabar **#{idx}** qilib belgilandi:\n*\"{preview}\"*")

    # 5. Sticker Control
    elif command_word == "/sticker_on":
        state.sticker_enabled = True
        await reply("✅ **Stiker yuborish yoqildi!**\nHar bir xabardan so'ng avtomatik stiker ham yuboriladi.")

    elif command_word == "/sticker_off":
        state.sticker_enabled = False
        await reply("❌ **Stiker yuborish o'chirildi.**\nEndi faqat matnli xabarlar yuboriladi.")

    elif command_word == "/list_stickers":
        sets = stickers_manager.get_available_sticker_sets()
        if not sets:
            await reply(
                "⚠️ `stickers.json` faylida stiker to'plamlari topilmadi.\n\n"
                "Avval terminalda quyidagi buyruqni ishga tushiring:\n"
                "`python3 get_stickers.py`"
            )
            return

        text = f"🎨 **Yuklangan Stiker To'plamlari** (Jami: {len(sets)} ta):\n\n"
        current_active = state.current_sticker_set or sets[0]["short_name"]

        for s in sets:
            active_mark = " 👈 **[Faol]**" if s["short_name"] == current_active else ""
            anim_info = " (Animatsiyali)" if s["is_animated"] else (" (Video)" if s["is_video"] else "")
            text += f"• `{s['short_name']}` — \"{s['title']}\" ({s['count']} ta stiker){anim_info}{active_mark}\n"

        text += "\n💡 *To'plamni almashtirish uchun:* `/set_sticker_set <to'plam_nomi>`"
        await reply(text)

    elif command_word == "/set_sticker_set":
        if not args:
            await reply("⚠️ **Foydalanish:** `/set_sticker_set <nomi>`\nTo'plamlar ro'yxatini ko'rish uchun: `/list_stickers`")
            return

        catalog = stickers_manager.load_stickers_catalog()
        if args not in catalog:
            await reply(f"⚠️ `{args}` nomli stiker to'plami topilmadi. `/list_stickers` orqali tekshiring.")
            return

        state.current_sticker_set = args
        state.sticker_index = 0
        count = len(catalog[args].get("stickers", []))
        await reply(f"✅ **Faol stiker to'plami o'zgartirildi:** `{args}` ({count} ta stiker).")

    elif command_word in ("/resync_stickers", "/sync_stickers"):
        target_name = args if args else None
        target_display = f"'{target_name}'" if target_name else "barcha stiker to'plamlari"
        await reply(f"🔄 **Telegram serverlaridan {target_display} sinxronizatsiya qilinmoqda...**\nIltimos, bir oz kuting.")

        ok, msg, sets_cnt, stickers_cnt = await stickers_manager.resync_stickers_from_telegram(
            client=client,
            target_set=target_name
        )

        if ok:
            await reply(
                f"✅ **Stikerlar muvaffaqiyatli sinxronizatsiya qilindi!**\n\n"
                f"📦 Jami to'plamlar: `{sets_cnt}` ta\n"
                f"🎨 Jami stikerlar: `{stickers_cnt}` ta\n\n"
                f"• Ro'yxatni ko'rish: `/list_stickers`\n"
                f"• To'plamni tanlash: `/set_sticker_set <nomi>`\n"
                f"• Stikerlarni yoqish: `/sticker_on`"
            )
        else:
            await reply(f"⚠️ {msg}")

    # 6. Timing & Interval Control
    elif command_word == "/set_interval":
        try:
            val = float(args)
            if val <= 0:
                raise ValueError
            state.interval_minutes = val
            scheduler_wakeup_event.set()
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
            state.set_time_window(s_str, e_str)
            scheduler_wakeup_event.set()
            await reply(f"🕒 **Faol ish vaqti oralig'i belgilandi:** `{s_str}` dan `{e_str}` gacha ({state.timezone_str})")
        except ValueError:
            await reply("⚠️ Noto'g'ri vaqt formati. Vaqtni `HH:MM` shaklida kiriting (masalan: `09:00 21:00`).")

    elif command_word == "/set_delay":
        parts_delay = args.split()
        try:
            if len(parts_delay) == 1:
                min_d = int(parts_delay[0])
                max_d = min_d + 1
            elif len(parts_delay) >= 2:
                min_d = int(parts_delay[0])
                max_d = int(parts_delay[1])
            else:
                raise ValueError
            if min_d < 1 or max_d < min_d:
                raise ValueError
            state.set_delays(min_d, max_d)
            await reply(f"⏳ **Guruhlararo kutilma vaqti `{min_d}s - {max_d}s` qilib belgilandi!**")
        except ValueError:
            await reply("⚠️ **Foydalanish:** `/set_delay <soniya>` yoki `/set_delay <min> <max>`\nMasalan: `/set_delay 3` yoki `/set_delay 3 5`")

    # 7. Help Menu
    elif command_word == "/help":
        await reply(HELP_TEXT)

    else:
        await reply(f"⚠️ Noma'lum buyruq: `{command_word}`\nBarcha buyruqlar ro'yxatini ko'rish uchun: `/help`")


async def poll_saved_messages(client: TelegramClient):
    """
    High-reliability background poller for Saved Messages commands.
    Ensures that commands sent from Telegram Desktop, Web, or Mobile
    are promptly processed even if MTProto does not push self-messages.
    """
    logger.info("Saved Messages command poller started.")

    # Initialize last_seen_id with existing messages
    try:
        initial_msgs = await client.get_messages("me", limit=10)
        for m in initial_msgs:
            processed_message_ids.add(m.id)
    except Exception as e:
        logger.warning(f"Error fetching initial Saved Messages: {e}")

    while True:
        try:
            # Poll for the latest messages in Saved Messages
            recent_msgs = await client.get_messages("me", limit=10)
            # Process in chronological order (oldest first)
            for msg in reversed(recent_msgs):
                if msg.id not in processed_message_ids:
                    processed_message_ids.add(msg.id)
                    text = (msg.text or "").strip()
                    if text.startswith("/"):
                        await process_command(client, msg)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in Saved Messages poller: {e}")

        await asyncio.sleep(1.5)


def register_command_handlers(client: TelegramClient, my_id: int):
    """Registers the NewMessage event handler as an immediate listener."""

    @client.on(events.NewMessage(chats="me"))
    async def handle_event_message(event: events.NewMessage.Event):
        if event.id in processed_message_ids:
            return
        processed_message_ids.add(event.id)
        if (event.raw_text or "").strip().startswith("/"):
            await process_command(client, event.message)
