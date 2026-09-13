"""
History page DOM inspection script for Site Web Monitor.

Loads authentication state, navigates to the SITE WEB history page
(sites.php), and dumps DOM structure to discover entry selectors.

Output is saved to data/debug/ (gitignored, sensitive).

Usage:
    python -m setup.inspect_history

IMPORTANT: Run setup.auth_setup first to create the auth state.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from app.auth import BrowserManager
from app.config import DEBUG_DIR
from app.dashboard import get_history_url
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)


async def inspect_history() -> None:
    """Navigate to the history page and dump DOM information."""

    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    history_url = get_history_url()

    bm = BrowserManager()
    try:
        page = await bm.start_authenticated(headless=True)

        logger.info("Navigating to SITE WEB history page: %s", history_url)
        await page.goto(history_url, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")

        current_url = page.url
        logger.info("Current URL: %s", current_url)

        # Check auth
        if "/login" in current_url.lower():
            logger.error("Redirected to login — session expired.")
            return

        # --- Full HTML ---
        html = await page.content()
        html_path = DEBUG_DIR / "history_full.html"
        html_path.write_text(html, encoding="utf-8")
        logger.info("Full HTML saved to: %s (%d bytes)", html_path, len(html))

        # --- Text content ---
        text = await page.inner_text("body")
        text_path = DEBUG_DIR / "history_text.txt"
        text_path.write_text(text, encoding="utf-8")
        logger.info("Text content saved to: %s", text_path)

        # --- Screenshot ---
        screenshot_path = DEBUG_DIR / "history_screenshot.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)
        logger.info("Screenshot saved to: %s", screenshot_path)

        # --- Search for table/list structures ---
        logger.info("")
        logger.info("=" * 60)
        logger.info("Analyzing history page structure...")
        logger.info("=" * 60)

        # Look for tables
        tables = await page.query_selector_all("table")
        logger.info("Found %d <table> elements", len(tables))

        for i, table in enumerate(tables):
            table_html = await table.evaluate("el => el.outerHTML.substring(0, 2000)")
            table_id = await table.get_attribute("id")
            table_class = await table.get_attribute("class")
            logger.info("")
            logger.info("--- Table %d ---", i + 1)
            logger.info("  id=%r  class=%r", table_id, table_class)
            logger.info("  HTML (first 2000 chars):")
            logger.info("  %s", table_html)

            # Get headers
            headers = await table.query_selector_all("th")
            if headers:
                header_texts = []
                for h in headers:
                    ht = await h.inner_text()
                    header_texts.append(ht.strip())
                logger.info("  Headers: %s", header_texts)

            # Get first few rows
            rows = await table.query_selector_all("tr")
            logger.info("  Total rows: %d", len(rows))
            for j, row in enumerate(rows[:5]):  # First 5 rows
                row_html = await row.evaluate("el => el.outerHTML.substring(0, 1000)")
                logger.info("  Row %d: %s", j, row_html)

        # --- Look for list-based structures ---
        lists_info = await page.evaluate("""() => {
            const results = [];

            // Check for DataTables
            const dtables = document.querySelectorAll('.dataTable, [id*="DataTable"], [id*="datatable"]');
            dtables.forEach(t => {
                results.push({
                    type: 'datatable',
                    id: t.id || null,
                    className: t.className || null,
                    rows: t.querySelectorAll('tr').length,
                    html: t.outerHTML.substring(0, 3000)
                });
            });

            // Check for any element with history-like data attributes
            const dataEls = document.querySelectorAll('[data-id], [data-entry], [data-row]');
            dataEls.forEach(el => {
                results.push({
                    type: 'data-element',
                    tag: el.tagName,
                    id: el.id || null,
                    dataId: el.getAttribute('data-id'),
                    dataEntry: el.getAttribute('data-entry'),
                    html: el.outerHTML.substring(0, 500)
                });
            });

            return results;
        }""")

        if lists_info:
            logger.info("")
            logger.info("--- Data structures found ---")
            for item in lists_info:
                logger.info("  Type: %s", item.get("type"))
                logger.info("  ID: %s", item.get("id"))
                logger.info("  Class: %s", item.get("className"))
                if item.get("rows"):
                    logger.info("  Rows: %d", item["rows"])
                logger.info("  HTML: %s", item.get("html", "")[:500])
                logger.info("")

        # --- Extract all links on the page ---
        links = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a[href]')).map(a => ({
                text: a.textContent.trim().substring(0, 100),
                href: a.href,
                id: a.id || null,
                className: a.className || null
            }));
        }""")
        links_path = DEBUG_DIR / "history_links.json"
        links_path.write_text(json.dumps(links, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Links (%d) saved to: %s", len(links), links_path)

        # --- Comprehensive element analysis ---
        # Look for any identifiers that could serve as stable entry IDs
        page_analysis = await page.evaluate("""() => {
            const body = document.body;
            const analysis = {
                title: document.title,
                mainContent: '',
                formElements: [],
                dataAttributes: [],
                idElements: []
            };

            // Get main content area
            const content = document.querySelector('.page-content, .content, main, #content');
            if (content) {
                analysis.mainContent = content.innerHTML.substring(0, 5000);
            }

            // Find all elements with id attributes in the main content area
            const idEls = (content || body).querySelectorAll('[id]');
            idEls.forEach(el => {
                if (el.id && !el.id.startsWith('_')) {
                    analysis.idElements.push({
                        id: el.id,
                        tag: el.tagName,
                        className: el.className || null,
                        textPreview: el.textContent.trim().substring(0, 100)
                    });
                }
            });

            return analysis;
        }""")

        analysis_path = DEBUG_DIR / "history_analysis.json"
        analysis_path.write_text(
            json.dumps(page_analysis, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("Page analysis saved to: %s", analysis_path)

        # Log the main content HTML
        main_content_path = DEBUG_DIR / "history_main_content.html"
        main_content_path.write_text(
            page_analysis.get("mainContent", ""), encoding="utf-8"
        )
        logger.info("Main content saved to: %s", main_content_path)

        # Log ID elements for debugging
        logger.info("")
        logger.info("--- Elements with IDs ---")
        for el in page_analysis.get("idElements", []):
            logger.info(
                "  #%s  tag=%s  class=%s  text=%r",
                el["id"], el["tag"], el.get("className"), el.get("textPreview", "")[:60]
            )

        logger.info("")
        logger.info("=" * 60)
        logger.info("History page inspection complete.")
        logger.info("Review the files in: %s", DEBUG_DIR)
        logger.info("=" * 60)

    except Exception:
        logger.exception("History page inspection failed")
        raise
    finally:
        await bm.close()


def main() -> None:
    setup_logging(debug=True)
    asyncio.run(inspect_history())


if __name__ == "__main__":
    main()
