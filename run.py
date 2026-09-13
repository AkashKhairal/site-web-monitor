"""
Site Web Monitor — Interactive CLI

A one-click command-line interface for managing the monitoring service.

Usage:
    python run.py
"""

import asyncio
import io
import logging
import os
import sys

# Fix Windows console encoding for Unicode characters
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Ensure project root is on sys.path
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

os.environ.setdefault("PYTHONPATH", _PROJECT_ROOT)

from app.logging_config import setup_logging

logger = logging.getLogger("cli")

# ── ANSI Colors ──────────────────────────────────────────────────────────
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
RESET = "\033[0m"
CLEAR = "\033[2J\033[H"


def banner():
    print(f"""{CLEAR}
{CYAN}{BOLD}╔══════════════════════════════════════════════════════╗
║           SITE WEB MONITOR  ·  CLI                   ║
╚══════════════════════════════════════════════════════╝{RESET}
""")


def print_status():
    """Print current system status."""
    from app.config import (
        AUTH_STATE_PATH,
        CHECK_INTERVAL_SECONDS,
        STATE_FILE_PATH,
        validate_auth_state,
        validate_telegram_config,
    )
    from app.state import load_state

    auth_ok = validate_auth_state()
    telegram_ok = validate_telegram_config()

    state = load_state()
    state_exists = STATE_FILE_PATH.is_file()

    print(f"  {BOLD}System Status:{RESET}")
    print(f"  ─────────────────────────────────────")
    print(f"  Auth State     : {'✅ Saved' if auth_ok else '❌ Not found'}")
    print(f"  Telegram       : {'✅ Configured' if telegram_ok else '❌ Not configured'}")
    print(f"  Monitor State  : {'✅ Exists' if state_exists else '⬜ Fresh (first run)'}")

    if state_exists:
        print(f"  Last Count     : {state.last_count}")
        print(f"  Seen Entry IDs : {len(state.seen_entry_ids)}")
        print(f"  Last Updated   : {state.updated_at or 'N/A'}")
        print(f"  First Run      : {state.is_first_run}")

    print(f"  Check Interval : {CHECK_INTERVAL_SECONDS}s ({CHECK_INTERVAL_SECONDS // 60}m)")
    print()


def menu():
    """Display the main menu and return the user's choice."""
    print(f"  {BOLD}Actions:{RESET}")
    print()
    print(f"  {GREEN}1{RESET})  Start Monitoring")
    print(f"  {GREEN}2{RESET})  Start Monitoring {DIM}(dry-run, no Telegram){RESET}")
    print(f"  {GREEN}3{RESET})  Start Monitoring {DIM}(debug mode){RESET}")
    print()
    print(f"  {YELLOW}4{RESET})  Re-authenticate {DIM}(update login session){RESET}")
    print(f"  {YELLOW}5{RESET})  Test Telegram {DIM}(send test message){RESET}")
    print()
    print(f"  {CYAN}6{RESET})  Check Dashboard {DIM}(one-time count check){RESET}")
    print(f"  {CYAN}7{RESET})  View History Entries {DIM}(show current entries){RESET}")
    print()
    print(f"  {MAGENTA}8{RESET})  Reset State {DIM}(clear seen entries, start fresh){RESET}")
    print(f"  {MAGENTA}9{RESET})  Show Status {DIM}(refresh status display){RESET}")
    print()
    print(f"  {CYAN}10{RESET}) Push Auth to GitHub {DIM}(sync session to GitHub Actions){RESET}")
    print()
    print(f"  {RED}0{RESET})  Exit")
    print()

    try:
        choice = input(f"  {BOLD}Select [{GREEN}1-10{RESET}{BOLD}, {RED}0{RESET}{BOLD}]: {RESET}").strip()
    except (EOFError, KeyboardInterrupt):
        choice = "0"

    return choice


# ── Actions ──────────────────────────────────────────────────────────────

