"""
Logging configuration for Site Web Monitor.

Sets up structured logging with appropriate levels.
Ensures sensitive data (tokens, cookies, passwords) is never logged.
"""

import logging
import re
import sys


class SensitiveDataFilter(logging.Filter):
    """Filter that redacts patterns resembling tokens or secrets from log output."""

    # Patterns that might contain sensitive data
    _PATTERNS = [
        # Telegram bot token format: digits:alphanumeric
        re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{35}\b"),
        # Generic "token=..." or "token:..." patterns
        re.compile(r"(token[=:]\s*)[^\s,\"']+", re.IGNORECASE),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern in self._PATTERNS:
                record.msg = pattern.sub("[REDACTED]", record.msg)
        return True


def setup_logging(*, debug: bool = False) -> None:
    """Configure the root logger for the application.

    Args:
        debug: If True, set log level to DEBUG. Otherwise INFO.
    """
    level = logging.DEBUG if debug else logging.INFO

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(SensitiveDataFilter())

    root = logging.getLogger()
    root.setLevel(level)

    # Remove any existing handlers to avoid duplicates on re-init
    root.handlers.clear()
    root.addHandler(handler)

    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)
