"""
Dashboard DOM inspection script for Site Web Monitor.

Loads the saved authentication state, navigates to the dashboard, and dumps
the DOM structure to help discover stable selectors for the SITE WEB card.

Output is saved to data/debug/ (gitignored, sensitive).

Usage:
    python -m setup.inspect_dashboard

IMPORTANT: Run setup.auth_setup first to create the auth state.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from app.auth import BrowserManager
from app.config import AUTH_STATE_PATH, DEBUG_DIR, TARGET_DASHBOARD_URL
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)


async def inspect_dashboard() -> None:
    """Navigate to the dashboard and dump DOM information."""

    if not AUTH_STATE_PATH.is_file():
        logger.error(
            "No authentication state found at %s. "
            "Run 'python -m setup.auth_setup' first.",
            AUTH_STATE_PATH,
        )
        return

    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    bm = BrowserManager()
    try:
        page = await bm.start_authenticated(headless=True)

        logger.info("Navigating to dashboard: %s", TARGET_DASHBOARD_URL)
        await page.goto(TARGET_DASHBOARD_URL, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")

        current_url = page.url
        logger.info("Current URL after navigation: %s", current_url)

        # Check if we got redirected to login (session expired)
        if "/login" in current_url.lower():
            logger.error(
                "Redirected to login page — authentication has expired. "
                "Run 'python -m setup.auth_setup' again."
            )
            return

        # --- Dump 1: Full page HTML ---
        html = await page.content()
        html_path = DEBUG_DIR / "dashboard_full.html"
        html_path.write_text(html, encoding="utf-8")
        logger.info("Full HTML saved to: %s (%d bytes)", html_path, len(html))

        # --- Dump 2: Page text content ---
        text = await page.inner_text("body")
        text_path = DEBUG_DIR / "dashboard_text.txt"
        text_path.write_text(text, encoding="utf-8")
        logger.info("Text content saved to: %s", text_path)

        # --- Dump 3: Accessibility tree (snapshot) ---
        try:
            ax_tree = await page.accessibility.snapshot()
            import json

            ax_path = DEBUG_DIR / "dashboard_accessibility.json"
            ax_path.write_text(
                json.dumps(ax_tree, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            logger.info("Accessibility tree saved to: %s", ax_path)
        except Exception as exc:
            logger.warning("Could not capture accessibility tree: %s", exc)

        # --- Dump 4: Search for "SITE WEB" text specifically ---
        logger.info("")
        logger.info("=" * 60)
        logger.info("Searching for 'SITE WEB' in page content...")
        logger.info("=" * 60)

        # Find all elements containing "SITE WEB" text
        site_web_elements = await page.query_selector_all("//*[contains(text(), 'SITE WEB') or contains(text(), 'Site Web') or contains(text(), 'site web')]")

        if not site_web_elements:
            # Try case-insensitive search via evaluate
            site_web_elements = await page.query_selector_all("*")
            logger.info("No elements found with direct 'SITE WEB' text. ")
            logger.info("Checking all visible text for 'site web' (case-insensitive)...")

            # Use JavaScript to find elements
            matches = await page.evaluate("""() => {
                const results = [];
                const walker = document.createTreeWalker(
                    document.body,
                    NodeFilter.SHOW_TEXT,
                    null,
                    false
                );
                let node;
                while (node = walker.nextNode()) {
                    if (node.textContent.toLowerCase().includes('site web')) {
                        const el = node.parentElement;
                        results.push({
                            tag: el.tagName,
                            id: el.id || null,
                            className: el.className || null,
                            text: node.textContent.trim().substring(0, 200),
                            href: el.href || null,
                            parentTag: el.parentElement ? el.parentElement.tagName : null,
                            parentId: el.parentElement ? el.parentElement.id : null,
                            parentClass: el.parentElement ? el.parentElement.className : null,
                            outerHTML: el.outerHTML.substring(0, 500),
                            // Walk up to find card/container
                            ancestors: (() => {
                                const anc = [];
                                let p = el;
                                for (let i = 0; i < 5 && p; i++) {
                                    anc.push({
                                        tag: p.tagName,
                                        id: p.id || null,
                                        className: p.className || null
                                    });
                                    p = p.parentElement;
                                }
                                return anc;
                            })()
                        });
                    }
                }
                return results;
            }""")

            if matches:
                logger.info("Found %d text nodes containing 'site web':", len(matches))
                for i, m in enumerate(matches):
                    logger.info("")
                    logger.info("--- Match %d ---", i + 1)
                    logger.info("  Tag: %s", m.get("tag"))
                    logger.info("  ID: %s", m.get("id"))
                    logger.info("  Class: %s", m.get("className"))
                    logger.info("  Text: %s", m.get("text"))
                    logger.info("  Href: %s", m.get("href"))
                    logger.info("  OuterHTML: %s", m.get("outerHTML"))
                    logger.info("  Ancestors:")
                    for j, a in enumerate(m.get("ancestors", [])):
                        logger.info(
                            "    [%d] %s id=%s class=%s",
                            j, a.get("tag"), a.get("id"), a.get("className"),
                        )

                # Save matches to file
                import json
                matches_path = DEBUG_DIR / "site_web_matches.json"
                matches_path.write_text(
                    json.dumps(matches, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                logger.info("")
                logger.info("Match details saved to: %s", matches_path)
            else:
                logger.warning(
                    "No text containing 'site web' found on the page. "
                    "The page structure may have changed."
                )
        else:
            logger.info(
                "Found %d elements with 'SITE WEB' text", len(site_web_elements)
            )
            for i, el in enumerate(site_web_elements):
                outer = await el.evaluate("el => el.outerHTML.substring(0, 500)")
                logger.info("--- Element %d ---", i + 1)
                logger.info("  %s", outer)

        # --- Dump 5: All links on page (useful for finding SITE WEB navigation) ---
        links = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('a[href]')).map(a => ({
                text: a.textContent.trim().substring(0, 100),
                href: a.href,
                id: a.id || null,
                className: a.className || null
            }));
        }""")

        import json
        links_path = DEBUG_DIR / "dashboard_links.json"
        links_path.write_text(
            json.dumps(links, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("")
        logger.info("All links (%d) saved to: %s", len(links), links_path)

        # --- Dump 6: Screenshot (for reference only, sensitive) ---
        screenshot_path = DEBUG_DIR / "dashboard_screenshot.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)
        logger.info("Screenshot saved to: %s", screenshot_path)

        logger.info("")
        logger.info("=" * 60)
        logger.info("Dashboard inspection complete.")
        logger.info("Review the files in: %s", DEBUG_DIR)
        logger.info("=" * 60)

    except Exception:
        logger.exception("Dashboard inspection failed")
        raise
    finally:
        await bm.close()


def main() -> None:
    setup_logging(debug=True)
    asyncio.run(inspect_dashboard())


if __name__ == "__main__":
    main()
