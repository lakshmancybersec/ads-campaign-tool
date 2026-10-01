# Transfer Lakshiya Dhotis to another Windows laptop

This transfers the existing application and history. It does not create new Meta campaigns. These instructions assume Windows on the destination laptop.

## 1. Stop the original application before copying

Keep ads paused during the handover. Stop the application terminal with Ctrl+C. Stop any other instance or scheduled task running this project. Do not run two copies against the same Meta account: each copy could run its own scheduler with a different database.

The verified database is `lakshiya_ads.db` in the project root. It stores campaign plans, approvals and existing Meta object IDs. Losing it would lose the application's association with the existing ads.

Make a backup of the project after stopping it. Do not delete the original installation. If SQLite `-wal` or `-shm` companion files remain, include them with the database; do not copy a database while the app is still writing to it.

## 2. Copy the project

From `C:\Users\Kali\Documents\GitHub\Ads Campaign Tool`, copy these to a new folder such as `C:\Lakshiya\Ads Campaign Tool`:

- `app`, `docs`, `scripts`, `tests`, `n8n`, `docker`
- `.env` (actual settings and credentials), `.env.example`, `.gitignore`
- `lakshiya_ads.db` and any SQLite companion files
- `requirements.txt`, `pytest.ini`, `README.md`, `docker-compose.yml`
- `local-backups` if you want to retain previous backups

Skip `.venv`, `.pytest_cache` and `__pycache__` folders. Recreate the virtual environment on the destination. Transfer `.env` and database privately, for example using your own encrypted USB drive. Do not upload the bundle to a public repository or paste credentials into chat.

Do not overwrite `.env` with `.env.example`. Do not start with a blank database.

## 3. Install Python and dependencies

Install Python 3.12 for Windows from https://www.python.org/downloads/windows/. Include the Python launcher during installation. Internet access is needed to install packages and communicate with Meta.

Open PowerShell on the new laptop and run each line:

```powershell
Set-Location 'C:\Lakshiya\Ads Campaign Tool'
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

These commands do not require virtual-environment activation or a PowerShell execution-policy change. Node.js, PHP, Docker and n8n are not required for this local Python/SQLite setup.

## 4. Configure a safe first start

Open the copied `.env` locally in an editor. Keep the credentials and business IDs. Check:

```ini
DATABASE_URL=sqlite:///./lakshiya_ads.db
META_APP_ID=1546656773810069
META_AD_ACCOUNT_ID=act_249780244315816
META_BUSINESS_MANAGER_ID=673644139160351
FACEBOOK_PAGE_ID=673640245827407
META_CATALOG_ID=1590606802764273
```

Initially set these flags on the NEW laptop only:

```ini
META_LIVE_WRITES_ENABLED=false
META_PAUSED_PREPARATION_ENABLED=false
SCHEDULER_ENABLED=false
```

This prevents automatic Meta activity during the transfer check. Preserve the saved budget settings and campaign approvals. Always run commands from the project root so the relative database path opens the copied database.

## 5. Start and sign in

```powershell
Set-Location 'C:\Lakshiya\Ads Campaign Tool'
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
```

Leave this terminal open. Open http://127.0.0.1:8000/ in a browser on the same laptop. Enter the value of `API_ADMIN_KEY` from the copied `.env` as the dashboard password. It is not the Meta token or Facebook password.

## 6. Verify the transfer before enabling writes

- Confirm saved campaigns, products, locations and budgets are present.
- Select the real Wedding Collection, identified by Meta Campaign ID `120254199040930204`.
- Confirm Ad Set `120254199242970204`, Creative `1882269586484301`, and Ad `120254203995060204` are still shown.
- Use Check Meta connection and Re-check Meta status. These should confirm access and ownership, not create new objects.
- Confirm delivery remains paused. Do not use Prepare paused ads on an empty duplicate record.
- Test refresh, campaign selection and logout.
- Review dates: the last verified schedule ended 2 October 2026 at 00:00 IST. This date may be expired when you transfer; use the schedule editor and approve an appropriate new schedule.

If history is empty, stop the app and check the copied database and working directory. Do not recreate the existing campaign to compensate for missing history.

Run the automated tests in a second PowerShell window from the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
```

The browser tests additionally require Playwright and a compatible browser. If missing:

```powershell
.\.venv\Scripts\python.exe -m pip install playwright
.\.venv\Scripts\python.exe -m playwright install chromium
```

Some project scripts/tests explicitly launch Microsoft Edge (`channel='msedge'`); install Edge if those checks require it. Automated tests use test databases/mocked Meta responses; they do not prove real billing or ad delivery.

## 7. Make the new laptop the sole operating installation

Confirm the original app remains stopped. On the new laptop, enable only the features you intend to use:

```ini
META_PAUSED_PREPARATION_ENABLED=true
SCHEDULER_ENABLED=true
META_LIVE_WRITES_ENABLED=true
```

Restart the application after editing `.env`. Enabling live writes permits approved actions; it does not replace the final owner approval. Previously enabled automation may resume, so review campaign automation states before restoring these flags.

Review Meta billing, approve the valid schedule and give final launch approval in the dashboard when ready. No new Meta app or token is needed solely because the laptop changed, provided the saved token remains valid and authorized.

## 8. Daily use and troubleshooting

- Start using the command in step 5; stop using Ctrl+C.
- Keep the laptop awake, online and the app running for local scheduling and monitoring. Closing the app does not itself pause an active Meta ad.
- No internet hosting is required for this local dashboard. Incoming Meta webhooks are a separate feature and are not made reachable by this setup.
- If port 8000 is busy, stop the conflicting process or start on port 8001 and visit http://127.0.0.1:8001/.
- If login fails, use `API_ADMIN_KEY` from the new laptop's `.env` and restart after changes.
- If Meta access fails, recheck token expiry and asset permissions; do not create duplicate campaigns.
- Do not run the scripts that prepare, reconcile, remove or modify campaigns just to test installation.
- Back up the stopped database and `.env` regularly. Do not independently operate two divergent copies. Before reverting to the old laptop after new activity, transfer the latest stopped database back first.

This migration moves application data, not Codex conversation history. Open the copied project in your editor; use the project docs for development handover and retain access to the previous conversation separately.