def action_start_monitor(dry_run=False, debug=False):
    """Start the monitoring loop."""
    from app.config import validate_auth_state, validate_telegram_config

    if not validate_auth_state():
        print(f"\n  {RED}No auth state found.{RESET} Run option 4 to authenticate first.\n")
        input("  Press Enter to continue...")
        return

    if not validate_telegram_config() and not dry_run:
        print(f"\n  {YELLOW}Warning:{RESET} Telegram not configured. Notifications will fail.")
        print(f"  Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env\n")

    mode = "dry-run" if dry_run else ("debug" if debug else "normal")
    print(f"\n  Starting monitor in {BOLD}{mode}{RESET} mode...")
    print(f"  Press {BOLD}Ctrl+C{RESET} to stop.\n")

    from app.main import Monitor
    setup_logging(debug=debug)
    monitor = Monitor(dry_run=dry_run, debug=debug)
    try:
        asyncio.run(monitor.start())
    except KeyboardInterrupt:
        print(f"\n  {YELLOW}Monitor stopped.{RESET}\n")

    input("  Press Enter to continue...")


def action_authenticate():
    """Run interactive authentication."""
    print(f"\n  {BOLD}Re-authentication{RESET}")
    print(f"  A browser window will open. Log in manually.")
    print(f"  {DIM}(Supports CAPTCHA and MFA){RESET}\n")

    from setup.auth_setup import run_auth_setup
    setup_logging()
    try:
        asyncio.run(run_auth_setup())
    except KeyboardInterrupt:
        print(f"\n  {YELLOW}Authentication cancelled.{RESET}\n")
    except Exception as exc:
        print(f"\n  {RED}Error: {exc}{RESET}\n")

    input("\n  Press Enter to continue...")


def action_test_telegram():
    """Send a test Telegram message."""
    from app.config import validate_telegram_config

    if not validate_telegram_config():
        print(f"\n  {RED}Telegram not configured.{RESET}")
        print(f"  Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env\n")
        input("  Press Enter to continue...")
        return

    print(f"\n  Sending test message...")

    async def _test():
        from app.notifier import send_message
        return await send_message(
            "🔔 <b>Site Web Monitor</b>\n\n"
            "Test message — notifications are working!",
        )

    setup_logging()
    success = asyncio.run(_test())

    if success:
        print(f"  {GREEN}✅ Test message sent! Check your Telegram.{RESET}\n")
    else:
        print(f"  {RED}❌ Failed to send. Check your .env credentials.{RESET}\n")

    input("  Press Enter to continue...")


def action_check_dashboard():
    """One-time dashboard check."""
    from app.config import validate_auth_state

    if not validate_auth_state():
        print(f"\n  {RED}No auth state found.{RESET} Run option 4 first.\n")
        input("  Press Enter to continue...")
        return

    print(f"\n  Checking dashboard...")

    async def _check():
        from app.auth import BrowserManager
        from app.dashboard import (
            AuthenticationError,
            ExtractionError,
            get_site_web_status,
            navigate_to_dashboard,
        )

        bm = BrowserManager()
        try:
            page = await bm.start_authenticated(headless=True)
            await navigate_to_dashboard(page)
            status = await get_site_web_status(page)
            return status
        except AuthenticationError:
            return "AUTH_EXPIRED"
        except ExtractionError as exc:
            return f"EXTRACTION_ERROR: {exc}"
        finally:
            await bm.close()

    setup_logging()
    result = asyncio.run(_check())

    if result == "AUTH_EXPIRED":
        print(f"  {RED}❌ Session expired!{RESET} Run option 4 to re-authenticate.\n")
    elif isinstance(result, str) and result.startswith("EXTRACTION_ERROR"):
        print(f"  {RED}❌ {result}{RESET}\n")
    else:
        print(f"\n  {BOLD}SITE WEB Count: {GREEN}{result.count}{RESET}")
        print(f"  {DIM}Raw text: {result.raw_text!r}{RESET}\n")

    input("  Press Enter to continue...")


