"""
Global Configuration for Multi-User Telegram Userbot SaaS System.
Loads environment variables, manages redundant API keys, encryption, and system paths.
"""

import os
from pathlib import Path
from typing import Any, Dict, List
from cryptography.fernet import Fernet
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

if ENV_FILE.exists():
    load_dotenv(dotenv_path=ENV_FILE)
else:
    load_dotenv()

# =====================================================================
# Redundant Telegram API Key Pairs (Primary & Fallback)
# =====================================================================
API_KEYS: List[Dict[str, Any]] = [
    {
        "api_id": int(os.getenv("PRIMARY_API_ID", "20319723")),
        "api_hash": os.getenv("PRIMARY_API_HASH", "01a4cedda56c677958b7d56d19e627fd"),
        "label": "Primary",
    },
    {
        "api_id": int(os.getenv("FALLBACK_API_ID", "32709830")),
        "api_hash": os.getenv("FALLBACK_API_HASH", "41f3c9cc39bf0274ec7b28039a890d13"),
        "label": "Fallback",
    },
]

# =====================================================================
# Telegram Bot Token & Admin IDs
# =====================================================================
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
BOT_USERNAME: str = os.getenv("BOT_USERNAME", "GetPostFlowBot").strip("@")

raw_admins = os.getenv("ADMIN_IDS", "8983737418").strip()
ADMIN_IDS: List[int] = [
    int(x.strip()) for x in raw_admins.split(",") if x.strip().isdigit()
]

# =====================================================================
# Database Configuration (PostgreSQL with SQLite fallback)
# =====================================================================
# Production: postgresql+asyncpg://user:password@localhost:5432/userbot_db
# Local testing: sqlite+aiosqlite:///saas_userbot.db
DATABASE_URL: str = os.getenv(
    "DATABASE_URL", "sqlite+aiosqlite:///" + str(BASE_DIR / "saas_userbot.db")
)

# =====================================================================
# Security & Encryption (Fernet key for phone numbers)
# =====================================================================
ENCRYPTION_KEY: str = os.getenv("ENCRYPTION_KEY", "").strip()
if not ENCRYPTION_KEY:
    # Auto-generate if missing for development; in production provide via .env
    ENCRYPTION_KEY = Fernet.generate_key().decode()

SESSIONS_DIR: Path = BASE_DIR / "users"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

# =====================================================================
# Operational Defaults
# =====================================================================
DEFAULT_INTERVAL_MINUTES: int = int(os.getenv("DEFAULT_INTERVAL_MINUTES", "60"))
DEFAULT_START_TIME: str = os.getenv("DEFAULT_START_TIME", "09:00")
DEFAULT_END_TIME: str = os.getenv("DEFAULT_END_TIME", "21:00")
DEFAULT_TIMEZONE: str = os.getenv("DEFAULT_TIMEZONE", "Asia/Tashkent")

MIN_DELAY_BETWEEN_GROUPS: int = int(os.getenv("MIN_DELAY_BETWEEN_GROUPS", "3"))
MAX_DELAY_BETWEEN_GROUPS: int = int(os.getenv("MAX_DELAY_BETWEEN_GROUPS", "5"))
ROUND_JITTER_SECONDS: int = int(os.getenv("ROUND_JITTER_SECONDS", "30"))

# Rate limit for onboarding: max 3 attempts per hour per telegram_id
MAX_ONBOARDING_ATTEMPTS_PER_HOUR: int = 3
