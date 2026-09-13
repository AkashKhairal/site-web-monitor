"""
Centralized configuration for Site Web Monitor.

All configuration is loaded from environment variables or a .env file.
Secrets (TELEGRAM_BOT_TOKEN, etc.) must never appear in source code.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Load .env if present (ignored in production where env vars are set directly)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_env_path = _PROJECT_ROOT / ".env"
if _env_path.is_file():
    load_dotenv(_env_path)

# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.environ.get("TELEGRAM_CHAT_ID", "")

# ---------------------------------------------------------------------------
# Target website
# ---------------------------------------------------------------------------
TARGET_LOGIN_URL: str = os.environ.get(
    "TARGET_LOGIN_URL", "https://mobile-tracker-free.com/login/"
)
TARGET_DASHBOARD_URL: str = os.environ.get(
    "TARGET_DASHBOARD_URL", "https://mobile-tracker-free.com/dashboard/"
)

# ---------------------------------------------------------------------------
# Monitoring
# ---------------------------------------------------------------------------
CHECK_INTERVAL_SECONDS: int = int(os.environ.get("CHECK_INTERVAL_SECONDS", "300"))

# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------
MAX_RETRIES: int = int(os.environ.get("MAX_RETRIES", "4"))

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# Private directory for auth state — outside repo on production
# On local dev, falls back to data/ inside project
_DEFAULT_PRIVATE_DIR = str(_PROJECT_ROOT / "data")
PRIVATE_DIR: Path = Path(os.environ.get("PRIVATE_DIR", _DEFAULT_PRIVATE_DIR))

AUTH_STATE_PATH: Path = PRIVATE_DIR / "auth-state.json"
STATE_FILE_PATH: Path = PRIVATE_DIR / "state.json"
HEALTH_FILE_PATH: Path = PRIVATE_DIR / "health.json"

# Debug output directory (gitignored, sensitive)
DEBUG_DIR: Path = _PROJECT_ROOT / "data" / "debug"


def validate_telegram_config() -> bool:
    """Return True if Telegram credentials are configured."""
    return bool(TELEGRAM_BOT_TOKEN) and bool(TELEGRAM_CHAT_ID)


def validate_auth_state() -> bool:
    """Return True if a saved authentication state file exists."""
    return AUTH_STATE_PATH.is_file()
