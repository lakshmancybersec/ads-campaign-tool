"""Record the owner's explicit Option A approval; create real PAUSED objects."""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding='utf-8')
from app.database import SessionLocal
from app.models.campaign import Campaign
from app.models.deployment import CampaignDeployment
from app.models.approval import Approval
from app.services.meta_workflow import workflow
from app.services.deployment import prepare
from app.services.meta_client import MetaClient, MetaError

async def main():
    client = MetaClient()
    assert client.account == 'act_249780244315816'
    assert datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat() == '2026-10-01', 'Approved shortened date is no longer current'
    with SessionLocal() as db:
        c = db.get(Campaign,'79b0f1e1-b75b-4dbb-9ff6-5e0ec46c4d29')
        d = db.get(CampaignDeployment,c.id)
        assert d.remote_campaign_id == '120254199040930204'
        assert not d.operation and not d.automation_enabled
        assert c.daily_budget_inr == c.weekly_budget_limit_inr == 150
        remote = await client.request('GET',d.remote_campaign_id,{'fields':'id,account_id,status'})
        assert remote['account_id'] == '249780244315816' and remote['status'] == 'PAUSED'
        plan = json.loads(d.plan_json)
        if plan['end_date'] != '2026-10-01':
            assert not any([d.remote_adset_id,d.remote_creative_id,d.remote_ad_id])
            Path('local-backups').mkdir(exist_ok=True)
            Path('local-backups/wedding-before-option-a.json').write_text(d.plan_json,encoding='utf-8')
            plan['end_date'] = '2026-10-01'
            approval = Approval(campaign_id=c.id,status='APPROVED',selected_product_code=plan['product_code'],
                                decision_note='Owner explicitly approved Option A: INR 150 total, end 1 October 2026. Real paused creation only; separate final launch approval required.',
                                decided_at=datetime.now(timezone.utc))
            db.add(approval)
            db.flush()
            d.plan_json = json.dumps(plan,sort_keys=True)
            d.approval_id = approval.id
            c.status = 'READY'
            state = workflow(db,c.id)
            state.owner_status = 'AWAITING_OWNER_APPROVAL'
            state.payment_status = 'NOT_REQUESTED'
            state.verified = False
            db.commit()
        try:
            result = await prepare(db,c,client)
            print('Verified real objects:',result.remote_campaign_id,result.remote_adset_id,result.remote_creative_id,result.remote_ad_id)
        except MetaError as error:
            print('Stopped:',error)

if __name__ == '__main__':
    asyncio.run(main())
