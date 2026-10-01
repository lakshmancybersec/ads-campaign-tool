# Ads MCP integration preparation

Implemented: authenticated dashboard connectivity check against https://mcp.facebook.com/ads using a credential-free MCP initialize request. No Meta/API/admin credential is forwarded. No tools are called and no account connection is claimed, even on HTTP 200. Redirects are not followed.

Not implemented: OAuth client registration/eligibility, user authorization callback, token storage/refresh, tool discovery, or tool execution. Meta's developer documentation and business help page were inaccessible during preparation; exact supported client setup remains unverified. The Marketing API token must not be assumed to authorize this MCP service.

Next integration work requires accessible official setup documentation and a successful owner-authorized Meta OAuth flow. Do not substitute a third-party connector silently. Start with explicitly reviewed reporting tools; discovery alone is not permission to execute tools. Campaign write tools must remain unavailable until mapped through the application's immutable plan, owner budget approval and activation controls. MCP must not auto-confirm payments or increase budgets.

Existing campaign operations continue through the Marketing API. This preparation does not turn the application into an AI agent and does not launch ads.

## Local payment requests

Select an approved campaign in the payment section and click Request payment on WhatsApp. The application builds a wa.me link addressed to OWNER_WHATSAPP_NUMBER, with campaign, product, approved daily/total budgets and outstanding confirmed-payment amount. Review the text, click Open WhatsApp, and manually press Send.

No Cloud API, public hosting, automatic send, transaction verification or delivery confirmation is involved. Pay Meta directly; the link is a message link, not a payment processor. If already funded, verify the existing payment rather than paying again. Payment confirmation remains a separate explicit owner action.
