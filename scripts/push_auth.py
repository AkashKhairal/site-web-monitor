"""
Push auth-state.json to GitHub as an encrypted repository secret.

Usage:
    python scripts/push_auth.py

Prerequisites:
    1. GitHub CLI (`gh`) must be installed and authenticated.
       Install: https://cli.github.com/  or  `winget install GitHub.cli`
       Login:   `gh auth login`
    2. data/auth-state.json must exist (run `python run.py` → Option 4)
    3. Your repo must be pushed to GitHub
"""

import base64
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Project root is one level up from scripts/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
AUTH_STATE_PATH = PROJECT_ROOT / "data" / "auth-state.json"

# ANSI colors (Windows terminal supports these)
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

if sys.platform == "win32":
    os.system("")  # Enable ANSI on Windows


def check_gh_cli() -> bool:
    """Check if GitHub CLI is installed and authenticated."""
    if not shutil.which("gh"):
        print(f"{RED}Error: GitHub CLI (gh) is not installed.{RESET}")
        print(f"  Install: https://cli.github.com/")
        print(f"  Or run:  winget install GitHub.cli")
        return False

    result = subprocess.run(
        ["gh", "auth", "status"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"{RED}Error: GitHub CLI is not authenticated.{RESET}")
        print(f"  Run: gh auth login")
        return False

    return True


def check_auth_state() -> bool:
    """Check if auth-state.json exists."""
    if not AUTH_STATE_PATH.is_file():
        print(f"{RED}Error: {AUTH_STATE_PATH} not found.{RESET}")
        print(f"  Run: python run.py → Option 4 to authenticate first.")
        return False
    return True


def check_git_repo() -> bool:
    """Check if we're in a git repo with a GitHub remote."""
    result = subprocess.run(
        ["gh", "repo", "view", "--json", "name"],
        capture_output=True, text=True,
        cwd=str(PROJECT_ROOT),
    )
    if result.returncode != 0:
        print(f"{RED}Error: Not in a GitHub repository, or no remote set.{RESET}")
        print(f"  Push your repo to GitHub first:")
        print(f"    gh repo create site-web-monitor --private --source=. --push")
        return False
    return True


def push_secret(name: str, value: str) -> bool:
    """Push a secret to the GitHub repository."""
    result = subprocess.run(
        ["gh", "secret", "set", name, "--body", value],
        capture_output=True, text=True,
        cwd=str(PROJECT_ROOT),
    )
    if result.returncode != 0:
        print(f"{RED}Failed to set {name}: {result.stderr.strip()}{RESET}")
        return False
    return True


def main():
    print(f"\n{BOLD}Push Auth State to GitHub Secrets{RESET}\n")

    # Preflight checks
    if not check_gh_cli():
        sys.exit(1)
    if not check_auth_state():
        sys.exit(1)
    if not check_git_repo():
        sys.exit(1)

    # Read and encode auth state
    auth_data = AUTH_STATE_PATH.read_bytes()
    auth_b64 = base64.b64encode(auth_data).decode("ascii")

    size_kb = len(auth_data) / 1024
    print(f"  Auth state: {size_kb:.1f} KB")
    print(f"  Pushing to GitHub Secrets as AUTH_STATE_B64...")

    if push_secret("AUTH_STATE_B64", auth_b64):
        print(f"\n  {GREEN}✅ Auth state pushed successfully!{RESET}")
        print(f"  {DIM}The next GitHub Actions run will use the new session.{RESET}\n")
    else:
        print(f"\n  {RED}❌ Failed to push auth state.{RESET}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
