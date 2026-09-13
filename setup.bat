@echo off
title Site Web Monitor - Setup

echo.
echo  ========================================================
echo         SITE WEB MONITOR  -  FIRST TIME SETUP
echo  ========================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python is not installed or not in PATH.
    echo  Download it from: https://www.python.org/downloads/
    echo  Make sure to check "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

echo  [1/4] Python found:
python --version
echo.

:: Install dependencies
echo  [2/4] Installing Python packages...
pip install playwright python-dotenv httpx --quiet
if errorlevel 1 (
    echo  [ERROR] Failed to install packages.
    pause
    exit /b 1
)
echo        Done.
echo.

:: Install Chromium
echo  [3/4] Installing Chromium browser (this may take a minute)...
python -m playwright install chromium
if errorlevel 1 (
    echo  [ERROR] Failed to install Chromium.
    pause
    exit /b 1
)
echo        Done.
echo.

:: Create .env if missing
if not exist ".env" (
    echo  [4/4] Creating .env config file...
    copy .env.example .env >nul
    echo        Done.
    echo.
    echo  ---------------------------------------------------------
    echo  IMPORTANT: Open .env in a text editor and set:
    echo    TELEGRAM_BOT_TOKEN=your_token_here
    echo    TELEGRAM_CHAT_ID=your_chat_id_here
    echo  ---------------------------------------------------------
) else (
    echo  [4/4] .env already exists - skipping.
)

echo.
echo  ========================================================
echo  Setup complete! To start, run:
echo.
echo      python run.py
echo.
echo  Or double-click start.bat
echo.
echo  First time? Choose option 4 to log in, then option 1.
echo  ========================================================
echo.
pause
