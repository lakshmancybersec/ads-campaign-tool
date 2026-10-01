from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings


@dataclass(frozen=True)
class MetaCampaignInsight:
    campaign_id: str
    spend_inr: float
    reach: int
    impressions: int
    clicks: int
    ctr: float
    cpc_inr: float


class MockMetaAdsService:
    """Development-only, read-only Meta Ads substitute. It makes no network calls."""

    def get_campaign_status(self, campaign_id: str) -> str:
        return "PAUSED"

    def get_insights(self, campaign_id: str) -> MetaCampaignInsight:
        return MetaCampaignInsight(campaign_id, 0.0, 0, 0, 0, 0.0, 0.0)


class MetaAdsReadOnlyService:
    """Limited Meta Graph API client. It exposes insights only and has no write methods."""

    graph_base_url = "https://graph.facebook.com/v22.0"

    def __init__(self, access_token: str | None = None, ad_account_id: str | None = None) -> None:
        settings = get_settings()
        self.access_token = access_token or settings.meta_access_token
        self.ad_account_id = ad_account_id or settings.meta_ad_account_id

    async def get_insights(self, campaign_id: str) -> dict[str, Any]:
        if not self.access_token or not self.ad_account_id:
            raise RuntimeError("Meta read-only credentials are not configured.")
        fields = "spend,reach,impressions,clicks,ctr,cpc,actions,cost_per_action_type"
        from app.services.meta_client import MetaClient
        client = MetaClient()
        client.settings = client.settings.model_copy(update={"meta_access_token": self.access_token,
                                                            "meta_ad_account_id": self.ad_account_id})
        return await client.request("GET", f"{campaign_id}/insights", {"fields": fields, "date_preset": "yesterday"})
