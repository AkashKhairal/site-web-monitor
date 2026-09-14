"""
Dashboard monitoring for Site Web Monitor.

Navigates to the authenticated dashboard and extracts the SITE WEB card count.
Selectors are based on real DOM inspection (confirmed in Phase 4):
  - Count: #siteHistoryData (stable HTML id)
  - Card: a.dashboard-stat[href="sites.php"] with .desc containing "Site Web"
  - History URL: sites.php (relative to dashboard)
"""

import logging
from dataclasses import dataclass
from typing import Optional

from playwright.async_api import Page

from app.auth import AuthenticationError, login
from app.config import MTF_EMAIL, MTF_PASSWORD, TARGET_DASHBOARD_URL

logger = logging.getLogger(__name__)

# Stable selectors discovered from real DOM inspection
SITE_WEB_COUNT_SELECTOR = "#siteHistoryData"
SITE_WEB_CARD_SELECTOR = 'a.dashboard-stat[href="sites.php"]'
SITE_WEB_HISTORY_URL = "sites.php"


class ExtractionError(Exception):
    """Raised when SITE WEB data cannot be extracted from the dashboard.

    This is NOT equivalent to count=0. A scraper failure must never be
    silently converted to zero (CLAUDE.md §34).
    """
    pass


@dataclass
class SiteWebStatus:
    """Result of a dashboard check."""
    count: int
    raw_text: Optional[str] = None
    is_authenticated: bool = True


async def check_authentication(page: Page) -> bool:
    """Check if the current page indicates an authenticated session.

    Returns True if authenticated, False if redirected to login.
    """
    current_url = page.url.lower()
    if "/login" in current_url:
        logger.warning("Session appears expired — redirected to login page")
        return False

    try:
        # If login form email field is present, we are logged out
        login_input = await page.query_selector("#email")
        if login_input:
            logger.warning("Session appears expired — login form detected")
            return False
    except Exception:
        pass

    return True


async def navigate_to_dashboard(page: Page) -> None:
    """Navigate to the dashboard and wait for it to load.

    Raises:
        AuthenticationError: If the session has expired and cannot be restored.
    """
    logger.info("Navigating to dashboard")
    await page.goto(TARGET_DASHBOARD_URL, wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle")

    if not await check_authentication(page):
        if MTF_EMAIL and MTF_PASSWORD:
            logger.info("Session expired — performing automated re-login...")
            await login(page, MTF_EMAIL, MTF_PASSWORD)
            await page.goto(TARGET_DASHBOARD_URL, wait_until="domcontentloaded")
            await page.wait_for_load_state("networkidle")
        else:
            raise AuthenticationError(
                "Session expired — redirected to login page. "
                "Run 'python -m setup.auth_setup' or configure MTF credentials."
            )

    logger.debug("Dashboard loaded successfully at: %s", page.url)


async def get_site_web_status(page: Page) -> SiteWebStatus:
    """Extract the SITE WEB count from the dashboard.

    The page must already be on the dashboard.

    Returns:
        SiteWebStatus with the current count.

    Raises:
        AuthenticationError: If the session has expired.
        ExtractionError: If the SITE WEB count cannot be extracted.
            NEVER defaults to 0 on failure.
    """
    # Verify we're still authenticated
    if not await check_authentication(page):
        if MTF_EMAIL and MTF_PASSWORD:
            logger.info("Session expired before extraction — re-authenticating...")
            await login(page, MTF_EMAIL, MTF_PASSWORD)
            await page.goto(TARGET_DASHBOARD_URL, wait_until="domcontentloaded")
            await page.wait_for_load_state("networkidle")
        else:
            raise AuthenticationError("Session expired during dashboard check.")

    # Locate the count element by its stable ID
    count_element = await page.query_selector(SITE_WEB_COUNT_SELECTOR)

    if count_element is None:
        # Check if the page actually booted us back to login
        if not await check_authentication(page):
            if MTF_EMAIL and MTF_PASSWORD:
                logger.info("Count element missing due to login redirect — re-authenticating...")
                await login(page, MTF_EMAIL, MTF_PASSWORD)
                await page.goto(TARGET_DASHBOARD_URL, wait_until="domcontentloaded")
                await page.wait_for_load_state("networkidle")
                count_element = await page.query_selector(SITE_WEB_COUNT_SELECTOR)
            else:
                raise AuthenticationError("Session expired during dashboard check.")

    if count_element is None:
        raise ExtractionError(
            f"Could not find SITE WEB count element "
            f"(selector: {SITE_WEB_COUNT_SELECTOR}). "
            "The dashboard HTML structure may have changed."
        )


    # Extract the raw text
    raw_text = await count_element.inner_text()
    raw_text = raw_text.strip()
    logger.debug("SITE WEB raw text: %r", raw_text)

    # Parse as integer — NEVER default to 0
    try:
        count = int(raw_text)
    except (ValueError, TypeError) as exc:
        raise ExtractionError(
            f"SITE WEB count is not a valid integer: {raw_text!r}. "
            "The dashboard may have changed or failed to load."
        ) from exc

    # Sanity check: verify the card label says "Site Web"
    card_element = await page.query_selector(SITE_WEB_CARD_SELECTOR)
    if card_element is not None:
        card_text = await card_element.inner_text()
        if "site web" not in card_text.lower():
            logger.warning(
                "SITE WEB card text does not contain 'Site Web': %r. "
                "Proceeding with count from #siteHistoryData.",
                card_text.strip(),
            )
    else:
        logger.warning(
            "Could not find SITE WEB card container for validation "
            "(selector: %s). Count extracted from #siteHistoryData: %d",
            SITE_WEB_CARD_SELECTOR,
            count,
        )

    logger.info("SITE WEB count: %d", count)
    return SiteWebStatus(count=count, raw_text=raw_text)


def get_history_url() -> str:
    """Return the full URL for the SITE WEB history page."""
    base = TARGET_DASHBOARD_URL.rstrip("/")
    return f"{base}/{SITE_WEB_HISTORY_URL}"
