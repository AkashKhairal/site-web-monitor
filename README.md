# Site Web Monitor

A lightweight monitoring service that watches the **SITE WEB** card on the Mobile Tracker Free dashboard. When new website activity is detected, it sends Telegram notifications.

## Features

- Monitors the SITE WEB dashboard card for count changes
- Detects new website history entries using stable database IDs
- Sends Telegram notifications for each new entry
- Handles multiple new entries between check cycles
- Persistent state survives restarts and reboots (atomic writes)
- First-run baseline — no false alerts on initial deployment
- Authentication failure detection with Telegram alert
- Exponential backoff retry on transient failures
- Browser crash recovery
- Dry-run and debug modes
- Graceful shutdown (SIGTERM/SIGINT)
- systemd service for 24/7 production operation

## Requirements

- Python 3.11+
- Playwright with Chromium
- Telegram Bot (for notifications)

---

## Local Development Setup

### 1. Clone/Copy the Project

```bash
cd /path/to/your/projects
# Copy the site-web-monitor directory
```

### 2. Create Virtual Environment

```bash
cd site-web-monitor
python -m venv venv
source venv/bin/activate      # Linux/Mac
# or: venv\Scripts\activate   # Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

### 4. Configure Environment

```bash
cp .env.example .env
# Edit .env with your values:
#   TELEGRAM_BOT_TOKEN=<from @BotFather>
#   TELEGRAM_CHAT_ID=<your chat ID>
```

**Get your Telegram Chat ID:**
1. Message [@userinfobot](https://t.me/userinfobot) on Telegram
2. It will reply with your chat ID

**Create a Telegram Bot:**
1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the instructions
3. Copy the bot token to your `.env` file
4. Start a chat with your bot (send it any message)

### 5. Authenticate

```bash
export PYTHONPATH=.   # Linux/Mac
# or: $env:PYTHONPATH = "."   # PowerShell

python -m setup.auth_setup
```

A browser window will open. Log in manually. The session will be saved automatically.

### 6. Run the Monitor

```bash
# Normal mode
python -m app.main

# Dry-run (logs actions but doesn't send Telegram)
python -m app.main --dry-run

# Debug mode (verbose logging, headed browser)
python -m app.main --debug
```

---

## Deployment Options

### Option A: GitHub Actions (Recommended — 100% Free, No Credit Card, Hands-Off)

If you don't have a credit card for cloud providers and don't want to keep your PC running 24/7, deploy via **GitHub Actions**:

- **Cost:** Free (unlimited minutes on public repos, 2,000 mins/mo on private)
- **Schedule:** Runs every 5–30 minutes automatically
- **Persistence:** State stored across runs via GitHub Actions Cache
- **Session Expiration Alerts:** Telegram alert sent if login expires
- **One-click Re-auth:** Re-login on your PC and run `push_auth.bat` or `python run.py` (Option 10)

👉 **Full Setup Guide:** [docs/github_actions_setup.md](docs/github_actions_setup.md)

Quick start:
```bash
# 1. Log in on PC:
python run.py  # Choose Option 4

# 2. Push repository to GitHub:
gh repo create site-web-monitor --public --source=. --push

# 3. Push secrets (token, chat ID, session):
python scripts/setup_github_secrets.py
```

---

### Option B: Oracle Cloud ARM64 VM (Dedicated 24/7 Service)

If you have an Oracle Cloud Always-Free VM:

#### 1. Create the VM


- Oracle Cloud Always Free tier
- Ubuntu 22.04+ (ARM64/AArch64)
- Open SSH port (22)

### 2. Connect via SSH

```bash
ssh ubuntu@<your-vm-ip>
```

### 3. Install System Dependencies

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git

# Verify architecture
uname -m
# Expected: aarch64
```

### 4. Create Service User

```bash
sudo useradd -r -m -s /bin/bash siteweb
```

### 5. Set Up Application Directory

```bash
sudo mkdir -p /opt/site-web-monitor
sudo mkdir -p /opt/site-web-monitor-private
sudo chown siteweb:siteweb /opt/site-web-monitor
sudo chown siteweb:siteweb /opt/site-web-monitor-private
sudo chmod 700 /opt/site-web-monitor-private
```

### 6. Copy Project Files

```bash
# From your local machine:
scp -r site-web-monitor/* ubuntu@<vm-ip>:/tmp/site-web-monitor/

# On the VM:
sudo cp -r /tmp/site-web-monitor/* /opt/site-web-monitor/
sudo chown -R siteweb:siteweb /opt/site-web-monitor
```

### 7. Set Up Python Environment

```bash
sudo -u siteweb bash
cd /opt/site-web-monitor

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
python -m playwright install-deps chromium
```

### 8. Verify Playwright Works on ARM64

```bash
python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('https://example.com')
    print(page.title())
    browser.close()
"
```

Expected output: `Example Domain`

### 9. Configure Environment

