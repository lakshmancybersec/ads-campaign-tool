"""Credential-free MCP connectivity probe. No tools are listed or executed."""
import httpx

ADS_MCP_URL = "https://mcp.facebook.com/ads"


async def probe_ads_mcp(transport=None):
    result = {"endpoint": ADS_MCP_URL, "connected": False, "tool_execution_enabled": False}
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=False, transport=transport) as client:
            response = await client.post(ADS_MCP_URL, headers={"Accept": "application/json, text/event-stream"},
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                    "protocolVersion": "2025-03-26", "capabilities": {},
                    "clientInfo": {"name": "lakshiya-readiness-check", "version": "0.1.0"}}})
    except httpx.HTTPError:
        return {**result, "status": "unreachable", "note": "Connection failed. Current Marketing API integration remains available."}
    if response.status_code in {401, 403}:
        return {**result, "status": "authorization_required", "note": "Meta requires authorization or account access. No MCP login is configured in this application yet."}
    # Even a successful anonymous response is not an authenticated account connection.
    return {**result, "status": "setup_required", "http_status": response.status_code,
            "note": "Endpoint responded. OAuth/client eligibility and supported tools must be verified before integration. No account is connected."}
