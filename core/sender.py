"""
Sender module: Handles transmission of rich messages (with Telegram Premium Custom Emojis)
and optional stickers to a target Telegram group/channel.
Features robust anti-flood, slow mode, and error handling.
"""

import asyncio
import random
from typing import Any, Optional, Union
from loguru import logger
from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    ChatAdminRequiredError,
    ChatWriteForbiddenError,
    FloodWaitError,
    RPCError,
    SlowModeWaitError,
    UserBannedInChannelError,
)

import config


def append_watermark(text: str) -> str:
    """
    Appends a stylish blockquote watermark attribution to the message.
    Preserves all existing HTML entities and Telegram Premium custom emojis.
    """
    cleaned = (text or "").rstrip()
    bot_user = getattr(config, "BOT_USERNAME", "GetPostFlowBot") or "GetPostFlowBot"
    if f"@{bot_user}" in cleaned:
        return cleaned

    watermark = f'\n\n<blockquote>🤖 <b><a href="https://t.me/{bot_user}">@{bot_user}</a> orqali yuborildi</b></blockquote>'
    return cleaned + watermark


def append_plain_watermark(text: str) -> str:
    """Fallback plain text watermark if HTML parsing encounters issues."""
    cleaned = (text or "").rstrip()
    bot_user = getattr(config, "BOT_USERNAME", "GetPostFlowBot") or "GetPostFlowBot"
    if f"@{bot_user}" in cleaned:
        return cleaned
    return cleaned + f"\n\n—\n🤖 @{bot_user} orqali yuborildi"


async def send_to_group(
    client: TelegramClient,
    group_identifier: Union[str, int],
    message_text: str,
    sticker_doc: Optional[Any] = None,
    send_sticker: bool = False,
    min_delay: int = config.MIN_DELAY_BETWEEN_GROUPS,
    max_delay: int = config.MAX_DELAY_BETWEEN_GROUPS,
    max_retries: int = 2,
) -> bool:
    """
    Sends a message (with full Telegram Premium emoji support via HTML and stylish watermark)
    and an optional sticker to a single Telegram group or channel.

    Returns:
        bool: True if delivered successfully, False otherwise.
    """
    target_display = f"'{group_identifier}'" if isinstance(group_identifier, str) else f"ID:{group_identifier}"

    # Prepare message with watermark
    final_html_message = append_watermark(message_text)

    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"-> Sending message to {target_display} (Attempt {attempt}/{max_retries})...")
            
            # 1. Resolve entity
            entity = await client.get_input_entity(group_identifier)

            # 2. Send text message with HTML mode to preserve Premium custom emojis & blockquote watermark
            try:
                await client.send_message(entity, final_html_message, parse_mode="html", link_preview=False)
            except RPCError:
                raise
            except Exception as parse_err:
                logger.warning(f"HTML format notice on {target_display} ({parse_err}), sending standard text...")
                fallback_text = append_plain_watermark(message_text)
                await client.send_message(entity, fallback_text, link_preview=False)

            logger.info(f"[SUCCESS] Message delivered to {target_display}")

            # 3. Send optional sticker if enabled
            if send_sticker and sticker_doc:
                await asyncio.sleep(random.uniform(2.0, 4.0))
                try:
                    await client.send_file(entity, sticker_doc)
                    logger.info(f"[SUCCESS] Attached sticker sent to {target_display}")
                except Exception as s_err:
                    logger.warning(f"Could not send sticker to {target_display}: {s_err}")

            # 4. Anti-ban delay before next group
            delay = random.uniform(min_delay, max_delay)
            logger.info(f"[ANTI-BAN] Sleeping {delay:.1f}s after {target_display}...")
            await asyncio.sleep(delay)
            return True

        except FloodWaitError as e:
            wait_time = e.seconds + 10
            logger.warning(
                f"[FLOOD WAIT] Telegram rate limit on {target_display}: wait {e.seconds}s. "
                f"Sleeping {wait_time}s before retry..."
            )
            await asyncio.sleep(wait_time)
            # Retries next attempt

        except SlowModeWaitError as e:
            wait_time = e.seconds + 2
            logger.warning(f"[SLOW MODE] Active on {target_display}. Waiting {wait_time}s...")
            await asyncio.sleep(wait_time)

        except ChatWriteForbiddenError:
            logger.warning(f"[SKIPPED] Write forbidden in {target_display}. Skipping group.")
            return False

        except UserBannedInChannelError:
            logger.warning(f"[SKIPPED] Account banned in {target_display}. Skipping group.")
            return False

        except ChatAdminRequiredError:
            logger.warning(f"[SKIPPED] Admin rights required in {target_display}. Skipping group.")
            return False

        except ChannelPrivateError:
            logger.warning(f"[SKIPPED] Channel {target_display} is private or inaccessible. Skipping.")
            return False

        except ValueError as e:
            logger.error(f"[INVALID TARGET] Could not resolve entity for {target_display}: {e}")
            return False

        except RPCError as e:
            logger.error(f"[RPC ERROR] Telegram error on {target_display}: {e}")
            return False

        except Exception as e:
            logger.error(f"[UNEXPECTED ERROR] Failed on {target_display}: {type(e).__name__} - {e}")
            return False

    return False
