"""Prepare the explicitly approved Wedding Collection; never activate it."""
import asyncio
import re
import sys
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import httpx
from app.database import SessionLocal
from app.models.campaign import Campaign
from app.services.deployment import prepare
from app.services.meta_client import MetaClient, MetaError

class Diagnostics(httpx.AsyncBaseTransport):
    def __init__(self):
        self.inner = httpx.AsyncHTTPTransport()
    async def handle_async_request(self, request):
        response = await self.inner.handle_async_request(request)
        await response.aread()
        if response.is_error:
            error = response.json().get('error', {})
            from app.config import get_settings
            s = get_settings()
            for key in ['code', 'error_subcode', 'error_user_title', 'error_user_msg', 'message']:
                value = str(error.get(key, ''))
                for secret in [s.meta_access_token, s.meta_app_secret, s.api_admin_key]:
                    if secret:
                        value = value.replace(secret, '[redacted]')
                value = re.sub(r'https?://\S+', '[URL]', value)
                print(key + ':', value[:1500])
        return response
    async def aclose(self):
        await self.inner.aclose()

class DiagnosticClient(MetaClient):
    async def request(self, method, path, params=None):
        return await super().request(method, path, {**(params or {}), 'locale': 'en_US'})

async def main():
    with SessionLocal() as db:
        campaign = db.get(Campaign, '79b0f1e1-b75b-4dbb-9ff6-5e0ec46c4d29')
        assert campaign and campaign.status in {'READY','FAILED'}
        assert campaign.daily_budget_inr == campaign.weekly_budget_limit_inr == 150
        try:
            d = await prepare(db, campaign, DiagnosticClient(transport=Diagnostics()))
            print('Prepared paused:', d.remote_campaign_id, d.remote_adset_id, d.remote_ad_id)
        except MetaError as error:
            print('Preparation stopped:', error)

if __name__ == '__main__':
    asyncio.run(main())
