"""
SITE WEB history page extraction for Site Web Monitor.

Navigates to the history page (sites.php) and extracts website entries
from the DataTable. Uses stable entry IDs from checkbox values for
deduplication.

Selectors are based on real DOM inspection (confirmed in Phase 6):
  - Table: #tabData
  - Entry ID: input.checkboxes value attribute (stable database IDs)
  - URL: 2nd <td> in each row
  - Timestamp: 4th <td> (td.sorting_1) in each row
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Set

from playwright.async_api import Page

from app.dashboard import ExtractionError, get_history_url

logger = logging.getLogger(__name__)

# Stable selectors discovered from real DOM inspection
HISTORY_TABLE_SELECTOR = "#tabData"
HISTORY_ROW_SELECTOR = "#tabData tbody tr[role='row']"
CHECKBOX_SELECTOR = "input.checkboxes"


@dataclass
class WebsiteEntry:
    """A single website history entry."""
    entry_id: str              # Stable database ID from checkbox value
    website: str               # URL/domain
    timestamp: Optional[str] = None  # Format: "2026/08/24 18:02:02"
    browser: Optional[str] = None    # e.g., "Chrome"


async def _show_all_entries(page: Page) -> None:
    """Select 'Show All' in the DataTable pagination dropdown.

    DataTables typically show 10 entries per page by default.
    This selects the highest available option (e.g., 100, All, -1)
    to ensure we can see every entry in the table.
    """
    try:
        # DataTables uses a <select> element with name="tabData_length"
        # or class "dataTables_length" to control entries per page.
        length_select = await page.query_selector(
            "select[name='tabData_length'], "
            "#tabData_length select, "
            ".dataTables_length select"
        )
        if length_select is None:
            logger.debug("No DataTable length selector found — table may show all entries already")
            return

        # Get all available options
        options = await length_select.query_selector_all("option")
        if not options:
            logger.debug("No options in length selector")
            return

        # Find the best option: prefer -1 (Show All), otherwise pick the largest value
        best_value = None
        best_numeric = 0
        for opt in options:
            value = await opt.get_attribute("value")
            if value == "-1":
                # -1 is the standard DataTables value for "Show All"
                best_value = "-1"
                break
            try:
                num = int(value)
                if num > best_numeric:
                    best_numeric = num
                    best_value = value
            except (ValueError, TypeError):
                continue

        if best_value:
            await length_select.select_option(best_value)
            # Wait for DataTable to re-render after changing page length
            await page.wait_for_timeout(1000)
            await page.wait_for_load_state("networkidle")
            logger.info("DataTable set to show %s entries", "all" if best_value == "-1" else best_value)
        else:
            logger.debug("Could not determine best page length option")

    except Exception as exc:
        # Non-fatal: if we can't change pagination, we still extract what's visible
        logger.warning("Could not change DataTable page length: %s", exc)


async def get_all_visible_entries(page: Page) -> List[WebsiteEntry]:
    """Extract all visible entries from the history table.

    Returns:
        List of WebsiteEntry objects, ordered as they appear in the table
        (typically newest first when sorted by date descending).

    Raises:
        ExtractionError: If the table cannot be found or parsed.
            Never silently returns an empty list when the table is missing.
    """
    # Verify table exists
    table = await page.query_selector(HISTORY_TABLE_SELECTOR)
    if table is None:
        raise ExtractionError(
            f"Could not find history table (selector: {HISTORY_TABLE_SELECTOR}). "
            "The history page HTML structure may have changed."
        )

    # Show all entries (DataTable defaults to 10 per page)
    await _show_all_entries(page)

    # Get all data rows (skip header row)
    rows = await page.query_selector_all(HISTORY_ROW_SELECTOR)
    logger.debug("Found %d rows in history table", len(rows))

    entries: List[WebsiteEntry] = []

    for i, row in enumerate(rows):
        try:
            # Extract stable entry ID from checkbox value
            checkbox = await row.query_selector(CHECKBOX_SELECTOR)
            if checkbox is None:
                logger.warning("Row %d has no checkbox — skipping", i)
                continue

            entry_id = await checkbox.get_attribute("value")
            if not entry_id:
                logger.warning("Row %d checkbox has no value — skipping", i)
                continue

            # Extract cells
            cells = await row.query_selector_all("td")
            if len(cells) < 4:
                logger.warning(
                    "Row %d has only %d cells (expected 4+) — skipping",
                    i, len(cells),
                )
                continue

            # Cell 0: checkbox (already processed)
            # Cell 1: URL
            website = (await cells[1].inner_text()).strip()
            # Cell 2: Browser
            browser = (await cells[2].inner_text()).strip()
            # Cell 3: Date/timestamp
            timestamp = (await cells[3].inner_text()).strip()

            entry = WebsiteEntry(
                entry_id=entry_id,
                website=website,
                timestamp=timestamp if timestamp else None,
                browser=browser if browser else None,
            )
            entries.append(entry)
            logger.debug(
                "Entry %d: id=%s url=%s time=%s",
                i, entry_id, website[:60], timestamp,
            )

        except Exception as exc:
            logger.warning("Error extracting row %d: %s", i, exc)
            continue

    logger.info("Extracted %d entries from history table", len(entries))
    return entries


async def get_new_entries(
    page: Page,
    seen_ids: Set[str],
) -> List[WebsiteEntry]:
    """Get entries that have not been seen before.

    Args:
        page: Playwright page (should be on the history page).
        seen_ids: Set of previously seen entry IDs.

    Returns:
        List of new (unseen) WebsiteEntry objects.
    """
    all_entries = await get_all_visible_entries(page)

    new_entries = [
        entry for entry in all_entries
        if entry.entry_id not in seen_ids
    ]

    if new_entries:
        logger.info(
            "Found %d new entries (out of %d visible)",
            len(new_entries), len(all_entries),
        )
    else:
        logger.debug("No new entries found among %d visible", len(all_entries))

    return new_entries


async def navigate_to_history(page: Page) -> None:
    """Navigate to the SITE WEB history page.

    Raises:
        ExtractionError: If navigation fails or table is not found.
    """
    history_url = get_history_url()
    logger.info("Navigating to history page: %s", history_url)

    await page.goto(history_url, wait_until="domcontentloaded")
    await page.wait_for_load_state("networkidle")

    # Verify we're on the right page
    current_url = page.url
    if "/login" in current_url.lower():
        from app.auth import AuthenticationError, login
        from app.config import MTF_EMAIL, MTF_PASSWORD

        if MTF_EMAIL and MTF_PASSWORD:
            logger.info("Session expired while accessing history — re-authenticating...")
            await login(page, MTF_EMAIL, MTF_PASSWORD)
            await page.goto(history_url, wait_until="domcontentloaded")
            await page.wait_for_load_state("networkidle")
        else:
            raise AuthenticationError(
                "Redirected to login while accessing history page."
            )

    logger.debug("History page loaded at: %s", page.url)

