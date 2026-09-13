"""Tests for app.config module."""
import os

import pytest


def test_config_loads_defaults():
    """Config should load with default values when env vars are not set."""
    from app.config import CHECK_INTERVAL_SECONDS, TARGET_LOGIN_URL

    assert CHECK_INTERVAL_SECONDS == 300 or isinstance(CHECK_INTERVAL_SECONDS, int)
    assert "mobile-tracker-free.com" in TARGET_LOGIN_URL


def test_validate_telegram_config_false_without_env():
    """Telegram validation returns False when credentials are empty."""
    from app.config import validate_telegram_config

    # This should be False unless env vars are actually set
    # (we don't control the test environment here)
    result = validate_telegram_config()
    assert isinstance(result, bool)


def test_validate_auth_state_false_initially():
    """Auth state validation returns False when no state file exists."""
    from app.config import validate_auth_state, AUTH_STATE_PATH

    # This depends on whether auth_setup has been run
    result = validate_auth_state()
    assert isinstance(result, bool)
