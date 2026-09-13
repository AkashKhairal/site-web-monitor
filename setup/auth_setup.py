"""
Interactive authentication setup for Site Web Monitor.

Launches a headed Chromium browser, navigates to the login page, and waits
for the authorized user to log in manually. Once the dashboard is reached,
saves the Playwright storage state for later use by the monitoring service.

Usage:
    python -m setup.auth_setup

The user must manually enter credentials. This script does NOT automate
password entry, CAPTCHA solving, or MFA bypass.
"""

import asyncio
import logging
import os
import stat
import sys

# Ensure project root is on sys.path for imports
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from app.auth import BrowserManager
from app.config import AUTH_STATE_PATH, TARGET_LOGIN_URL
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)

# How long (seconds) to wait for the user to complete login
LOGIN_TIMEOUT_SECONDS = 300  # 5 minutes


async def run_auth_setup() -> None:
    """Run the interactive authentication setup workflow."""
    logger.info("=" * 60)
    logger.info("Site Web Monitor — Authentication Setup")
    logger.info("=" * 60)
    logger.info("")
    logger.info("A browser window will open to: %s", TARGET_LOGIN_URL)
    logger.info("Please log in manually using your authorized credentials.")
    logger.info("If CAPTCHA or MFA is required, complete it in the browser.")
    logger.info("")
    logger.info("Waiting up to %d seconds for login...", LOGIN_TIMEOUT_SECONDS)
    logger.info("")

    bm = BrowserManager()

    try:
        # Launch headed (visible) browser — user needs to see and interact
        page = await bm.start(headless=False)

        # Navigate to login page
        await page.goto(TARGET_LOGIN_URL, wait_until="domcontentloaded")
        logger.info("Login page loaded. Please log in now...")

        # Wait for the user to successfully authenticate.
        # We detect success by waiting for the URL to change away from
        # the login page, indicating a redirect to the dashboard or
        # another authenticated page.
        try:
            await page.wait_for_url(
                # Wait until URL no longer contains "/login"
                lambda url: "/login" not in url.lower(),
                timeout=LOGIN_TIMEOUT_SECONDS * 1000,
            )
        except Exception:
            logger.error(
                "Timed out waiting for login. Please try again and "
                "complete the login within %d seconds.",
                LOGIN_TIMEOUT_SECONDS,
            )
            return

        # Give the dashboard a moment to fully load
        await page.wait_for_load_state("networkidle")
        current_url = page.url
        logger.info("Login appears successful! Current URL: %s", current_url)

        # Save storage state
        AUTH_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        await bm.save_storage_state(AUTH_STATE_PATH)

        # Set restrictive file permissions (Unix-like systems)
        try:
            os.chmod(AUTH_STATE_PATH, stat.S_IRUSR | stat.S_IWUSR)  # 600
            logger.info("Set restrictive permissions (600) on auth state file")
        except OSError:
            # Windows doesn't support chmod the same way — that's fine for dev
            logger.debug(
                "Could not set Unix file permissions (expected on Windows)"
            )

        logger.info("")
        logger.info("=" * 60)
        logger.info("✅ Authentication state saved successfully!")
        logger.info("   Path: %s", AUTH_STATE_PATH)
        logger.info("")
        logger.info("You can now run the monitor with:")
        logger.info("   python -m app.main")
        logger.info("=" * 60)

    except Exception:
        logger.exception("Authentication setup failed with an unexpected error")
        raise
    finally:
        await bm.close()


def main() -> None:
    """Entry point for `python -m setup.auth_setup`."""
    setup_logging()
    asyncio.run(run_auth_setup())


if __name__ == "__main__":
    main()
