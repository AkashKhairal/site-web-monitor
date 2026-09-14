"""
Browser lifecycle management for Site Web Monitor.

Provides helpers to launch Chromium via Playwright, create authenticated
browser contexts using saved storage state, and manage the browser lifecycle.
"""

import logging
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from app.config import (
    AUTH_STATE_PATH,
    MTF_EMAIL,
    MTF_PASSWORD,
    TARGET_LOGIN_URL,
)

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Raised when authentication fails or session expires."""
    pass


async def login(
    page: Page,
    email: Optional[str] = None,
    password: Optional[str] = None,
) -> None:
    """Perform automated login to Mobile Tracker Free.

    Args:
        page: Active Playwright Page instance.
        email: Optional email override; defaults to MTF_EMAIL.
        password: Optional password override; defaults to MTF_PASSWORD.

    Raises:
        AuthenticationError: If login fails or credentials are invalid.
    """
    user_email = email or MTF_EMAIL
    user_pass = password or MTF_PASSWORD
    if not user_email or not user_pass:
        raise AuthenticationError(
            "Automated login failed: MTF_EMAIL or MTF_PASSWORD not configured."
        )

    logger.info("Performing automated login for %s", user_email)
    await page.goto(TARGET_LOGIN_URL, wait_until="domcontentloaded")

    # Wait for the login form elements
    try:
        await page.wait_for_selector("#email", timeout=15000)
        await page.fill("#email", user_email)
        await page.fill("#password", user_pass)
        await page.click("#btnLogin")
    except Exception as exc:
        raise AuthenticationError(f"Error submitting login form: {exc}") from exc

    # Wait for navigation away from login (to dashboard or authenticated route)
    try:
        await page.wait_for_url(lambda u: "/login" not in u.lower(), timeout=20000)
    except Exception as exc:
        error_msg = ""
        try:
            error_elem = await page.query_selector("#errorLogin")
            if error_elem:
                error_msg = (await error_elem.inner_text()).strip()
        except Exception:
            pass

        if error_msg:
            raise AuthenticationError(f"Login rejected by website: {error_msg}") from exc
        raise AuthenticationError(
            f"Timed out waiting for login redirect. Current URL: {page.url}"
        ) from exc

    await page.wait_for_load_state("networkidle")
    logger.info("Automated login successful. Current URL: %s", page.url)


class BrowserManager:
    """Manages Playwright browser lifecycle.

    Maintains a single Playwright instance, browser, context, and page.
    Supports creating authenticated contexts from saved storage state
    or performing automated credential-based login.
    """

    def __init__(self) -> None:
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def start(
        self,
        *,
        headless: bool = True,
        storage_state: Optional[Path] = None,
    ) -> Page:
        """Launch the browser and return a page.

        Args:
            headless: Run Chromium in headless mode (True for production).
            storage_state: Path to Playwright storage state JSON for
                authenticated sessions. If None, starts unauthenticated.

        Returns:
            A ready-to-use Playwright Page.
        """
        logger.info("Starting Playwright and launching Chromium (headless=%s)", headless)

        self._playwright = await async_playwright().start()

        self._browser = await self._playwright.chromium.launch(
            headless=headless,
        )

        # Build context kwargs
        context_kwargs: dict = {}
        if storage_state and storage_state.is_file():
            logger.info("Loading authentication state from saved storage")
            context_kwargs["storage_state"] = str(storage_state)

        self._context = await self._browser.new_context(**context_kwargs)
        self._page = await self._context.new_page()

        logger.info("Browser started successfully")
        return self._page

    async def start_authenticated(self, *, headless: bool = True) -> Page:
        """Launch the browser with automated login or saved authentication state.

        If MTF_EMAIL and MTF_PASSWORD are configured, performs automated login.
        Otherwise, falls back to saved storage state in AUTH_STATE_PATH.

        Raises:
            FileNotFoundError: If neither credentials nor saved auth state exists.
        """
        has_creds = bool(MTF_EMAIL and MTF_PASSWORD)
        has_state = AUTH_STATE_PATH.is_file()

        if not has_creds and not has_state:
            raise FileNotFoundError(
                f"No credentials (MTF_EMAIL/MTF_PASSWORD) or authentication state found at {AUTH_STATE_PATH}. "
                "Set MTF_EMAIL and MTF_PASSWORD or run 'python -m setup.auth_setup' first."
            )

        if has_creds:
            # Fresh automated login with credentials
            page = await self.start(headless=headless)
            await login(page, MTF_EMAIL, MTF_PASSWORD)
            await self.save_storage_state(AUTH_STATE_PATH)
            return page

        # Fallback to saved storage state
        return await self.start(headless=headless, storage_state=AUTH_STATE_PATH)

    async def save_storage_state(self, path: Optional[Path] = None) -> None:
        """Save the current browser context's storage state.

        Args:
            path: Where to save. Defaults to AUTH_STATE_PATH.
        """
        if self._context is None:
            raise RuntimeError("No browser context to save state from.")

        target = path or AUTH_STATE_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        await self._context.storage_state(path=str(target))
        logger.info("Storage state saved successfully")

    async def close(self) -> None:
        """Cleanly close all browser resources."""
        for resource_name, resource in [
            ("page", self._page),
            ("context", self._context),
            ("browser", self._browser),
        ]:
            if resource is not None:
                try:
                    await resource.close()
                except Exception as exc:
                    logger.warning("Error closing %s: %s", resource_name, exc)

        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception as exc:
                logger.warning("Error stopping Playwright: %s", exc)

        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        logger.info("Browser resources closed")

    @property
    def page(self) -> Optional[Page]:
        """The current page, or None if not started."""
        return self._page

    @property
    def context(self) -> Optional[BrowserContext]:
        """The current browser context, or None if not started."""
        return self._context

    @property
    def browser(self) -> Optional[Browser]:
        """The current browser, or None if not started."""
        return self._browser
