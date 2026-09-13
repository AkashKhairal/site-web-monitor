"""
Telegram notification module for Site Web Monitor.

Sends notifications via the Telegram Bot API using httpx.
Never logs the bot token. Handles errors, timeouts, rate limits.
"""

import logging
from typing import List, Optional

import httpx

from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from app.history import WebsiteEntry

logger = logging.getLogger(__name__)

# Telegram Bot API base URL (token is appended at runtime, never logged)
_API_BASE = "https://api.telegram.org/bot"

# Timeouts
_REQUEST_TIMEOUT = 30  # seconds


async def send_message(text: str, *, dry_run: bool = False) -> bool:
    """Send a message via Telegram Bot API.

    Args:
        text: Message text to send.
        dry_run: If True, log the message but don't actually send.

    Returns:
        True if the message was sent (or dry_run), False on failure.
    """
    if dry_run:
        logger.info("[DRY RUN] Would send Telegram message:\n%s", text)
        return True

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error(
            "Telegram not configured (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing)"
        )
        return False

    url = f"{_API_BASE}{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            response = await client.post(url, json=payload)

            if response.status_code == 200:
                logger.info("Telegram notification sent successfully")
                return True
            elif response.status_code == 429:
                # Rate limited
                logger.warning(
                    "Telegram rate limited (429). Will retry on next cycle."
                )
                return False
            else:
                # Log status but not the URL (contains token)
                logger.error(
                    "Telegram API error: HTTP %d — %s",
                    response.status_code,
                    response.text[:200],
                )
                return False

    except httpx.TimeoutException:
        logger.error("Telegram request timed out after %ds", _REQUEST_TIMEOUT)
        return False
    except httpx.HTTPError as exc:
        logger.error("Telegram HTTP error: %s", exc)
        return False
    except Exception as exc:
        logger.error("Unexpected error sending Telegram message: %s", exc)
        return False


def format_single_entry(entry: WebsiteEntry, count: int) -> str:
    """Format a notification for a single new website entry."""
    time_str = entry.timestamp or "Not available"
    return (
        "🔔 <b>New Website Detected</b>\n"
        "\n"
        f"SITE WEB Count: {count}\n"
        f"Website: {entry.website}\n"
        f"Time: {time_str}"
    )


def format_multiple_entries(entries: List[WebsiteEntry], count: int) -> str:
    """Format a notification for multiple new website entries."""
    lines = [
        "🔔 <b>New Website Activity</b>\n",
        f"SITE WEB Count: {count}",
        f"New entries: {len(entries)}\n",
    ]

    for i, entry in enumerate(entries, 1):
        time_str = entry.timestamp or "Not available"
        lines.append(f"{i}. {entry.website}")
        lines.append(f"   {time_str}\n")

    return "\n".join(lines)


def format_auth_failure() -> str:
    """Format an authentication failure notification."""
    return (
        "⚠️ <b>Authentication Required</b>\n"
        "\n"
        "The Mobile Tracker Free monitoring session has expired.\n"
        "\n"
        "Run the authentication setup again on the Oracle VM:\n"
        "<code>python -m setup.auth_setup</code>"
    )


def format_error(error_msg: str) -> str:
    """Format an operational error notification."""
    return (
        "⚠️ <b>Monitor Error</b>\n"
        "\n"
        f"{error_msg}"
    )


async def notify_new_entries(
    entries: List[WebsiteEntry],
    count: int,
    *,
    dry_run: bool = False,
) -> bool:
    """Send notification for new website entries.

    Args:
        entries: List of new entries to notify about.
        count: Current SITE WEB count.
        dry_run: If True, log but don't send.

    Returns:
        True if notification was sent successfully, False otherwise.
    """
    if not entries:
        return True

    if len(entries) == 1:
        text = format_single_entry(entries[0], count)
    else:
        text = format_multiple_entries(entries, count)

    return await send_message(text, dry_run=dry_run)


async def notify_auth_failure(*, dry_run: bool = False) -> bool:
    """Send authentication failure notification."""
    return await send_message(format_auth_failure(), dry_run=dry_run)


async def notify_error(error_msg: str, *, dry_run: bool = False) -> bool:
    """Send operational error notification."""
    return await send_message(format_error(error_msg), dry_run=dry_run)
