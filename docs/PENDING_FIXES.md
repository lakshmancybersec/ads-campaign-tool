# Local workflow fixes

The two code findings in VALIDATION_REPORT_2026-09-26.md are now addressed:

- A saved campaign plan is required before an approval request. The dashboard lists only campaigns with saved plans in the approval selector. Legacy approvals without a linked plan cannot be approved, but can be rejected so the plan can be corrected.
- Weekly conversation metrics are null when there are no snapshots or any snapshot lacks conversation data. Measured zero remains zero. Incomplete totals do not produce a misleading cost per conversation or positive conversation recommendation. The report includes `conversation_data_complete`.

Validation: 74 automated tests passed, with two existing dependency deprecation warnings. Provider writes are mocked. JavaScript syntax check passes.

Deployment scope: local laptop, not public hosting. Keep the laptop awake, online and the application running for scheduler and monitoring. Losing the local process does not stop an active Meta ad. Remote budget/end-date controls remain important.

Live-test requirements are unchanged: replacement of exposed credentials, owner-approved complete plan and budget, actual payment confirmation as required by the current workflow, followed by a paused Meta preparation test. No live writes were enabled by these fixes. WhatsApp notifications/webhooks are optional and separate from the WhatsApp ad destination.

Other validation limits still apply: no live ad creation/delivery test, interactive browser test or dependency CVE scan in this change. Summed daily reach is not deduplicated weekly reach.
