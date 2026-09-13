@echo off
REM Push auth-state.json to GitHub Secrets
REM Requires: GitHub CLI (gh) installed and authenticated

cd /d "%~dp0.."
python scripts\push_auth.py
pause