```bash
# Create .env in the private directory
cat > /opt/site-web-monitor-private/.env << 'EOF'
TELEGRAM_BOT_TOKEN=<your-bot-token>
TELEGRAM_CHAT_ID=<your-chat-id>
CHECK_INTERVAL_SECONDS=300
PRIVATE_DIR=/opt/site-web-monitor-private
EOF

chmod 600 /opt/site-web-monitor-private/.env
```

### 10. Authenticate

For first-time authentication, you need a display. Options:

**Option A: X11 Forwarding (recommended)**
```bash
ssh -X ubuntu@<vm-ip>
sudo -u siteweb bash
cd /opt/site-web-monitor
source venv/bin/activate
export DISPLAY=:0  # or use X11 forwarding
export PYTHONPATH=/opt/site-web-monitor
python -m setup.auth_setup
```

**Option B: Use a VNC/remote desktop session**

Log in manually in the browser window when it opens.

### 11. Test the Monitor

```bash
sudo -u siteweb bash
cd /opt/site-web-monitor
source venv/bin/activate
export PYTHONPATH=/opt/site-web-monitor

# Dry run first
python -m app.main --dry-run

# If that works, test with Telegram
python -m app.main
# Press Ctrl+C after the first successful cycle
```

### 12. Install systemd Service

```bash
sudo cp /opt/site-web-monitor/site-web-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable site-web-monitor
sudo systemctl start site-web-monitor
```

### 13. Verify Service is Running

```bash
sudo systemctl status site-web-monitor
```

---

## Operational Commands

### Service Management

```bash
# Check status
sudo systemctl status site-web-monitor

# View logs (live)
journalctl -u site-web-monitor -f

# View recent logs
journalctl -u site-web-monitor --since "1 hour ago"

# Restart
sudo systemctl restart site-web-monitor

# Stop
sudo systemctl stop site-web-monitor
```

### Re-Authentication

When the session expires, you'll receive a Telegram alert. To re-authenticate:

```bash
sudo systemctl stop site-web-monitor

sudo -u siteweb bash
cd /opt/site-web-monitor
source venv/bin/activate
export PYTHONPATH=/opt/site-web-monitor
python -m setup.auth_setup

# After login completes:
exit
sudo systemctl start site-web-monitor
```

### Manual Monitor Run

```bash
sudo -u siteweb bash
cd /opt/site-web-monitor
source venv/bin/activate
export PYTHONPATH=/opt/site-web-monitor
python -m app.main --dry-run
```

---

## Project Structure

```
site-web-monitor/
├── app/
│   ├── __init__.py          # Package init
│   ├── __main__.py          # python -m app.main entry point
│   ├── main.py              # Main monitoring loop
│   ├── auth.py              # Browser lifecycle (Playwright)
│   ├── dashboard.py         # SITE WEB card extraction
│   ├── history.py           # History page entry extraction
│   ├── notifier.py          # Telegram notifications
│   ├── state.py             # Persistent state (atomic JSON)
│   ├── config.py            # Centralized configuration
│   └── logging_config.py    # Logging with sensitive-data filter
├── setup/
│   ├── __init__.py
│   ├── __main__.py          # python -m setup.auth_setup entry point
│   ├── auth_setup.py        # Interactive login helper
│   ├── inspect_dashboard.py # Dashboard DOM inspector
│   └── inspect_history.py   # History page DOM inspector
├── tests/
│   ├── test_state.py
│   └── test_config.py
├── data/                    # Local runtime data (gitignored)
│   └── debug/               # Sensitive debug artifacts (gitignored)
├── requirements.txt
├── .env.example
├── .gitignore
├── site-web-monitor.service # systemd unit file
└── README.md
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | *(required)* | Telegram Bot API token |
| `TELEGRAM_CHAT_ID` | *(required)* | Telegram chat ID for notifications |
| `CHECK_INTERVAL_SECONDS` | `300` | Monitoring interval (seconds) |
| `MAX_RETRIES` | `4` | Max retry attempts on transient failures |
| `PRIVATE_DIR` | `./data` | Directory for auth state and runtime data |
| `TARGET_LOGIN_URL` | `https://mobile-tracker-free.com/login/` | Login page URL |
| `TARGET_DASHBOARD_URL` | `https://mobile-tracker-free.com/dashboard/` | Dashboard URL |

## Security

- Credentials are never stored in source code
- Authentication state is stored outside the repository
- `.env` file is gitignored
- Debug artifacts (DOM dumps, screenshots) are gitignored
- Telegram bot token is never logged (redacted by filter)
- State files use restrictive permissions on Linux

## GitHub (Optional)

GitHub is **not required** for the application to run. The Oracle VM runs entirely from its local filesystem. If you choose to use GitHub for source code backup:

1. Never commit `.env`, `auth-state.json`, or `data/debug/` contents
2. The `.gitignore` is already configured to exclude these files
3. The application does not depend on GitHub at runtime
