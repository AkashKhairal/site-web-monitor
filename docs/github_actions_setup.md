# 🚀 Free Cloud Deployment via GitHub Actions

Deploy and run **Site Web Monitor** 24/7 in the cloud with **zero hosting cost**, **no credit card required**, and **no need to keep your PC turned on**.

---

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                      GITHUB ACTIONS                         │
│                                                             │
│   Cron Trigger (every 5-30 mins)                            │
│         │                                                   │
│         ▼                                                   │
│   Restore Session ◄── Encrypted Secret (AUTH_STATE_B64)     │
│         │                                                   │
│         ▼                                                   │
│   Restore State   ◄── GitHub Cache (data/state.json)        │
│         │                                                   │
│         ▼                                                   │
│   Headless Playwright Check Dashboard                       │
│         │                                                   │
│    ┌────┴───────────────────────────┐                       │
│    │ New entries found?             │ Session expired?      │
│    ▼                                ▼                       │
│  Telegram Alert               Telegram Alert                │
│  "New Website Activity"       "⚠️ Session Expired"          │
│    │                                │                       │
│    ▼                                ▼                       │
│  Save State to Cache          Wait for PC re-auth           │
└─────────────────────────────────────────────────────────────┘
```

1. **Scheduled Runs:** GitHub Actions automatically spins up an Ubuntu VM on a cron schedule to execute `python -m app.main --once`.
2. **Encrypted Authentication:** Your login cookies are stored as an encrypted GitHub Secret (`AUTH_STATE_B64`). The runner decodes them into `data/auth-state.json` at the start of each run.
3. **State Persistence Across Runs:** The monitor state (`data/state.json`) is stored in the **GitHub Actions Cache**. It persists known entry IDs and prevents duplicate Telegram notifications.
4. **Session Expiration Alerts:** If the website session expires, the monitor detects it and immediately sends you a Telegram message warning you to re-authenticate.
5. **Fast Re-authentication:** When alerted, you log in on your PC and run one script (`scripts/push_auth.bat` or Option 10 in `run.py`) to upload the refreshed session.

---

## Public vs. Private Repositories

| Feature | Public Repository | Private Repository |
|---|---|---|
| **Cost** | 100% Free | 100% Free (within limits) |
| **Actions Minutes** | **Unlimited** | **2,000 minutes / month** |
| **Recommended Schedule** | Every 5 minutes (`*/5 * * * *`) | Every 15–30 minutes (`*/30 * * * *`) |
| **Security** | Safe: secrets (`.env`, cookies) are gitignored and encrypted in GitHub Secrets | Safe: entirely private |

> [!TIP]
> **Why Public is safe:** The `.gitignore` prevents `.env`, `data/auth-state.json`, and `data/state.json` from ever being committed. Secrets are stored in encrypted repository settings that only GitHub Actions can read.

---

## Prerequisites

1. **GitHub Account**: [github.com](https://github.com)
2. **Git**: Installed on your PC
3. **GitHub CLI (`gh`)**:
   - Windows: `winget install GitHub.cli` or download from [cli.github.com](https://cli.github.com)
   - After installing, log in in your terminal:
     ```bash
     gh auth login
     ```
4. **Telegram Bot**: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` configured in your local `.env`.

---

## Step-by-Step Setup

### Step 1: Log In Locally (Once)

Before deploying to the cloud, create a valid session on your PC:

```bash
python run.py
```
- Select **Option 4 (Re-authenticate)**.
- A browser opens. Log in manually (solve CAPTCHA / 2FA if prompted).
- Once logged in, your session is saved to `data/auth-state.json`.

---

### Step 2: Push Repository to GitHub

If you haven't pushed this repo to GitHub yet:

```bash
# Initialize git if needed
git init
git add .
git commit -m "Initial commit for Site Web Monitor"

# Create a repo using GitHub CLI (choose public or private)
gh repo create site-web-monitor --public --source=. --push
# Or for private:
# gh repo create site-web-monitor --private --source=. --push
```

---

### Step 3: Push Secrets to GitHub (One Command)

Run the included setup script:

```bash
python scripts/setup_github_secrets.py
```

This automatically uploads three encrypted secrets to your GitHub repository:
- `TELEGRAM_BOT_TOKEN` (from your `.env`)
- `TELEGRAM_CHAT_ID` (from your `.env`)
- `AUTH_STATE_B64` (base64-encoded `data/auth-state.json`)

---

### Step 4: Test & Verify

Trigger a manual test run directly from GitHub CLI or the web UI:

```bash
gh workflow run monitor.yml
```

To watch the live run:
```bash
gh run watch
```

Or open GitHub in your browser:
1. Go to your repository on GitHub.
2. Click the **Actions** tab.
3. You will see **Site Web Monitor**.
4. The first run will establish the baseline (no false alerts). Future runs will check for new activity!

---

## How to Re-Authenticate When Session Expires

When your session cookies eventually expire:

1. You will receive a Telegram message:
   ```
   ⚠️ Site Web Monitor: Authentication Failed
   Session expired or credentials rejected. Re-authenticate on your PC.
   ```
2. On your PC, open a terminal in the project folder and run:
   ```bash
   python run.py
   ```
   - Press **4** to log in again in the browser.
   - Press **10** to push the new session to GitHub.
   *(Alternatively, double-click `scripts\push_auth.bat`).*
3. That's it! GitHub Actions resumes monitoring with the new session automatically.
