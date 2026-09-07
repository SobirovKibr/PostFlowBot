"""
Message and Sticker sender module for Telegram Userbot.
Handles single-target transmission with anti-flood and error handling.
"""

import asyncio
from typing import Any, Dict, Optional, Union
from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    ChatWriteForbiddenError,
    UserBannedInChannelError,
    SlowModeWaitError,
    ChannelPrivateError,
    ChatAdminRequiredError,
    FileReferenceExpiredError,
    RPCError,
)
from telethon.tl import types

from logger import logger
import stickers_manager


async def send_message_to_group(
    client: TelegramClient,
    target: Union[str, int],
    message: str,
    max_retries: int = 2
) -> bool:
    """
    Sends a text message to a specific Telegram group or channel.

    Args:
        client: Active Telethon TelegramClient instance.
        target: Target identifier (username, numeric ID, or link).
        message: Text message content to send.
        max_retries: Maximum retries allowed for temporary errors.

    Returns:
        bool: True if message sent successfully, False otherwise.
    """
    target_display = f"'{target}'" if isinstance(target, str) else f"ID:{target}"

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"-> Sending message to {target_display} (Attempt {attempt}/{max_retries})...")
            try:
                await client.send_message(target, message, parse_mode="html", link_preview=False)
            except RPCError:
                raise
            except Exception as parse_err:
                logger.warning(f"HTML parsing note ({parse_err}), retrying with default formatting...")
                await client.send_message(target, message, link_preview=False)
            logger.info(f"[SUCCESS] Message delivered to {target_display}")
            return True

        except FloodWaitError as e:
            wait_time = e.seconds + 2
            logger.warning(
                f"[FLOOD WAIT] Telegram requested wait of {e.seconds}s on {target_display}. "
                f"Sleeping {wait_time}s before retrying..."
            )
            await asyncio.sleep(wait_time)

        except SlowModeWaitError as e:
            wait_time = e.seconds + 1
            logger.warning(
                f"[SLOW MODE] Slow mode active in {target_display}. Waiting {wait_time}s..."
            )
            await asyncio.sleep(wait_time)

        except ChatWriteForbiddenError:
            logger.warning(f"[SKIPPED] Write forbidden in {target_display}. Skipping.")
            return False

        except UserBannedInChannelError:
            logger.warning(f"[SKIPPED] Account banned in {target_display}. Skipping.")
            return False

        except ChatAdminRequiredError:
            logger.warning(f"[SKIPPED] Admin rights required in {target_display}. Skipping.")
            return False

        except ChannelPrivateError:
            logger.warning(f"[SKIPPED] Channel {target_display} is private or inaccessible. Skipping.")
            return False

        except ValueError as e:
            logger.error(f"[INVALID TARGET] Could not resolve entity for {target_display}: {e}")
            return False

        except RPCError as e:
            logger.error(f"[RPC ERROR] Telegram RPC error on {target_display}: {e}")
            return False

        except Exception as e:
            logger.error(f"[UNEXPECTED ERROR] Failed to send message to {target_display}: {type(e).__name__} - {e}")
            return False

    logger.error(f"[FAILED] Exceeded maximum retries ({max_retries}) for message to {target_display}")
    return False


async def send_sticker_to_group(
    client: TelegramClient,
    target: Union[str, int],
    sticker_info: Dict[str, Any],
    max_retries: int = 2
) -> bool:
    """
    Sends a sticker (including Premium stickers) to a specific Telegram group.

    Args:
        client: Active Telethon TelegramClient instance.
        target: Target identifier (username, numeric ID, or link).
        sticker_info: Dictionary containing sticker ID, access_hash, file_ref, etc.
        max_retries: Maximum retries allowed.

    Returns:
        bool: True if sticker was delivered, False otherwise.
    """
    target_display = f"'{target}'" if isinstance(target, str) else f"ID:{target}"
    doc_id = sticker_info.get("id")
    set_short_name = sticker_info.get("set_short_name", "")
    emoji = sticker_info.get("emoji", "🎨")

    input_doc = await stickers_manager.prepare_input_document(client, sticker_info)

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"-> Sending sticker {emoji} (ID: {doc_id}) to {target_display}...")
            await client.send_file(target, input_doc)
            logger.info(f"[SUCCESS] Sticker delivered to {target_display}")
            return True

        except FileReferenceExpiredError:
            logger.warning(f"[STALE FILE REF] File reference expired for sticker {doc_id}. Refreshing...")
            fresh_doc = await stickers_manager.refresh_sticker_document(client, set_short_name, doc_id)
            if fresh_doc:
                input_doc = fresh_doc
                continue
            else:
                logger.error(f"[FAILED REFRESH] Could not refresh sticker {doc_id}. Skipping.")
                return False

        except FloodWaitError as e:
            wait_time = e.seconds + 2
            logger.warning(f"[FLOOD WAIT] Waiting {wait_time}s on {target_display} for sticker...")
            await asyncio.sleep(wait_time)

        except SlowModeWaitError as e:
            wait_time = e.seconds + 1
            logger.warning(f"[SLOW MODE] Waiting {wait_time}s on {target_display} for sticker...")
            await asyncio.sleep(wait_time)

        except (ChatWriteForbiddenError, UserBannedInChannelError, ChatAdminRequiredError, ChannelPrivateError) as e:
            logger.warning(f"[SKIPPED] Cannot send sticker to {target_display}: {type(e).__name__}. Skipping.")
            return False

        except Exception as e:
            logger.error(f"[UNEXPECTED ERROR] Failed to send sticker to {target_display}: {type(e).__name__} - {e}")
            return False

    return False
