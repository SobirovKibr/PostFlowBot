"""
KeyManager: Manages primary and fallback Telegram API key pairs.
Provides automatic failover, health checks, and key status reporting.
"""

from typing import Any, Dict, Optional, Tuple
from loguru import logger
from telethon import TelegramClient
from telethon.errors import (
    ApiIdInvalidError,
    AuthKeyError,
    PhoneNumberBannedError,
    PhoneNumberInvalidError,
)

import config


class KeyManager:
    """Manages redundant Telegram API Key pairs with automatic failover."""

    def __init__(self):
        self.api_keys: list[Dict[str, Any]] = config.API_KEYS
        # Track status: True if operational, False if restricted
        self.key_status: Dict[int, bool] = {0: True, 1: True}
        self.failure_reasons: Dict[int, str] = {0: "OK", 1: "OK"}

    def get_key(self, index: int) -> Dict[str, Any]:
        """Returns API credentials for given index."""
        if 0 <= index < len(self.api_keys):
            return self.api_keys[index]
        return self.api_keys[0]

    def get_primary(self) -> Dict[str, Any]:
        return self.get_key(0)

    def get_fallback(self) -> Dict[str, Any]:
        return self.get_key(1)

    def mark_key_failed(self, index: int, reason: str = "Auth/Connection Error"):
        """Marks a key as failed and records the reason."""
        self.key_status[index] = False
        self.failure_reasons[index] = reason
        logger.warning(
            f"[KEY MANAGER] API Key #{index} ({self.api_keys[index]['label']} ID: {self.api_keys[index]['api_id']}) "
            f"marked as FAILED. Reason: {reason}"
        )

    def mark_key_recovered(self, index: int):
        self.key_status[index] = True
        self.failure_reasons[index] = "OK"
        logger.info(f"[KEY MANAGER] API Key #{index} marked as RECOVERED/OK.")

    async def try_connect(
        self, session_target: Any = None
    ) -> Tuple[TelegramClient, int]:
        """
        Attempts to create and connect a TelegramClient using the primary API key.
        If primary fails or is marked failed, automatically falls back to secondary key.

        Returns:
            Tuple[TelegramClient, int]: Connected client instance and the key_index used.
        """
        # Determine starting index based on known health
        indices_to_try = [0, 1] if self.key_status.get(0, True) else [1, 0]

        last_exception = None

        for idx in indices_to_try:
            key_data = self.get_key(idx)
            api_id = key_data["api_id"]
            api_hash = key_data["api_hash"]

            logger.info(
                f"[KEY MANAGER] Attempting connection with Key #{idx} ({key_data['label']} ID: {api_id})..."
            )

            client = TelegramClient(
                session=session_target,
                api_id=api_id,
                api_hash=api_hash,
            )

            try:
                await client.connect()
                # If connection succeeds, ensure status is marked operational
                self.mark_key_recovered(idx)
                logger.info(f"[KEY MANAGER] Successfully connected using Key #{idx}.")
                return client, idx

            except (AuthKeyError, ApiIdInvalidError) as e:
                self.mark_key_failed(idx, f"Critical auth error: {type(e).__name__}")
                last_exception = e
                await client.disconnect()
                logger.warning(
                    f"[KEY MANAGER] Key #{idx} failed with {type(e).__name__}. Falling back..."
                )
                continue

            except Exception as e:
                logger.warning(f"[KEY MANAGER] Key #{idx} encountered {type(e).__name__}: {e}")
                last_exception = e
                await client.disconnect()
                continue

        raise RuntimeError(
            f"All Telegram API Keys exhausted. Last error: {last_exception}"
        )

    async def health_check_keys(self) -> list[Dict[str, Any]]:
        """
        Runs on startup to test connectivity of both API keys with an ephemeral session.
        """
        logger.info("--- Testing Telegram API Key Pairs Connectivity ---")
        results = []

        for idx, key in enumerate(self.api_keys):
            test_client = TelegramClient(None, key["api_id"], key["api_hash"])
            try:
                await test_client.connect()
                self.mark_key_recovered(idx)
                results.append({
                    "index": idx,
                    "status": "Active",
                    "api_id": key["api_id"],
                    "label": key["label"],
                    "error": None,
                })
                logger.info(f"  [+] Key #{idx} ({key['label']} ID: {key['api_id']}): ONLINE")
            except Exception as e:
                self.mark_key_failed(idx, str(e))
                results.append({
                    "index": idx,
                    "status": "Failed",
                    "api_id": key["api_id"],
                    "label": key["label"],
                    "error": str(e),
                })
                logger.error(f"  [-] Key #{idx} ({key['label']} ID: {key['api_id']}): OFFLINE ({e})")
            finally:
                try:
                    await test_client.disconnect()
                except Exception:
                    pass

        return results


# Global KeyManager singleton
key_manager = KeyManager()
