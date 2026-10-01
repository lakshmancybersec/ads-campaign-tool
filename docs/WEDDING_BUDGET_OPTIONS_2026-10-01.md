# Wedding Collection budget diagnosis — 1 October 2026

## Unchanged saved campaign

- Account: `act_249780244315816`.
- Meta campaign: `120254199040930204`; paused.
- Local state: FAILED after the ad-set rejection. No ad set, creative or ad IDs.
- Saved mode remains FIXED, daily allowance INR 150, total allowance INR 150. Adding Dynamic controls did not change this approved campaign.
- Dates: 1 October through 2 October 2026, inclusive; timezone Asia/Kolkata.
- Daily application scheduling window: 00:20–23:09 IST.
- API end: **3 October 2026 00:00 IST** (exclusive end of the saved last day).
- API start: `max(saved start-date midnight, request time + five minutes)`.

The original failed request's exact runtime start timestamp was not persisted. It cannot honestly be reconstructed. The saved plan and request builder determine the other parameters exactly.

## Relevant failed request parameters

`campaign_id=120254199040930204`, `lifetime_budget=15000` paise,
`billing_event=IMPRESSIONS`, `optimization_goal=LINK_CLICKS`,
`bid_strategy=LOWEST_COST_WITHOUT_CAP`, `destination_type=WEBSITE`,
`status=PAUSED`, Facebook placement, ages 20–60, and the nine saved region/city targets.
Parent objective is OUTCOME_TRAFFIC. No daily budget was submitted because the lifetime amount already limited total spending to the approved daily allowance.

The application's daily operating window is enforced by its scheduler; it was not submitted as an ad-set schedule. Meta evaluates the ad set's continuous start/end span for this lifetime budget.

## Validation-only results

All remote POST probes explicitly forced `execution_options=[validate_only]`. No returned object IDs, Meta creations, approvals, budget updates or activation were requested.

The initial automatic review rejected the diagnostic execution, believing it lacked validate_only. Inspection demonstrated the flag in both the payload and serialization. The flag was made explicit at the final call site, and a renewed review allowed execution. The rejected invocation did not run.

Final probe start: **1 October 2026 09:03:10.904798 IST**.
Original end: **3 October 2026 00:00 IST**; elapsed span approximately **38.947 hours**.

| Variant | Result |
|---|---|
| Original end, INR 150 lifetime | Rejected 100/1885272: required more than INR 156.33 at this later start time |
| Original end, INR 158 lifetime plus INR 150 daily_spend_cap | Rejected 100/1885624: this ad-set-budget configuration does not accept the separate spend-cap/target combination |
| Original end, INR 158 lifetime without a separate daily cap | Validation succeeded; fits an owner-approved INR 158 daily ceiling because the entire lifetime allowance is INR 158 |
| 24 hours from probe start, INR 150 lifetime | Validation succeeded |
| End 1 October (API end 2 October 00:00 IST), INR 150 lifetime | Validation succeeded |

These successful variants also required `targeting_automation.advantage_audience=0`. Without that explicit flag Meta rejected them with 100/1870227. The adapter now includes it, preserving the specified audience rather than opting into Advantage expansion.

## Cause and interpretation

The rejection is a **lifetime-budget minimum for the submitted duration/configuration**, not a demand for INR 157.79 each day, nor a billing-payment request. Changing only duration allowed INR 150 to validate while preserving objective, billing event and optimization goal.

The earlier request reported INR 157.79. Later starts shortened the remaining span and the reported minimum dropped through INR 156.43 to INR 156.33. This confirms the threshold is not a permanent constant. The previously observed account minimum daily budget was 9633 paise; multiplying INR 96.33 by the final span/24 gives approximately INR 156.32, close to the response after rounding. That is supporting arithmetic, not a claim to know Meta's complete internal minimum calculation.

## Choices requiring owner approval

**A — preserve budget:** end on 1 October instead of 2 October. Keep INR 150/day and INR 150 total; revalidate when approved. This passed and is the lowest-change option.

**B — preserve end date:** explicitly approve a daily ceiling of INR 158 and a total of INR 158, within the permitted Dynamic INR 150–200 range and INR 1,050 maximum. This passed as a lifetime allowance of INR 158. It is not INR 158 spent each day. It changes two approved limits and has not been applied.

**C — alternative supported configuration:** requires further validation and owner approval. Do not silently remove a necessary daily safeguard or change objective/optimization merely to pass validation. The separately specified daily cap failed for this ad-set-budget structure.

**D — cancel:** requires explicit owner instruction; no cancellation occurred.

For daily-spend planning, floor(1050/158) = **6 full days**: INR 948, leaving INR 102. Seven such days cost INR 1,106 and exceed the limit. At INR 150/day the arithmetic permits seven days; at INR 200/day it permits five. These are affordability calculations, **not proof that the current adapter can enforce those multi-day daily ceilings on Meta**. The separate cap rejection means that requires a validated supported configuration.

No evidence shows the existing date span is incompatible with the INR 1,050 ceiling: the INR 158-total option passed. Therefore the dashboard must not claim this campaign cannot fit within INR 1,050. The requested infeasibility message is shown only when the reported required total actually exceeds that ceiling.

## Changes and tests

- `app/services/deployment.py`: explicit Advantage audience flag, no budget/date modification.
- `app/services/budget_diagnosis.py`: read-only minimum interpretation and owner options, no automatic selection.
- `app/api/integrations.py`: exposes diagnosis alongside existing workflow state.
- `app/static/dashboard.js`, `dashboard.html`: display diagnosis/options and versioned asset.
- `scripts/validate_wedding_budget_options.py`: bounded validation-only probes on the existing campaign; safe non-secret evidence in ignored local-backups.
- `tests/test_budget_diagnosis.py`: total-versus-daily interpretation, strict minimum arithmetic, no plan mutation, infeasible-ceiling message, no guessing on missing errors, and targeting preservation.
- Full suite: **129 passed**; JavaScript syntax check passed. Existing non-fatal deprecation/cache warnings remain.

No database schema changes. No duplicate parent campaign. No budget increase, date change, payment transition or publishing. Owner selection is still required before the failed ad-set step can be retried; successful stored parent ID must be reused.
