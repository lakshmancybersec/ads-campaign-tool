"""Reconcile only the known HTTP 400/4834011 Wedding campaign rejection.

Never use this to clear transport failures or arbitrary operations.
"""
import asyncio
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.database import init_db, SessionLocal
from app.models.campaign import Campaign
from app.models.deployment import CampaignDeployment
from app.services.meta_client import MetaClient
from app.services.meta_workflow import workflow

async def main():
    init_db()
    client = MetaClient()
    with SessionLocal() as db:
        c = db.get(Campaign, '79b0f1e1-b75b-4dbb-9ff6-5e0ec46c4d29')
        d = db.get(CampaignDeployment, c.id)
        assert c.name == 'Wedding Collection' and d.operation == 'create:campaigns'
        assert not any([d.remote_campaign_id,d.remote_adset_id,d.remote_creative_id,d.remote_ad_id,d.automation_enabled])
        rows = await client.all_pages(client.account + '/campaigns', {'fields':'id,name', 'limit':100})
        assert not any(r.get('name') == c.name for r in rows), 'Matching Meta campaign exists; manual reconciliation needed'
        state = workflow(db,c.id)
        state.ad_account_id = client.account
        state.creation_status = 'CREATION_FAILED'
        state.retry_safe = True
        state.last_error = 'Previous HTTP 400/100/4834011 rejection: missing is_adset_budget_sharing_enabled. No matching campaign found during reconciliation.'
        d.last_error = state.last_error
        d.operation = None
        c.status = 'FAILED'
        db.commit()
        print('Known rejected campaign reconciled; safe retry available. No Meta writes performed.')

if __name__ == '__main__':
    asyncio.run(main())
