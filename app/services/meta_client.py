"""Bounded Graph requests; tokens never appear in URLs, exceptions or responses."""
import hashlib
import hmac
import json
import re

import httpx

from app.config import get_settings


class MetaError(ValueError):
    def __init__(self, message, *, definitive=False):
        super().__init__(message)
        self.definitive = definitive


def configured(value: str | None) -> bool:
    return bool(value and not any(word in value.lower() for word in ("replace", "placeholder", "put-", "your-")))


class MetaClient:
    def __init__(self, transport=None):
        self.settings = get_settings()
        self.transport = transport

    @property
    def account(self):
        value = (self.settings.meta_ad_account_id or "").removeprefix("act_")
        if not value.isdigit():
            raise MetaError("Configure a valid META_AD_ACCOUNT_ID.")
        return f"act_{value}"

    async def request(self, method, path, params=None):
        s = self.settings
        if not configured(s.meta_access_token):
            raise MetaError("Configure META_ACCESS_TOKEN, then restart the application.")
        if not re.fullmatch(r"[A-Za-z0-9_]+(?:/[A-Za-z0-9_]+)?", path):
            raise MetaError("Invalid Meta resource identifier.")
        values = {k: json.dumps(v) if isinstance(v, (dict, list, bool)) else v for k, v in (params or {}).items()}
        if s.meta_app_secret:
            values["appsecret_proof"] = hmac.new(s.meta_app_secret.encode(), s.meta_access_token.encode(), hashlib.sha256).hexdigest()
        try:
            async with httpx.AsyncClient(timeout=25, transport=self.transport) as client:
                response = await client.request(method, f"https://graph.facebook.com/{s.meta_api_version}/{path}",
                    headers={"Authorization": f"Bearer {s.meta_access_token}"},
                    **({"params": values} if method == "GET" else {"data": values}))
        except httpx.HTTPError:
            raise MetaError("Meta connection failed. For a write, check Ads Manager before retrying.") from None
        try:
            data = response.json()
        except ValueError:
            raise MetaError("Meta returned an unreadable response.") from None
        if response.is_error or not isinstance(data, dict) or "error" in data:
            error = data.get("error", {}) if isinstance(data, dict) else {}
            if not isinstance(error, dict):
                error = {}
            code = error.get("code")
            subcode = error.get("error_subcode")
            hint = {
                4834011: "Campaign creation requires is_adset_budget_sharing_enabled=false.",
            }.get(subcode, "Check permissions, account setup and request parameters.")
            # Display only a short redacted user-facing explanation, never the
            # provider's raw payload, request URL or debug trace.
            detail = str(error.get('error_user_msg') or error.get('error_user_title') or '')
            for name in type(s).model_fields:
                if any(part in name for part in ('secret', 'token', 'password', 'admin_key')):
                    value = getattr(s, name, None)
                    if isinstance(value, str) and value:
                        detail = detail.replace(value, '[redacted]')
            detail = re.sub(r'https?://\S+|[A-Za-z0-9_-]{40,}', '[redacted]', detail)
            detail = ' '.join(detail.split())[:300]
            # Never echo provider messages, request bodies or URLs containing secrets.
            raise MetaError(f"Meta rejected the request (HTTP {response.status_code}, code {code if isinstance(code, int) else 'unknown'}, subcode {subcode if isinstance(subcode, int) else 'unknown'}). {detail or hint}", definitive=response.status_code == 400 and code in {100, 190, 200, 10})
        return data

    async def all_pages(self, path, params):
        result, cursor = [], None
        for _ in range(100):
            data = await self.request("GET", path, {**params, **({"after": cursor} if cursor else {})})
            rows = data.get('data', [])
            if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                raise MetaError('Meta returned an invalid collection response.')
            result.extend(rows)
            paging = data.get("paging", {})
            if not paging.get("next"):
                return result
            next_cursor = paging.get("cursors", {}).get("after")
            if not next_cursor or next_cursor == cursor:
                raise MetaError("Meta pagination could not be completed; no import was committed.")
            cursor = next_cursor
        raise MetaError("Import exceeds the supported page limit; no import was committed.")

    async def validate_account(self):
        account = await self.request("GET", self.account, {"fields": "id,name,account_status,currency,timezone_name"})
        if account.get("account_status") != 1 or account.get("currency") != "INR":
            raise MetaError("The ad account must be active and use INR.")
        return account

    def require_writes(self, preparation=False):
        s = self.settings
        if not s.meta_live_writes_enabled and not (preparation and s.meta_paused_preparation_enabled):
            raise MetaError("Live Meta writes are disabled. Complete account setup before enabling META_LIVE_WRITES_ENABLED.")
        if not configured(s.api_admin_key) or len(s.api_admin_key or "") < 32:
            raise MetaError("Replace the placeholder API_ADMIN_KEY with a random key of at least 32 characters before enabling live writes.")
        if not configured(s.meta_app_secret):
            raise MetaError("Configure META_APP_SECRET before enabling live writes.")

    async def spend(self, campaign_id, start, end):
        from decimal import Decimal
        result = await self.request("GET", f"{campaign_id}/insights", {
            "fields": "spend", "time_range": {"since": start, "until": end}})
        return sum((Decimal(row["spend"]) for row in result.get("data", [])), Decimal(0))
