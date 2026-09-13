"""
First-time setup: push all required secrets to GitHub.

Usage:
    python scripts/setup_github_secrets.py

This pushes:
    - TELEGRAM_BOT_TOKEN  (from .env)
    - TELEGRAM_CHAT_ID    (from .env)
    - AUTH_STATE_B64       (from data/auth-state.json, base64 encoded)

Prerequisites:
    1. GitHub CLI (`gh`) installed and authenticated
    2. .env file configured with Telegram credentials
    3. data/auth-state.json exists (run `python run.py` → Option 4)
    4. Repo pushed to GitHub
"""

import base64
import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

# Project root is one level up from scripts/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUTH_STATE_PATH = PROJECT_ROOT / "data" / "auth-state.json"

# Load .env
load_dotenv(PROJECT_ROOT / ".env")

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

if sys.platform == "win32":
    os.system("")


def push_secret(name: str, value: str) -> bool:
    """Push a secret to the GitHub repository."""
    result = subprocess.run(
        ["gh", "secret", "set", name, "--body", value],
        capture_output=True, text=True,
        cwd=str(PROJECT_ROOT),
    )
    if result.returncode != 0:
        print(f"  {RED}✗ {name}: {result.stderr.strip()}{RESET}")
        return False
    print(f"  {GREEN}✓ {name}{RESET}")
    return True


def main():
    print(f"\n{BOLD}GitHub Actions — First-Time Secrets Setup{RESET}\n")

    # Check gh CLI
    if not shutil.which("gh"):
        print(f"{RED}Error: GitHub CLI (gh) is not installed.{RESET}")
        print(f"  Install: https://cli.github.com/")
        sys.exit(1)

    result = subprocess.run(
        ["gh", "auth", "status"], capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"{RED}Error: Run 'gh auth login' first.{RESET}")
        sys.exit(1)

    # Gather values
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not telegram_token or not telegram_chat_id:
        print(f"{RED}Error: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env{RESET}")
        sys.exit(1)

    if not AUTH_STATE_PATH.is_file():
        print(f"{RED}Error: {AUTH_STATE_PATH} not found.{RESET}")
        print(f"  Run: python run.py → Option 4 to authenticate first.")
        sys.exit(1)

    auth_b64 = base64.b64encode(AUTH_STATE_PATH.read_bytes()).decode("ascii")

    # Push all secrets
    print(f"  Pushing secrets to GitHub...\n")

    all_ok = True
    all_ok &= push_secret("TELEGRAM_BOT_TOKEN", telegram_token)
    all_ok &= push_secret("TELEGRAM_CHAT_ID", telegram_chat_id)
    all_ok &= push_secret("AUTH_STATE_B64", auth_b64)

    if all_ok:
        print(f"\n  {GREEN}✅ All secrets configured!{RESET}")
        print(f"  {DIM}GitHub Actions will start monitoring on the next cron tick.{RESET}")
        print(f"  {DIM}Or trigger manually: gh workflow run monitor.yml{RESET}\n")
    else:
        print(f"\n  {RED}❌ Some secrets failed. Fix the errors above and retry.{RESET}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
