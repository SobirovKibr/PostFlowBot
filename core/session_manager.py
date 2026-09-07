"""
Session Manager: Manages creation, storage, loading, and deletion
of per-user Telethon sessions and Fernet encryption for sensitive credentials.
"""

from pathlib import Path
from typing import Dict, Optional
from cryptography.fernet import Fernet
from loguru import logger
from telethon import TelegramClient

import config
from core.key_manager import key_manager

# Fernet cipher instance
cipher = Fernet(config.ENCRYPTION_KEY.encode() if isinstance(config.ENCRYPTION_KEY, str) else config.ENCRYPTION_KEY)


def encrypt_phone(phone: str) -> str:
    """Encrypts plaintext phone number using Fernet."""
    return cipher.encrypt(phone.strip().encode()).decode()


def decrypt_phone(encrypted_phone: str) -> str:
    """Decrypts Fernet-encrypted phone number."""
    try:
        return cipher.decrypt(encrypted_phone.encode()).decode()
    except Exception as e:
        logger.error(f"Failed to decrypt phone: {e}")
        return "+998000000000"


def get_user_dir(telegram_id: int) -> Path:
    """Returns the dedicated filesystem folder for a specific user."""
    user_dir = config.SESSIONS_DIR / str(telegram_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def get_user_session_path(telegram_id: int) -> str:
    """Returns string path for Telethon session file without .session suffix."""
    return str(get_user_dir(telegram_id) / "user")


class SessionManager:
    """Manages active live Telethon clients for each registered user."""

    def __init__(self):
        self._active_clients: Dict[int, TelegramClient] = {}

    def is_user_running(self, telegram_id: int) -> bool:
        client = self._active_clients.get(telegram_id)
        return client is not None and client.is_connected()

    def get_client(self, telegram_id: int) -> Optional[TelegramClient]:
        return self._active_clients.get(telegram_id)

    async def start_user_session(
        self,
        telegram_id: int,
        api_key_index: int = 0
    ) -> Optional[TelegramClient]:
        """
        Loads and starts a Telethon client for a given user from their stored session.
        Registers their Saved Messages listener.
        """
        if self.is_user_running(telegram_id):
            return self._active_clients[telegram_id]

        session_path = get_user_session_path(telegram_id)
        session_file = Path(f"{session_path}.session")

        if not session_file.exists():
            logger.warning(f"[SESSION] No session file found for user {telegram_id} at {session_file}")
            return None

        key_data = key_manager.get_key(api_key_index)
        client = TelegramClient(
            session=session_path,
            api_id=key_data["api_id"],
            api_hash=key_data["api_hash"],
        )

        try:
            await client.connect()
            if not await client.is_user_authorized():
                logger.warning(f"[SESSION] Session for user {telegram_id} is unauthorized or expired.")
                await client.disconnect()
                return None

            self._active_clients[telegram_id] = client
            logger.info(f"[SESSION] Successfully loaded and started userbot for user {telegram_id} (Key #{api_key_index})")

            # Register user's Saved Messages command listener and sync poller
            from core.commands import register_saved_message_handlers
            await register_saved_message_handlers(client, telegram_id)

            return client

        except Exception as e:
            logger.error(f"[SESSION] Failed to start user session {telegram_id}: {e}")
            if client.is_connected():
                await client.disconnect()
            return None

    async def stop_user_session(self, telegram_id: int):
        """Disconnects and removes active client for a user."""
        client = self._active_clients.pop(telegram_id, None)
        if client and client.is_connected():
            try:
                await client.disconnect()
                logger.info(f"[SESSION] Disconnected userbot for user {telegram_id}")
            except Exception as e:
                logger.error(f"[SESSION] Error disconnecting user {telegram_id}: {e}")

    async def stop_all(self):
        """Gracefully disconnects all running user sessions on server shutdown."""
        logger.info(f"Stopping all ({len(self._active_clients)}) active userbot sessions...")
        for tg_id, client in list(self._active_clients.items()):
            if client.is_connected():
                try:
                    await client.disconnect()
                except Exception:
                    pass
        self._active_clients.clear()
        logger.info("All userbot sessions stopped cleanly.")


# Global SessionManager singleton
session_manager = SessionManager()
