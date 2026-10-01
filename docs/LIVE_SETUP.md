# Campaign approval and live integration

The application now implements the local-to-Meta workflow. It has been tested
with simulated Graph API responses, not with this business's live credentials.
No ads or messages were sent during development.

## What is implemented

- Account connection check (active account, INR currency).
- Commerce Manager product import with pagination; repeated imports update products.
- Campaign review containing the actual product photo URL, caption, dates, age range,
  location IDs/names, peak windows, destination, placements and budget.
- Owner approval bound to the saved plan. Approved plans cannot be edited.
- Confirmed manual payment references must total at least the campaign's budget limit.
- Campaign, ad set, creative and ad creation in PAUSED state, with persisted remote IDs.
- Separate explicit activation, pause and end actions.
- Activation checks account ownership, remote budget/end time, approval, funding,
  availability, dates, peak hours and current spend. Parent campaign is activated last.
- Campaign spend cap on Meta plus local spend checks. API reporting/billing delays mean
  local polling is not a guarantee of exact final billed spend.
- Built-in scheduler (default every 60 seconds) and hourly performance collection.
- Manual pause disables automatic resumption. End is terminal. Failed spend retrieval
  never resumes an ad and attempts to pause an active campaign.
- Signed WhatsApp owner decisions and an explicit Send to owner WhatsApp action using
  an approved message template. Customer messages still feed lead capture.

## Credentials and business identifiers

Keep values in `.env`; do not put tokens in chat, screenshots or source control.
The existing `.env` was not overwritten. New settings are listed in `.env.example`.

For Meta:

| Setting | Purpose |
| --- | --- |
| `API_ADMIN_KEY` | Replace the development placeholder with a random value of 32+ characters |
| `META_ACCESS_TOKEN` | Token granted access to this business's ad account and relevant assets |
| `META_APP_SECRET` | App secret for request proof |
| `META_AD_ACCOUNT_ID` | Ad account ID, with or without `act_` |
| `META_API_VERSION` | Supported version for the app; current code retains the existing v22.0 default |
| `FACEBOOK_PAGE_ID` | Numeric Page ID, not the Page URL |
| `INSTAGRAM_ACTOR_ID` | Optional Instagram identity; without it this adapter uses Facebook only |
| `META_CATALOG_ID` | Commerce Manager catalog ID, required only for catalog import |
| `CUSTOMER_WHATSAPP_NUMBER` | Customer destination number, country code plus digits |
| `META_LIVE_WRITES_ENABLED` | Leave false until account setup is reviewed; true allows dashboard write actions |
| `SCHEDULER_ENABLED` | Keep true for live operation |

Meta asset access and account eligibility must be verified in the business's account.
An account read check does not certify write permissions, ad review, linked Instagram
identity or creative compatibility. Test those by preparing paused ads.

For owner WhatsApp approval:

- Configure `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`,
  `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_APP_SECRET`, and `OWNER_WHATSAPP_NUMBER`.
- Configure `PUBLIC_DASHBOARD_URL` with an HTTPS URL reachable by the owner.
- Configure Meta's webhook URL as `https://YOUR_HOST/webhooks/whatsapp` and subscribe
  to message events. Signature verification is mandatory at the HTTP endpoint.
- Create and obtain approval for a template with four positional body text parameters:
  campaign name, product code, approval ID, dashboard URL (in that order).
- Example body for Meta review:
  `Campaign {{1}}, product {{2}}, is ready for your review. Open {{4}} and review its
  photo, caption, audience, schedule and budget. Reply APPROVE {{3}} or REJECT {{3}}.`
- Set `WHATSAPP_APPROVAL_TEMPLATE` to its approved name and
  `WHATSAPP_TEMPLATE_LANGUAGE` to its approved locale, then enable
  `WHATSAPP_NOTIFICATIONS_ENABLED=true`.
- The notification provides a dashboard link; the owner must review the plan there.
  WhatsApp replies record approval only. They never activate an ad or confirm payment.
- Notification sends are not retried automatically after an uncertain response.

## Run and use

1. Back up the database before upgrading. Startup adds the new `campaign_deployments`
   and `approval_notifications` tables without changing existing table columns.
2. Restart the application after changing `.env`:
   `.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
3. Run one application worker. Keep the service and Internet connection available.
   For public deployment, put the service behind HTTPS; do not expose the development
   Docker database port or use the placeholder admin key.
4. Open the dashboard and run **Check Meta connection**. Import the catalog or add a
   product manually. Imports skip non-INR products, fractional-rupee prices and invalid
   records because the current local price field holds whole rupees.
5. Create a draft. Search and add target locations, select a product, enter caption,
   start/end dates and daily peak hours. Save the plan. The API supports multiple
   windows; the first dashboard form exposes one window.
6. Request approval for the same product. Review the full saved plan. Approve in the
   dashboard or send it to the owner using the configured WhatsApp template.
7. Record actual externally verified payment references covering the budget limit.
8. When live writes are deliberately enabled, click **Prepare paused ads**.
   Inspect the remote campaign, ad set and ad in Ads Manager before activation.
9. **Activate approved campaign** is a separate spending action. It is permitted only
   within the reviewed dates and peak hours. Automatic scheduling starts after this
   first activation; it does not automatically launch a merely READY campaign.
10. **Pause** disables automatic resumption. **End campaign** pauses Meta delivery and
    ends the local campaign permanently. Create a new campaign for a subsequent week.

The internal worker owns scheduling and collection. The n8n scheduler/collector
templates call the same protected endpoints but remain disabled; use one scheduling
owner, not both. Set n8n's API URL and key if you use its workflows for diagnostics.

## Failed or interrupted operations

Remote creation has no automatic retries. A timeout might mean Meta created the
object but the response was lost. The dashboard shows the operation and any IDs saved
before failure. Check Ads Manager, pause any affected remote campaign, and reconcile
the stored IDs with developer assistance before clearing an operation marker.
There is intentionally no blind retry/unlock button. Use Ads Manager directly to
pause delivery if the local app, network or a pending operation prevents local pausing.

## Current limitations

- The first publishing adapter creates traffic ads linking to `wa.me`, optimized for
  link clicks. It is **not** the conversation-optimized click-to-WhatsApp ad format.
  Account-specific conversation optimization remains a follow-up after live validation.
- Static catalog images only; photo/video uploads and social content publishing are
  separate scope. Native catalog/dynamic ads are not implemented by this adapter.
- No email delivery or automatic start/pause/end/budget-alert WhatsApp messages yet.
  The implemented WhatsApp outbound flow is the owner approval template.
- Performance collection stores campaign-level daily metrics; daily reach is not a
  deduplicated weekly reach figure. Location/creative breakdown reports remain pending.
- Credentials and public hosting are missing locally, so Meta schema/permissions,
  messaging template approval and actual ad delivery have not been live-verified.

## Primary references

- [Meta Marketing API collection](https://www.postman.com/meta/facebook-marketing-api/overview)
- [Meta campaign/ad-set/creative onboarding](https://www.postman.com/meta/facebook-marketing-api/documentation/9jo4f5y/mapi-onboarding)
- [Meta WhatsApp template examples](https://www.postman.com/meta/whatsapp-business-platform/request/v43klng/send-sample-issue-resolution-template)
- [Meta SDK product fields](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/productitem.py)

Provider documentation describes the request structures; mocked tests do not establish
live account eligibility. Verify current API version and permissions during onboarding.
