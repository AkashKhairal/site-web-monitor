"""
Main monitoring loop for Site Web Monitor.

Periodically checks the SITE WEB dashboard card, detects count changes,
fetches new history entries, and sends Telegram notifications.

Usage:
    python -m app.main              # Normal monitoring
    python -m app.main --dry-run    # Log but don't send Telegram
    python -m app.main --debug      # Debug mode with verbose logging
"""

import argparse
import asyncio
import logging
import signal
import sys
import os
from typing import Optional

# Ensure project root is on sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from app.auth import BrowserManager
from app.config import (
    AUTH_STATE_PATH,
    CHECK_INTERVAL_SECONDS,
    DEBUG_DIR,
    MAX_RETRIES,
    validate_auth_state,
    validate_telegram_config,
)
from app.dashboard import (
    AuthenticationError,
    ExtractionError,
    get_site_web_status,
    navigate_to_dashboard,
)
from app.history import WebsiteEntry, get_new_entries, navigate_to_history
from app.logging_config import setup_logging
from app.notifier import notify_auth_failure, notify_error, notify_new_entries
from app.state import (
    MonitorState,
    load_state,
    save_state,
    update_state_baseline,
)

logger = logging.getLogger(__name__)


class Monitor:
    """Main monitoring service."""

    def __init__(
        self,
        *,
        dry_run: bool = False,
        debug: bool = False,
        once: bool = False,
    ) -> None:
        self.dry_run = dry_run
        self.debug = debug
        self.once = once
        self.bm: Optional[BrowserManager] = None
        self.state: Optional[MonitorState] = None
        self._shutdown = False
        self._consecutive_errors = 0
        # Dedup for operational error notifications
        self._last_error_notified: Optional[str] = None

    async def start(self) -> None:
        """Start the monitoring service."""
        logger.info("=" * 60)
        logger.info("Site Web Monitor starting")
        logger.info("  Dry run: %s", self.dry_run)
        logger.info("  Debug: %s", self.debug)
        logger.info("  Check interval: %ds", CHECK_INTERVAL_SECONDS)
        logger.info("  Auth state: %s", AUTH_STATE_PATH)
        logger.info("  Telegram configured: %s", validate_telegram_config())
        logger.info("=" * 60)

        # Validate prerequisites
        if not validate_auth_state():
            logger.error(
                "No authentication state found. "
                "Run 'python -m setup.auth_setup' first."
            )
            return

        if not validate_telegram_config() and not self.dry_run:
            logger.warning(
                "Telegram is not configured. Notifications will fail. "
                "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env"
            )

        # Load persistent state
        self.state = load_state()

        if self.once:
            # Single check cycle for CI/CD (e.g., GitHub Actions)
            await self._run_single_cycle()
        else:
            # Continuous monitoring loop
            self._setup_signal_handlers()
            await self._monitor_loop()

    def _setup_signal_handlers(self) -> None:
        """Register handlers for graceful shutdown."""
        loop = asyncio.get_event_loop()

        def handle_signal(signum, frame):
            sig_name = signal.Signals(signum).name
            logger.info("Received %s — shutting down gracefully...", sig_name)
            self._shutdown = True

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

    async def _ensure_browser(self) -> None:
        """Ensure a browser is running, restarting if needed."""
        if self.bm is not None and self.bm.page is not None:
            # Check if browser is still alive
            try:
                await self.bm.page.evaluate("() => true")
                return
            except Exception:
                logger.warning("Browser appears crashed — restarting")
                await self._close_browser()

        logger.info("Starting browser...")
        self.bm = BrowserManager()
        headless = not self.debug
        await self.bm.start_authenticated(headless=headless)

    async def _close_browser(self) -> None:
        """Safely close the browser."""
        if self.bm is not None:
            try:
                await self.bm.close()
            except Exception as exc:
                logger.warning("Error closing browser: %s", exc)
            self.bm = None

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while not self._shutdown:
            try:
                await self._run_check_cycle()
                self._consecutive_errors = 0
                self._last_error_notified = None

            except AuthenticationError as exc:
                logger.error("Authentication failure: %s", exc)
                await self._handle_auth_failure()

            except ExtractionError as exc:
                logger.error("Extraction failure: %s", exc)
                self._consecutive_errors += 1
                await self._handle_extraction_error(str(exc))

            except Exception as exc:
                logger.exception("Unexpected error in monitoring cycle")
                self._consecutive_errors += 1
                await self._handle_unexpected_error(str(exc))

            if self._shutdown:
                break

            # Calculate wait time with backoff on errors
            wait_time = self._get_wait_time()
            logger.info("Next check in %d seconds", wait_time)
            await self._interruptible_sleep(wait_time)

        # Graceful shutdown
        logger.info("Shutting down...")
        await self._close_browser()
        if self.state is not None:
            save_state(self.state)
        logger.info("Shutdown complete")

    async def _run_single_cycle(self) -> None:
        """Run exactly one check cycle, then exit.

        Used for CI/CD environments (e.g., GitHub Actions) where the
        monitor runs on a schedule rather than as a persistent loop.
        All errors are handled gracefully so the process always exits
        cleanly and state is always saved.
        """
        logger.info("Running single check cycle (--once mode)")

        try:
            await self._ensure_browser()
            await self._run_check_cycle()
            logger.info("Single check cycle completed successfully")

        except AuthenticationError as exc:
            logger.error("Authentication failure: %s", exc)
            await self._handle_auth_failure()

        except ExtractionError as exc:
            logger.error("Extraction failure: %s", exc)
            await self._handle_extraction_error(str(exc))

        except Exception as exc:
            logger.exception("Unexpected error in monitoring cycle")
            await self._handle_unexpected_error(str(exc))

        finally:
            await self._close_browser()
            if self.state is not None:
                save_state(self.state)
                logger.info("State saved")
            logger.info("Single cycle done — exiting")

    async def _run_check_cycle(self) -> None:
        """Execute one monitoring check cycle."""
        logger.info("--- Monitoring cycle start ---")

        await self._ensure_browser()
        page = self.bm.page

        # Navigate to dashboard and get SITE WEB count
        await navigate_to_dashboard(page)
        status = await get_site_web_status(page)

        current_count = status.count
        logger.info(
            "SITE WEB count: current=%d, previous=%d",
            current_count, self.state.last_count,
        )

        # First run: establish baseline, no alerts
        if self.state.is_first_run:
            logger.info(
                "First run — establishing baseline (count=%d). No alerts.",
                current_count,
            )
            await navigate_to_history(page)
            from app.history import get_all_visible_entries
            all_entries = await get_all_visible_entries(page)
            all_ids = {e.entry_id for e in all_entries}

            latest = all_entries[0] if all_entries else None
            update_state_baseline(
                self.state,
                count=current_count,
                entry_ids=all_ids,
                latest_website=latest.website if latest else None,
                latest_timestamp=latest.timestamp if latest else None,
            )
            save_state(self.state)
            logger.info("Baseline established with %d seen entry IDs", len(all_ids))
            return

        # Check for new activity
        #
        # IMPORTANT: The dashboard count resets to 0 whenever sites.php is
        # opened (i.e., after we view the history page). This means the
        # typical cycle is:
        #   count=0 → new activity → count=3 → we open history → count=0
        #
        # Our primary dedup key is seen_entry_ids, NOT the count.
        # The count is just a trigger to check history.
        #
        if current_count > 0 and current_count > self.state.last_count:
            increase = current_count - self.state.last_count
            logger.info(
                "Count increased by %d (from %d to %d) — checking history",
                increase, self.state.last_count, current_count,
            )
            await self._process_new_entries(page, current_count)

        elif current_count == 0 and self.state.last_count > 0:
            # Count reset to 0 after we opened sites.php — this is normal
            logger.info(
                "Count reset to 0 (was %d) — normal after viewing history",
                self.state.last_count,
            )
            self.state.last_count = 0
            save_state(self.state)

        elif current_count == self.state.last_count:
            logger.info("No change in count (%d) — nothing to do", current_count)

        elif current_count < self.state.last_count:
            logger.warning(
                "Count decreased from %d to %d — possible data reset. "
                "Updating baseline.",
                self.state.last_count, current_count,
            )
            # Re-baseline on count decrease (e.g., data was deleted)
            self.state.last_count = current_count
            save_state(self.state)

    async def _process_new_entries(self, page, current_count: int) -> None:
        """Navigate to history and process any new entries."""
        await navigate_to_history(page)
        new_entries = await get_new_entries(page, self.state.seen_entry_ids)

        if not new_entries:
            logger.info(
                "Count increased but no new entries found by ID. "
                "Updating count baseline."
            )
            self.state.last_count = current_count
            save_state(self.state)
            return

        logger.info("Found %d new entries to process", len(new_entries))

        # Sort by entry_id (ascending) so we process oldest first
        new_entries.sort(key=lambda e: int(e.entry_id) if e.entry_id.isdigit() else 0)

        # Send notification — only update state after confirmed delivery
        notification_sent = await notify_new_entries(
            new_entries, current_count, dry_run=self.dry_run
        )

        if notification_sent:
            new_ids = {e.entry_id for e in new_entries}
            latest = new_entries[-1]  # Most recent after sorting
            update_state_baseline(
                self.state,
                count=current_count,
                entry_ids=new_ids,
                latest_website=latest.website,
                latest_timestamp=latest.timestamp,
            )
            save_state(self.state)
            logger.info(
                "State updated: count=%d, total seen IDs=%d",
                current_count, len(self.state.seen_entry_ids),
            )
        else:
            # Telegram failed — do NOT update state (§35)
            logger.warning(
                "Telegram notification failed — state NOT updated. "
                "Will retry on next cycle."
            )

    async def _handle_auth_failure(self) -> None:
        """Handle authentication failure with deduplication."""
        if not self.state.auth_failure_notified:
            sent = await notify_auth_failure(dry_run=self.dry_run)
            if sent:
                self.state.auth_failure_notified = True
                save_state(self.state)
                logger.info("Auth failure notification sent")
        else:
            logger.debug("Auth failure already notified — skipping duplicate")

        # Close browser since session is invalid
        await self._close_browser()

    async def _handle_extraction_error(self, error_msg: str) -> None:
        """Handle extraction errors with alert deduplication."""
        if self.debug:
            await self._save_debug_snapshot()

        # Only notify once per unique error
        if error_msg != self._last_error_notified:
            await notify_error(
                f"Dashboard extraction failed: {error_msg[:200]}",
                dry_run=self.dry_run,
            )
            self._last_error_notified = error_msg

    async def _handle_unexpected_error(self, error_msg: str) -> None:
        """Handle unexpected errors."""
        # Close browser on unexpected errors to get a clean restart
        await self._close_browser()

        if error_msg != self._last_error_notified:
            await notify_error(
                f"Unexpected monitor error: {error_msg[:200]}",
                dry_run=self.dry_run,
            )
            self._last_error_notified = error_msg

    async def _save_debug_snapshot(self) -> None:
        """Save screenshot and HTML for debugging (only in debug mode)."""
        if self.bm and self.bm.page:
            try:
                DEBUG_DIR.mkdir(parents=True, exist_ok=True)
                await self.bm.page.screenshot(
                    path=str(DEBUG_DIR / "debug_screenshot.png"), full_page=True
                )
                html = await self.bm.page.content()
                (DEBUG_DIR / "debug_page.html").write_text(html, encoding="utf-8")
                logger.debug("Debug snapshot saved to %s", DEBUG_DIR)
            except Exception as exc:
                logger.warning("Failed to save debug snapshot: %s", exc)

    def _get_wait_time(self) -> int:
        """Calculate wait time with exponential backoff on errors."""
        if self._consecutive_errors == 0:
            return CHECK_INTERVAL_SECONDS

        # Exponential backoff: 5s, 15s, 30s, then cap at normal interval
        backoff_times = [5, 15, 30]
        idx = min(self._consecutive_errors - 1, len(backoff_times) - 1)

        if self._consecutive_errors <= len(backoff_times):
            return backoff_times[idx]
        else:
            # After retries exhausted, fall back to normal interval
            return CHECK_INTERVAL_SECONDS

    async def _interruptible_sleep(self, seconds: int) -> None:
        """Sleep that can be interrupted by shutdown signal."""
        try:
            for _ in range(seconds):
                if self._shutdown:
                    return
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            return


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Site Web Monitor — monitors the SITE WEB dashboard card",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log what would be sent but don't actually send Telegram messages",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging and headed browser",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single check cycle and exit (for CI/CD environments)",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point for `python -m app.main`."""
    args = parse_args()
    setup_logging(debug=args.debug)

    monitor = Monitor(dry_run=args.dry_run, debug=args.debug, once=args.once)
    asyncio.run(monitor.start())


if __name__ == "__main__":
    main()
