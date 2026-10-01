# Meta campaign and payment flow audit — 1 October 2026

## Actual configuration and root cause

- Runtime: Python/FastAPI, SQLAlchemy/SQLite, HTML/CSS/JavaScript. No PHP application files were found; PHP syntax checking is not applicable.
- Configured account: `act_249780244315816`; configured Graph API version: `v22.0`.
- Existing integration is the official Marketing API. MCP remains a credential-free availability probe and cannot create campaigns or execute tools.
- Local admin API authentication and Graph bearer authentication/app-secret proof remain in place. No credentials were printed or changed.
- The prior Wedding Collection request stopped at **POST account/campaigns**, before any child objects. Meta's validation-only response reproduced HTTP 400, code 100, subcode **4834011**: `is_adset_budget_sharing_enabled` must be supplied for ad-set budgets. The application omitted it.
- Previously, a billing link was displayed after local plan approval alone. No read-back of campaign/ad-set/creative/ad objects was required. The integration view also incorrectly equated one stored ad ID with successful preparation.
- Earlier error handling discarded useful Meta subcodes. A diagnostic script then failed while printing a localized message in the Windows console, leaving a creation checkpoint locked without a useful saved error.

## Fixes

1. Campaign requests explicitly disable ad-set budget sharing. Meta accepted the corrected payload through `execution_options=[validate_only]`.
2. Lifetime ad-set budgets replace the incompatible campaign spend-cap mechanism. When total budget is no greater than the daily limit, the lifetime budget protects both. Larger totals additionally require Meta's `daily_spend_cap`; missing/mismatched caps block verification/activation. There is no fallback that silently raises a budget or removes a required cap.
3. Server-side creation, reuse, saved plans and preparation enforce at most INR 150/day and INR 1,050 total for a plan lasting at most seven days. Existing owner-entered lower limits are preserved.
4. All four object IDs are durably checkpointed. Read-back checks exact IDs, account ownership, campaign/ad-set/creative relationships, budgets, end date and remote statuses. Billing requires a fresh successful check.
5. Definite parameter/permission rejections can be retried, resuming saved successful IDs. Transport failures and missing response IDs retain their lock; no blind retry creates duplicates.
6. Creation failure records FAILED in the campaign lifecycle and CREATION_FAILED in workflow diagnostics. Sync failures are distinct. Exact safe Meta error codes/subcodes and redacted user-facing details are shown.
7. A draft-creation idempotency ledger handles repeated requests with the same key. The dashboard supplies a stable key on retries. In-progress Meta writes retain the existing atomic operation lock.
8. The dashboard shows account and all Meta IDs, verification/connection result, creation and payment states, owner approval, remote statuses, last successful synchronization, and errors.

## Payment and owner approval

The existing preliminary plan approval is retained to freeze product, targeting, dates and budget before remote writes. A separate final owner launch approval is required after Meta creation and billing review.

Flow: save/approve plan → create paused objects → verify all objects → AWAITING_PAYMENT → verify again before issuing the account-specific billing link → PAYMENT_PENDING → owner reviews billing in Meta → re-check all objects → explicit owner launch approval → separate activation action.

The application does **not** infer payment from opening billing, account access, funding-source presence, or owner approval. The current integration cannot prove receipt of a particular payment. `OWNER_REVIEWED_IN_META` is an owner acknowledgement, **not PAYMENT_CONFIRMED**. No synthetic PAYMENT_CONFIRMED or PAYMENT_FAILED result is generated. Pending billing reported by Meta remains PAYMENT_PENDING. Card/UPI credentials are neither requested nor stored. No UPI collect request is initiated.

The billing URL is constructed from the account bound to verified objects:
`https://adsmanager.facebook.com/adsmanager/billing/transactions/?act=249780244315816`.
It is not evidence of creation or payment. Legacy notification routes also require fresh object verification, so they cannot bypass the gate.

## Database changes

Two additive tables are registered with the existing `init_db`/`create_all` startup mechanism:

- `meta_workflows`: account binding, creation/payment/owner states, verification result, safe-retry flag, last successful synchronization, remote statuses, safe last error. One row per campaign.
- `campaign_create_requests`: unique request key, payload hash and local campaign ID.

Existing `campaign_deployments` ID columns and existing campaign/payment/approval data are retained. Repeated initialization is tested. The existing string lifecycle now also accepts FAILED. Local deletion removes the new dependent records where deletion is allowed.

## Live evidence and current blocker

After validating the fix, the known failed checkpoint was reconciled against Meta (no matching campaign), and paused preparation was retried using the existing approved INR 150/day, INR 150 total plan.

- Campaign **Wedding Collection** was created: **120254199040930204**.
- A separate GET confirmed its account is **249780244315816** and its status is **PAUSED**.
- Ad-set creation failed with HTTP 400, code 100, subcode **1885272**: Meta required a budget **above INR 157.79** for the submitted schedule. The approved total is INR 150.
- No ad set, creative or ad IDs exist. Payment and activation buttons are therefore unavailable. No activation or payment request was made.
- This minimum is the response for this particular request, not a universal minimum or permission to increase the budget. The owner must choose revised dates or explicitly approve a revised total within the hard limits; the application does not change either automatically.
- No additional permission change is indicated by these two errors. Successful parent creation verifies that request, not every downstream publishing permission or ad-review outcome.

## Validation

- Full suite: **117 passed**. Includes isolated Edge browser save/approval/create/billing-review/final-approval/logout flow; Meta calls are mocked in automated tests.
- Cases include each of four creation steps rejecting/timing out/omitting IDs, wrong-account objects, changed account configuration, sync/network failures, billing gating, owner approval, safe retry, repeated preparation, draft idempotency, daily/total caps, and repeatable DB initialization.
- `node --check app/static/dashboard.js` and Python compilation passed.
- Local runtime audit: one diagnostic panel, zero payment buttons, zero activation buttons for the failed partial campaign; no browser errors.
- Configured-secret scan across app/tests/scripts/docs/n8n source found no matches. This is a focused check, not a guarantee against every possible secret pattern.
- Non-failing warnings: Starlette/httpx and AnyIO deprecations; pytest cache directory not writable.
- No Ads Manager scraping, credential entry, UPI notification, or spending activation occurred.

## Files changed

Application: `app/services/deployment.py`, `app/services/meta_client.py`, new `app/services/meta_workflow.py`, `app/api/campaigns.py`, `app/api/integrations.py`, `app/api/approvals.py`, new `app/models/meta_workflow.py`, `app/models/__init__.py`, `app/models/enums.py`, `app/static/dashboard.js`, `app/static/dashboard.html`, `app/static/dashboard.css`.

Tests: `tests/test_live_integration.py`, `tests/test_small_budget.py`, `tests/test_meta_payment_flow.py`, `tests/test_browser_approval.py`, `tests/test_payment_email.py`, `tests/test_payment_request_mcp.py`.

Diagnostics: `scripts/prepare_wedding_paused.py` (explicit invocation only), `scripts/reconcile_wedding_rejection.py` (bounded to the known rejected request), `scripts/audit_meta_flow.py`, this report.