def action_view_history():
    """Show current history entries."""
    from app.config import validate_auth_state

    if not validate_auth_state():
        print(f"\n  {RED}No auth state found.{RESET} Run option 4 first.\n")
        input("  Press Enter to continue...")
        return

    print(f"\n  Loading history entries...")

    async def _history():
        from app.auth import BrowserManager
        from app.history import get_all_visible_entries, navigate_to_history

        bm = BrowserManager()
        try:
            page = await bm.start_authenticated(headless=True)
            await navigate_to_history(page)
            entries = await get_all_visible_entries(page)
            return entries
        finally:
            await bm.close()

    setup_logging()
    entries = asyncio.run(_history())

    if not entries:
        print(f"  {DIM}No entries found.{RESET}\n")
    else:
        from app.state import load_state
        state = load_state()

        print(f"\n  {BOLD}History Entries ({len(entries)} visible):{RESET}")
        print(f"  {'─' * 70}")
        print(f"  {'#':<4} {'ID':<14} {'Status':<8} {'Date':<22} {'URL'}")
        print(f"  {'─' * 70}")

        for i, e in enumerate(entries, 1):
            seen = "seen" if e.entry_id in state.seen_entry_ids else f"{GREEN}NEW{RESET} "
            url = e.website[:45] + "..." if len(e.website) > 48 else e.website
            print(f"  {i:<4} {e.entry_id:<14} {seen:<8} {e.timestamp or 'N/A':<22} {url}")

        print(f"  {'─' * 70}\n")

    input("  Press Enter to continue...")


def action_reset_state():
    """Reset the monitor state (clear seen entries)."""
    print(f"\n  {YELLOW}This will clear all seen entry IDs and reset the monitor.{RESET}")
    print(f"  The next run will establish a new baseline (no alerts for existing entries).\n")

    try:
        confirm = input(f"  Type {BOLD}RESET{RESET} to confirm: ").strip()
    except (EOFError, KeyboardInterrupt):
        confirm = ""

    if confirm != "RESET":
        print(f"  {DIM}Cancelled.{RESET}\n")
        input("  Press Enter to continue...")
        return

    from app.config import STATE_FILE_PATH

    if STATE_FILE_PATH.is_file():
        STATE_FILE_PATH.unlink()
        print(f"  {GREEN}State cleared.{RESET} Next run will establish a fresh baseline.\n")
    else:
        print(f"  {DIM}No state file to clear.{RESET}\n")

    input("  Press Enter to continue...")


def action_push_auth_github():
    """Push local auth-state.json to GitHub Secrets."""
    import subprocess

    scripts_dir = os.path.join(_PROJECT_ROOT, "scripts")
    push_script = os.path.join(scripts_dir, "push_auth.py")

    try:
        subprocess.run([sys.executable, push_script], cwd=_PROJECT_ROOT)
    except Exception as exc:
        print(f"\n  {RED}Error running push_auth: {exc}{RESET}\n")

    input("  Press Enter to continue...")


# ── Main Loop ────────────────────────────────────────────────────────────

def main():
    """Main CLI entry point."""
    # Enable ANSI colors on Windows
    if sys.platform == "win32":
        os.system("")  # Enables ANSI escape sequences in Windows terminal

    while True:
        banner()
        print_status()
        choice = menu()

        if choice == "1":
            action_start_monitor()
        elif choice == "2":
            action_start_monitor(dry_run=True)
        elif choice == "3":
            action_start_monitor(debug=True)
        elif choice == "4":
            action_authenticate()
        elif choice == "5":
            action_test_telegram()
        elif choice == "6":
            action_check_dashboard()
        elif choice == "7":
            action_view_history()
        elif choice == "8":
            action_reset_state()
        elif choice == "9":
            continue  # Just refreshes the screen
        elif choice == "10":
            action_push_auth_github()
        elif choice == "0":
            print(f"\n  {DIM}Goodbye!{RESET}\n")
            break
        else:
            print(f"\n  {RED}Invalid choice.{RESET}")
            input("  Press Enter to continue...")


if __name__ == "__main__":
    main()

