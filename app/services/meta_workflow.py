from datetime import datetime, timezone
import json
from app.models.meta_workflow import MetaWorkflow
from app.models.deployment import CampaignDeployment
from app.services.meta_client import MetaClient, MetaError

def workflow(db, campaign_id):
    item = db.get(MetaWorkflow, campaign_id)
    if not item:
        item = MetaWorkflow(campaign_id=campaign_id, creation_status='DRAFT', payment_status='NOT_REQUESTED',
                            owner_status='AWAITING_OWNER_APPROVAL', verified=False, connection_ok=False, retry_safe=False)
        db.add(item)
        db.flush()
    return item

def enforce_limits(plan):
    mode = plan.get('budget_mode', 'FIXED')
    cap = 200 if mode == 'DYNAMIC' else 150
    if mode not in {'FIXED','DYNAMIC'} or not 0 < plan['daily_budget_inr'] <= cap or not 0 < plan['weekly_budget_inr'] <= 1050:
        raise MetaError('Budget exceeds the approved mode ceiling or INR 1050 total limit.')
    if mode == 'DYNAMIC' and not 150 <= plan.get('daily_budget_min_inr', 0) <= plan['daily_budget_inr'] <= 200:
        raise MetaError('Dynamic budgets require an explicit approved INR 150–200/day range.')

async def verify_objects(db, campaign, client=None):
    client = client or MetaClient()
    state = workflow(db, campaign.id)
    d = db.get(CampaignDeployment, campaign.id)
    state.verified = False
    try:
        if not d or not all([d.remote_campaign_id, d.remote_adset_id, d.remote_creative_id, d.remote_ad_id]):
            raise MetaError('All four Meta object IDs are required before billing or activation.')
        if d.operation:
            raise MetaError('A pending Meta operation must be reconciled before verification.')
        if state.ad_account_id != client.account:
            raise MetaError('Configured ad account differs from the account used for creation.')
        await client.validate_account()
        state.connection_ok = True
        fields = [
            (d.remote_campaign_id, 'id,account_id,status,effective_status'),
            (d.remote_adset_id, 'id,account_id,campaign_id,status,daily_budget,lifetime_budget,daily_spend_cap,end_time'),
            (d.remote_creative_id, 'id,account_id'),
            (d.remote_ad_id, 'id,account_id,campaign_id,adset_id,creative,status,effective_status'),
        ]
        results = []
        for identifier, requested in fields:
            row = await client.request('GET', identifier, {'fields': requested})
            if str(row.get('id')) != identifier or str(row.get('account_id')) != client.account.removeprefix('act_'):
                raise MetaError('Meta object is missing or belongs to a different ad account.')
            results.append(row)
        remote, adset, creative, ad = results
        if (str(adset.get('campaign_id')) != d.remote_campaign_id or str(ad.get('campaign_id')) != d.remote_campaign_id
                or str(ad.get('adset_id')) != d.remote_adset_id or str(ad.get('creative', {}).get('id')) != d.remote_creative_id):
            raise MetaError('Meta objects do not belong to the same campaign, ad set and creative.')
        if any(r.get('status') in {'DELETED', 'ARCHIVED'} for r in [remote, adset, ad]):
            raise MetaError('A Meta campaign, ad set or ad was deleted or archived.')
        plan = json.loads(d.plan_json)
        enforce_limits(plan)
        if str(adset.get('lifetime_budget')) != str(plan['weekly_budget_inr'] * 100) or str(adset.get('daily_budget', 0)) != '0':
            raise MetaError('Remote lifetime budget differs from the approved plan.')
        if plan['weekly_budget_inr'] > plan['daily_budget_inr'] and str(adset.get('daily_spend_cap')) != str(plan['daily_budget_inr'] * 100):
            raise MetaError('Meta daily hard cap differs from the approved plan; activation blocked.')
        from datetime import date, time, timedelta
        from zoneinfo import ZoneInfo
        expected = datetime.combine(date.fromisoformat(plan['end_date']) + timedelta(days=1), time.min, ZoneInfo(plan['timezone']))
        if datetime.fromisoformat(adset.get('end_time', '')) != expected:
            raise MetaError('Remote end time differs from the approved schedule.')
        state.remote_campaign_status = remote.get('effective_status', remote.get('status'))
        state.remote_ad_status = ad.get('effective_status', ad.get('status'))
        if state.remote_ad_status == 'PENDING_BILLING_INFO':
            state.payment_status = 'PAYMENT_PENDING'
        state.verified = True
        state.last_sync = datetime.now(timezone.utc)
        state.last_error = None
        state.creation_status = 'META_OBJECTS_CREATED'
        if state.payment_status == 'NOT_REQUESTED':
            state.payment_status = 'AWAITING_PAYMENT'
        db.commit()
        return state
    except (MetaError, ValueError, TypeError) as error:
        state.verified = False
        state.creation_status = 'META_SYNC_ERROR'
        state.connection_ok = False
        state.last_error = str(error) if isinstance(error, MetaError) else 'Meta returned invalid object data.'
        db.commit()
        raise MetaError(state.last_error) from None
