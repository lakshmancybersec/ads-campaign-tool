# Lakshiya Dhotis Ads Agent

Owner-approved Meta advertising application using FastAPI, SQLAlchemy, a web dashboard and optional n8n workflows.

## Current workflow

Import a Meta catalog (or add products manually), create a draft, save caption, targeting and schedule, approve the plan, record verified payment references, prepare paused Meta ads, then explicitly activate.

Live operations are gated by configuration. Tests use simulated provider responses; no real ads or messages were sent during development. Read [live setup and limitations](docs/LIVE_SETUP.md) before connecting an account.

## Included

- Catalog, drafts, owner approval, manual payment references and lead capture.
- Frozen campaign plan containing the photo, caption, audience, dates and budgets.
- Meta account check, catalog import, paused campaign/ad-set/creative/ad creation, activation, pause and end.
- Built-in peak-time scheduling, spend checks and hourly performance collection.
- WhatsApp approval templates and signed owner replies.
- Dashboard, analytics and disabled n8n templates.

The first adapter uses traffic ads linking to WhatsApp. Conversation optimization, email delivery, broader notifications and social video publishing remain separate work.

## Local setup

1. Use Python 3.12+ and create a virtual environment.
2. Install dependencies: `pip install -r requirements.txt`.
3. Copy `.env.example` to `.env` only if no `.env` exists. Set a private admin key and database URL. Leave provider write flags disabled initially.
4. Run `uvicorn app.main:app --reload`.
5. Open http://127.0.0.1:8000/ and enter your `API_ADMIN_KEY`.

Restart after configuration changes. Startup adds missing tables without resetting existing data.

## Tests

Run `pytest -q -p no:cacheprovider`. Integration tests use isolated SQLite and mocked HTTP requests.

## Deployment

Docker Compose includes PostgreSQL and optional n8n. Replace development passwords, protect database ports, back up data and configure HTTPS before public deployment. Use one application worker and keep it online for scheduling.

## Owner controls

Preparing creates paused ads; activation is a separate spending action. Both approval and confirmed payments covering the budget limit are required. Manual pause disables automatic resumption. Ended campaigns cannot restart. No automatic budget increases or bank transactions are implemented.

Interrupted remote writes require reconciliation, not blind retries. See the setup guide for account prerequisites, operation recovery and remaining limitations.
