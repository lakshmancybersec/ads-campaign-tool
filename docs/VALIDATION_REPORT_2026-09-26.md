# Validation report — 26 September 2026

Result: local smoke checks and 60 automated test cases pass. This is not a production security certification or proof of live advertising delivery.

## Execution

- `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`: 60 passed, two third-party deprecation warnings.
- `.venv\Scripts\python.exe -m pip check`: no broken requirements.
- `node --check app/static/dashboard.js`: passed.
- Running server at localhost:8000: health, dashboard HTML and JavaScript returned 200; unauthenticated campaign listing returned 401; authenticated dashboard overview returned 200.
- Added regression checks use an isolated in-memory database. Provider operations in integration tests use mocked HTTP transports.
- No real campaigns, messages, payments or spending were initiated during this validation.

## Feature coverage

| Feature | Evidence / limitation |
| --- | --- |
| Dashboard startup and assets | Real local HTTP smoke check; HTML/JavaScript element references checked. No interactive browser click-through. |
| Authentication | Missing/wrong keys rejected on tested business reads and writes; missing configured key fails closed; malformed Unicode key rejected. |
| Secret handling | Environment paths not served; Graph errors redact provider text; arbitrary Graph resource URLs rejected. This is a targeted review, not exhaustive penetration testing. |
| Catalog | Mocked repeat import, numeric-paise and formatted-INR prices tested; fractional-rupee products skipped. Previous real import is not repeated in this run. |
| Budgets | Explicit positive integer owner inputs required; chosen values retained; approval snapshot budget changes rejected. |
| Approval and payments | Approval/payment gates, duplicate reference rejection, full budget coverage and frozen pending plans tested. Payment records are manual assertions, not bank verification. |
| Meta preparation | Mocked campaign/ad set/ad created paused, repeat preparation idempotent, uncertain writes not blindly retried. Real creation remains unverified. |
| Delivery controls | Mocked activation order, budget/time/date guards, pause and terminal end tested. |
| Scheduler | Timezone/window logic and spend-threshold stop tested with mocks; no long-running production endurance test. |
| Analytics | Snapshot calculations, weekly report and daily collection deduplication tested. See limitations below. |
| WhatsApp approval | Signed owner decision, customer isolation, duplicate webhook handling and one-time template attempt tested with mocks. Real delivery not tested/configured. |
| Lead scoring | Rules and signed customer webhook path tested. No automatic ingestion from the ordinary WhatsApp Business app is established. |
| AI recommendations | Existing rule-based recommendation tests pass; no LLM agent, MCP or JARVIS validated. |
| Reels/upload/music | Not implemented; not testable as existing features. |

## Fixes made during this review

1. Required admin authentication for campaign, catalog and setup read endpoints that previously exposed operational metadata without authentication.
2. Compared admin keys as UTF-8 bytes to reject malformed Unicode keys without a server error.
3. Added 22 test cases covering access control, smoke checks, price formats, analytics, duplicate payment and remote-path restrictions.

## Open findings and live-test gates

- Approval requests can still be made without a saved deployment plan. This creates confusing pending/ready records; remote preparation rejects them. Require a complete plan before requesting approval in a follow-up fix. Existing incomplete pending records need rejection and reconfiguration.
- Weekly analytics currently aggregate absent conversation values as zero, which can mislead recommendations. Preserve unavailable data separately from measured zero before relying on conversion reporting. Summed daily reach also is not unique weekly reach.
- The current ad adapter optimizes traffic/link clicks to a WhatsApp URL, not native WhatsApp conversation optimization. A click is not proof of an enquiry.
- Rotate the previously shared Meta token; rotation was not verified in this run.
- Live writes remain disabled. A complete owner-selected plan, explicit approval, payment confirmation record and a paused Meta creation test are still required before delivery.
- WhatsApp sender credentials, approved template and public HTTPS dashboard/webhook configuration are not live-validated. Owner notification setup is optional for dashboard approval.
- No installed browser automation, dependency vulnerability scanner or static security scanner was available. `pip check` checks compatibility, not known vulnerabilities. Interactive browser, dependency CVE, deployment/TLS, load, backup/restore and sustained scheduler tests remain outstanding.
- Two test-client dependency deprecation warnings remain; they did not fail tests.
- The directory has no accessible Git repository metadata, so a Git diff review could not be performed. `.gitignore` lists `.env`, but that does not establish historical secret exclusion.

Recommendation: suitable for continued local testing, not yet cleared for unattended paid campaigns or public deployment.
