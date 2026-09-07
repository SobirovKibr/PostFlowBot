"""
Centralized strings and localization for Multi-User Telegram Userbot SaaS.
Easy to modify and translate.
"""

# =====================================================================
# Onboarding Bot Strings (Aiogram)
# =====================================================================
WELCOME = """
👋 **Assalomu alaykum! Telegram Avtomatlashtirish Platformasiga xush kelibsiz.**

Ushbu bot orqali siz o'zingizning Telegram akkauntingizni avtomatlashtirishingiz va xabarlaringizni o'zingiz tanlagan guruhlarga belgilangan jadval bo'yicha avtomatik yuborishingiz mumkin!

💎 **Asosiy Imkoniyatlar:**
• Guruhlarga rejalashtirilgan xabarlarni avtomatik tarqatish
• Telegram Premium harakatlanuvchi emojilarni 100% qo'llab-quvvatlash
• Xavfsiz Anti-Ban va Anti-Flood tizimi
• Barcha boshqaruv bevosita o'zingizning **Saved Messages** chatingiz orqali amalga oshiriladi!

Boshlash uchun telefon raqamingizni xalqaro formatda yuboring (masalan: `+998901234567`) yoki pastdagi **"📱 Kontaktni yuborish"** tugmasini bosing:
"""

ASK_PHONE = """
📱 Iltimos, Telegram akkauntingizga ulangan telefon raqamingizni kiriting:
(Masalan: `+998901234567`)
"""

INVALID_PHONE = """
⚠️ **Telefon raqami noto'g'ri kiritildi.**
Raqamni `+` belgisi va mamlakat kodi bilan to'liq kiriting (masalan: `+998901234567`).
"""

RATE_LIMITED = """
⛔ **Xavfsizlik cheklovi:**
Siz 1 soat ichida juda ko'p urinish qildingiz. Iltimos, 1 soatdan so'ng qayta urinib ko'ring.
"""

ASK_OTP = """
📩 **Telegram ilovangizga tasdiqlash kodi yuborildi!**

🔴 **DIQQAT, JUDA MUHIM QOIDA!**
Telegram xavfsizlik tizimi kodni chatda sezib qolsa, uni **darhol bekor (expire) qilib yuboradi!**

Shuning uchun kodni **to'g'ridan-to'g'ri oddiy raqam qilib yubormang!**

Kodni raqamlari orasiga **nuqta (.)** qo'yib yuboring:
👉 Masalan: `12.345` yoki `1.2.3.4.5` yoki `82.726`

*(Tizim nuqtalarni avtomatik tozalab qabul qiladi).*
"""

INVALID_OTP = """
⚠️ **Tasdiqlash kodi noto'g'ri.**
Iltimos, kodni raqamlari orasiga **nuqta (.)** qo'yib qayta kiriting (masalan: `12.345`).
Qolgan urinishlar soni: {attempts} ta.
"""

EXPIRED_OTP = """
⏳ **Kodingizning amal qilish muddati tugadi yoki Telegram uni bekor qildi.**
Agar kodni to'g'ridan-to'g'ri yuborgan bo'lsangiz, Telegram xavfsizligi uni avtomatik o'chirgan bo'lishi mumkin.

Qaytadan boshlash uchun /start buyrug'ini yuboring va kod orasiga **nuqta (.)** qo'yib yuboring!
"""

ASK_2FA = """
🔐 **Ikki bosqichli autentifikatsiya (2FA) aniqlandi.**

Akkauntingizda 2FA paroli mavjud. Iltimos, Telegram parolingizni kiriting (Qolgan urinishlar: {attempts}):
"""

INVALID_2FA = """
⚠️ **Parol noto'g'ri kiritildi.**
Iltimos, parolingizni tekshirib qayta kiriting (Qolgan urinishlar: {attempts}):
"""

ALREADY_REGISTERED = """
ℹ️ **Siz allaqachon ro'yxatdan o'tgansiz!**

Sizning userbotingiz faol holatda. Botni boshqarish uchun o'zingizning Telegram ilovangizdagi **Saved Messages (Saqlangan xabarlar)** chatiga o'ting va `/help` deb yozing!
"""

ONBOARDING_SUCCESS = """
🎉 **Muborakbod etamiz! Akkauntingiz muvaffaqiyatli ulandi!**

Sizning shaxsiy userbotingiz ishga tushirildi va fon rejimida ishlamoqda.

🚀 **Qanday boshlash kerak?**
1. Telegram ilovangizdagi **"Saved Messages" (Saqlangan xabarlar)** chatiga kiring.
2. U yerga `/help` deb yozing — barcha buyruqlar ro'yxati chiqadi.
3. `/add_group @guruh_username` — xabar yuboriladigan guruhlarni qo'shing.
4. `/add_message <xabar>` — yuboriladigan matn va Premium emojilaringizni kiriting.
5. `/start_sending` — avtomatik yuborishni boshlang!

Barcha sozlamalar va o'zgarishlar faqat o'zingizning Saved Messages chatingiz orqali boshqariladi. Omad!
"""

# =====================================================================
# Saved Messages Command Strings
# =====================================================================
SAVED_HELP = """
🤖 **SIZNING SHAXSIY USERBOT BOSHQARUV PANELI**

⚡ **Jadval Boshqaruvi (Scheduler):**
• `/start_sending` — Avtomatik yuborishni boshlash
• `/stop_sending` — Avtomatik yuborishni pauzaga qo'yish
• `/status` — Botning to'liq ish holatini ko'rish
• `/send_now` — Barcha guruhlarga zudlik bilan hozir xabar yuborish

👥 **Guruhlar Boshqaruvi:**
• `/add_group <username/id>` — Guruh qo'shish (masalan: `/add_group @mygroup`)
• `/remove_group <username/id>` — Guruhni ro'yxatdan o'chirish
• `/list_groups` — Saqlangan target guruhlar ro'yxati

📝 **Xabarlar Boshqaruvi:**
• `/add_message <matn>` — Yangi xabar qo'shish (Telegram Premium emojilarni 100% saqlaydi!)
• `/list_messages` — Barcha xabarlarni raqami bilan ko'rish
• `/remove_message <raqam>` — Xabarni raqami bo'yicha o'chirish
• `/set_message <raqam>` — Navbatdagi yuboriladigan xabarni belgilash

🎨 **Stikerlar Boshqaruvi (Ixtiyoriy):**
• `/sticker_on` — Xabardan so'ng stiker yuborishni yoqish
• `/sticker_off` — Stiker yuborishni o'chirish
• `/list_stickers` — Yuklangan stiker to'plamlarini ko'rish
• `/set_sticker_set <nomi>` — Stiker to'plamini tanlash

⏱️ **Vaqt va Kutilma Sozlamalari:**
• `/set_interval <daqiqa>` — Yuborish oralig'ini o'zgartirish (masalan: `/set_interval 30`)
• `/set_window <HH:MM> <HH:MM>` — Ish vaqti oralig'i (masalan: `/set_window 09:00 21:00`)
• `/set_delay <soniya>` — Guruhlararo kutilma (masalan: `/set_delay 3`)

ℹ️ **Yordam:**
• `/help` — Ushbu buyruqlar ro'yxatini chiqarish
"""

CANCELLED = "❌ Amal bekor qilindi."
