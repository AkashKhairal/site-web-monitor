"""Tests for --once flag and single-cycle mode."""
import sys
from unittest.mock import AsyncMock, patch

import pytest

from app.main import Monitor, parse_args


def test_parse_args_once_flag():
    """Verify --once flag is parsed correctly."""
    with patch.object(sys, "argv", ["app.main", "--once"]):
        args = parse_args()
        assert args.once is True
        assert args.dry_run is False
        assert args.debug is False


def test_parse_args_default():
    """Verify default args have once=False."""
    with patch.object(sys, "argv", ["app.main"]):
        args = parse_args()
        assert args.once is False


def test_monitor_init_once():
    """Verify Monitor respects once parameter."""
    monitor = Monitor(once=True, dry_run=True)
    assert monitor.once is True
    assert monitor.dry_run is True


def test_monitor_start_calls_single_cycle():
    """Verify start() branches to _run_single_cycle when once=True."""
    import asyncio

    monitor = Monitor(once=True, dry_run=True)

    with patch("app.main.validate_auth_state", return_value=True), \
         patch("app.main.validate_telegram_config", return_value=True), \
         patch("app.main.load_state"), \
         patch.object(monitor, "_run_single_cycle", new_callable=AsyncMock) as mock_single, \
         patch.object(monitor, "_monitor_loop", new_callable=AsyncMock) as mock_loop:

        asyncio.run(monitor.start())

        mock_single.assert_awaited_once()
        mock_loop.assert_not_awaited()

