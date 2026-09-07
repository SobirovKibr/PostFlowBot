# Telegram Userbot Multi-User SaaS Platform (Ko'p Foydalanuvchili Tizim)

Telegram guruhlariga avtomatlashtirilgan xabarlar (jumladan Telegram Premium harakatlanuvchi emojilar va stikerlar) tarqatuvchi, xavfsiz va to'liq avtonom Multi-User SaaS tizimi.

---

## 🌟 Asosiy Imkoniyatlar va Arxitektura

1. **Shared Redundant API Keys (Zaxirali API Kalitlar Arxitekturasi):**
   - Foydalanuvchilar o'zlarining `api_id` yoki `api_hash` ma'lumotlarini qidirishi shart emas.
   - Serverda ikkita API juftligi (Birlamchi va Zaxira) saqlanadi. Agar birlamchi kalitda cheklov yoki ulanish muammosi yuzaga kelsa, tizim avtomatik ravishda ikkinchi zaxira kalitga o'tadi (`KeyManager`).
2. **Aiogram 3.x Onboarding Bot:**
   - Foydalanuvchi faqat telefon raqami, Telegram ilovasiga kelgan OTP kodi va (agar yoqilgan bo'lsa) 2FA parolini kiritadi.
   - Shaxsiy Telethon sessiyasi serverda `users/{telegram_id}/user.session` faylida xavfsiz saqlanadi.
3. **Saved Messages (Saqlangan Xabarlar) orqali Boshqaruv:**
   - Har bir foydalanuvchi o'z userbotini o'zining Telegram ilovasidagi **Saved Messages** chatiga `/` buyruqlarini yuborish orqali to'liq boshqaradi.
   - MTProto push-bildirishnomalari va yuqori ishonchli fon polleri birgalikda ishlaydi.
4. **Telegram Premium Emojilar va HTML Format:**
   - `<tg-emoji emoji-id="...">` teglarini to'liq qo'llab-quvvatlaydi. Xabardagi barcha premium harakatlanuvchi animatsiyalar buzilmasdan yetkaziladi.
5. **Mustaqil APScheduler Jadvali:**
   - Har bir foydalanuvchi uchun alohida fon vazifasi (`AsyncIOScheduler`).
   - Guruhlararo xavfsiz 3-5 soniyalik kechikish (Anti-Flood / Anti-Ban).
   - Ish vaqti oralig'ini belgilash (`09:00 - 21:00`).
6. **Ma'lumotlar Bazasi va Xavfsizlik:**
   - SQLAlchemy 2.0 Async ORM (PostgreSQL `asyncpg` yoki SQLite `aiosqlite`).
   - Telefon raqamlari Fernet simmetrik shifrlash algoritmi orqali bazada shifrlangan holda saqlanadi.
   - Onboarding uchun soatiga 3 martalik xavfsizlik cheklovi (Rate Limit).

---

## 📁 Loyiha Strukturasi

```text
UserBot/
├── bot/
│   ├── main.py              # Aiogram 3 bot va tizimning boshlang'ich nuqtasi (Bootstrap)
│   ├── onboarding.py        # FSM Onboarding routeri (Telefon -> Kod -> 2FA)
│   ├── admin.py             # Administrator boshqaruv paneli va buyruqlari
│   └── keyboards.py         # Reply va Inline tugmalar
├── core/
│   ├── key_manager.py       # Primary va Fallback API kalitlarni boshqaruvchi modul
│   ├── session_manager.py   # Telethon sessiyalari va shifrlash boshqaruvi
│   ├── commands.py          # Saved Messages buyruqlari va sinxronizatsiya polleri
│   ├── scheduler.py         # Multi-User APScheduler tarqatish dvigateli
│   ├── sender.py            # HTML/Premium emoji va anti-flood xabar yuboruvchi
│   └── sticker_helper.py    # Stiker to'plamlari va aylanish mexanizmi
├── db/
│   ├── database.py          # Asinxron DB engine va sessiyalar
│   ├── models.py            # User, Group, Message, State ORM modellari
│   └── crud.py              # Asinxron ma'lumotlar bazasi amallari
├── users/                   # Har bir foydalanuvchi sessiyalari va stikerlari
│   └── {telegram_id}/
│       ├── user.session
│       └── stickers.json
├── config.py                # Konfiguratsiya va sozlamalar
├── strings.py               # O'zbek tilidagi barcha xabarlar va matnlar
├── get_stickers.py          # Stikerlarni eksport qilish CLI skripti
├── requirements.txt         # Kerakli Python kutubxonalari
├── userbot.service          # Linux Systemd xizmat fayli
└── .env                     # Maxfiy kalitlar va muhit parametrlari
```

---

## 🚀 VPS Serverga O'rnatish (Ubuntu 22.04 / 24.04)

### 1. Tizim paketlarini yangilash va o'rnatish
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git libpq-dev
```

### 2. Loyihani yuklash va virtual muhit yaratish
```bash
cd /home/sobirov/Desktop/UserBot
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 3. Fernet shifrlash kalitini yaratish
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Natijada hosil bo'lgan kalitni nusxalab oling.

### 4. Muhit parametrlarini sozlash (`.env`)
`.env` faylini oching va qiymatlarni kiriting:
```bash
nano .env
```
Fayl namunasi:
```env
# BotFather dan olingan bot tokeni
BOT_TOKEN=7770000000:AAExamplePlaceholderTokenForBotFather

# Admin Telegram ID raqami
ADMIN_IDS=8983737418

# Telegram API Kalitlar (Shared)
PRIMARY_API_ID=20319723
PRIMARY_API_HASH=01a4cedda56c677958b7d56d19e627fd

FALLBACK_API_ID=32709830
FALLBACK_API_HASH=41f3c9cc39bf0274ec7b28039a890d13

# Ma'lumotlar bazasi:
# Local/SQLite uchun:
DATABASE_URL=sqlite+aiosqlite:///saas_userbot.db
# PostgreSQL uchun:
# DATABASE_URL=postgresql+asyncpg://userbot_user:strong_password@localhost:5432/userbot_db

# Yuqorida generatsiya qilingan Fernet kaliti
ENCRYPTION_KEY=yeC6GG5DpNgZko5e1BF6oVoOoDXR7ViAO7WJWoo1GVA=

# Standart parametrlar
DEFAULT_INTERVAL_MINUTES=60
DEFAULT_START_TIME=09:00
DEFAULT_END_TIME=21:00
DEFAULT_TIMEZONE=Asia/Tashkent

MIN_DELAY_BETWEEN_GROUPS=3
MAX_DELAY_BETWEEN_GROUPS=5
ROUND_JITTER_SECONDS=30
```

---

## 🛠️ PostgreSQL O'rnatish (Tavsiya etiladi)

Agar SQLite o'rniga PostgreSQL ishlatmoqchi bo'lsangiz:
```bash
sudo apt install -y postgresql postgresql-contrib
sudo -u postgres psql
```
PostgreSQL konsolida:
```sql
CREATE DATABASE userbot_db;
CREATE USER userbot_user WITH PASSWORD 'strong_password';
GRANT ALL PRIVILEGES ON DATABASE userbot_db TO userbot_user;
ALTER DATABASE userbot_db OWNER TO userbot_user;
\q
```
So'ngra `.env` faylidagi `DATABASE_URL` parametrini moslang:
```env
DATABASE_URL=postgresql+asyncpg://userbot_user:strong_password@localhost:5432/userbot_db
```

---

## 🤖 Tizimni Ishga Tushirish

### Test rejimida qo'lda tekshirish:
```bash
source venv/bin/activate
python3 bot/main.py
```
Konsolda quyidagi startup banner chiqadi:
- Baza initsializatsiyasi
- Primary va Fallback API kalitlarining `ONLINE` tekshiruvi
- Faol foydalanuvchilarning yuklanishi
- Aiogram polling boshlanishi

---

## ⚙️ 24/7 Fon Rejimi (Systemd Service)

Server qayta yoqilganda ham tizim to'xtovsiz ishlashi uchun `systemd` xizmatini yoqing:

1. Xizmat faylini tizimga ko'chirish:
```bash
sudo cp /home/sobirov/Desktop/UserBot/userbot.service /etc/systemd/system/userbot.service
```

2. Daemonni qayta yuklash va xizmatni yoqish:
```bash
sudo systemctl daemon-reload
sudo systemctl enable userbot.service
sudo systemctl start userbot.service
```

3. Xizmat holatini tekshirish:
```bash
sudo systemctl status userbot.service
```

4. Loglarni jonli kuzatish:
```bash
journalctl -u userbot.service -f
# Yoki loyihadagi fayldan:
tail -f saas_userbot.log
```

---

## 🎮 Buyruqlar Qo'llanmasi

### 1. Yangi Foydalanuvchi Onboarding Jarayoni:
1. Foydalanuvchi Telegram botingizga kiradi va `/start` bosadi.
2. Bot telefon raqamini so'raydi (yoki "📱 Kontaktni yuborish" tugmasi bosiladi).
3. Tizim birlamchi API kaliti orqali kod so'raydi (muammo bo'lsa zaxira kalitga o'tadi).
4. Foydalanuvchi Telegram ilovasiga kelgan 5 xonali OTP kodni kiritadi.
5. Agar akkauntda 2FA bo'lsa, parolni kiritadi.
6. Sessiya saqlanadi va uning shaxsiy userboti ishga tushadi!

---

### 2. Foydalanuvchining Shaxsiy Boshqaruvi (Saved Messages):
Foydalanuvchi o'z Telegram ilovasidagi **Saved Messages (Saqlangan xabarlar)** chatiga kirib boshqaradi:

| Buyruq | Vazifasi |
|---|---|
| `/start_sending` | Avtomatik rejalashtirilgan yuborishni boshlash |
| `/stop_sending` | Avto-yuboruvchini pauzaga qo'yish |
| `/status` | Bot holati, keyingi yuborish vaqti, guruhlar soni |
| `/send_now` | Barcha guruhlarga zudlik bilan bitta xabar yuborish |
| `/add_group <@username/id>` | Xabar yuboriladigan guruh qo'shish |
| `/remove_group <@username/id>` | Guruhni ro'yxatdan o'chirish |
| `/list_groups` | Barcha saqlangan target guruhlar ro'yxati |
| `/add_message <matn>` | Yangi aylanma xabar qo'shish (Premium emojilarni saqlaydi) |
| `/list_messages` | Barcha xabarlar ro'yxati |
| `/remove_message <raqam>` | Xabarni raqami bo'yicha o'chirish |
| `/set_message <raqam>` | Navbatdagi yuboriladigan xabarni tanlash |
| `/set_interval <daqiqa>` | Yuborish oralig'ini o'zgartirish (masalan: `/set_interval 30`) |
| `/set_window <boshlanish> <tugash>` | Ish vaqti oralig'ini belgilash (`09:00 21:00`) |
| `/sticker_on` / `/sticker_off` | Stiker yuborishni yoqish / o'chirish |
| `/list_stickers` | Yuklangan stiker to'plamlarini ko'rish |
| `/set_sticker_set <nomi>` | Faol stiker to'plamini tanlash |
| `/resync_stickers` | Akkauntdagi stikerlarni qayta yuklash |
| `/help` | Barcha buyruqlar ro'yxati |

---

### 3. Administrator Buyruqlari (Admin Bot):
Faqat `ADMIN_IDS` ro'yxatidagi ma'murlar uchun:

| Buyruq | Vazifasi |
|---|---|
| `/admin` | Interaktiv boshqaruv menyusi (Inline dashboard) |
| `/admin_stats` | Tizim statistikasi (Foydalanuvchilar, guruhlar, sessiyalar) |
| `/admin_users` | Foydalanuvchilar ro'yxati (sahifalash bilan) |
| `/admin_user <telegram_id>` | Muayyan foydalanuvchining batafsil ma'lumotlari |
| `/admin_ban <telegram_id>` | Foydalanuvchini bloklash (sessiya va jadval uziladi) |
| `/admin_unban <telegram_id>` | Blokdan chiqarish va qayta ishga tushirish |
| `/admin_restart_user <telegram_id>` | Foydalanuvchi userbotini qayta ishga tushirish |
| `/admin_broadcast <xabar>` | Barcha ro'yxatdan o'tganlarga e'lon yuborish |
| `/admin_key_status` | Primary va Fallback API kalitlarining jonli holati |

---

## 🔒 Xavfsizlik va Zaxira Nusxalash (Backup)

1. **Shifrlangan Ma'lumotlar:** Barcha telefon raqamlar bazada `Fernet` yordamida shifrlangan.
2. **Sessiyalar Izolyatsiyasi:** Har bir foydalanuvchining sessiyasi `users/{telegram_id}/user.session` papkasida alohida saqlanadi.
3. **Zaxiralash Skripti:**
   ```bash
   # Har kuni bazani va sessiyalarni arxivlash:
   tar -czvf /backup/userbot_backup_$(date +%F).tar.gz saas_userbot.db users/ .env
   ```
