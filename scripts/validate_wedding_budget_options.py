"""Meta validate_only probes: no object creation, approval, payment or activation."""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding='utf-8')
from app.database import SessionLocal
from app.models.deployment import CampaignDeployment
from app.services.meta_client import MetaClient, MetaError

async def main():
    client = MetaClient()
    assert client.account == 'act_249780244315816'
    with SessionLocal() as db:
        d = db.get(CampaignDeployment, '79b0f1e1-b75b-4dbb-9ff6-5e0ec46c4d29')
        plan = json.loads(d.plan_json)
        assert d.remote_campaign_id == '120254199040930204'
        assert not any([d.remote_adset_id,d.remote_creative_id,d.remote_ad_id])
        campaign = await client.request('GET',d.remote_campaign_id,{'fields':'id,account_id,status,objective'})
        assert campaign['account_id'] == '249780244315816' and campaign['status'] == 'PAUSED'
        zone = ZoneInfo(plan['timezone'])
        start = max(datetime.combine(date.fromisoformat(plan['start_date']),time.min,zone),datetime.now(timezone.utc)+timedelta(minutes=5))
        end = datetime.combine(date.fromisoformat(plan['end_date'])+timedelta(days=1),time.min,zone)
        geo = {'regions':[], 'cities':[]}
        for location in plan['locations']:
            geo['regions' if location['type']=='region' else 'cities'].append({'key':location['key']})
        base = {'name':'Wedding Collection audience','campaign_id':d.remote_campaign_id,
                'billing_event':'IMPRESSIONS','optimization_goal':'LINK_CLICKS',
                'bid_strategy':'LOWEST_COST_WITHOUT_CAP','destination_type':'WEBSITE',
                'targeting':{'age_min':plan['age_min'],'age_max':plan['age_max'],
                             'targeting_automation':{'advantage_audience':0},
                             'geo_locations':{k:v for k,v in geo.items() if v},'publisher_platforms':['facebook']},
                'status':'PAUSED','start_time':start.isoformat(),'end_time':end.isoformat(),
                'execution_options':['validate_only'],'locale':'en_US'}
        cases = [('Current schedule, INR 150 total', {'lifetime_budget':15000}),
                 ('Current schedule, INR 158 total, INR 150 daily cap', {'lifetime_budget':15800,'daily_spend_cap':15000}),
                 ('Current schedule, INR 158 total (fits proposed INR 158/day cap)', {'lifetime_budget':15800}),
                 ('Shorter: 24 hours, INR 150 total', {'lifetime_budget':15000,'end_time':(start+timedelta(hours=24)).isoformat()}),
                 ('Shorter: end 1 October at midnight, INR 150 total', {'lifetime_budget':15000,'end_time':datetime(2026,10,2,tzinfo=zone).isoformat()})]
        report = {'checked_at':datetime.now(timezone.utc).isoformat(), 'campaign':campaign,
                  'base_parameters':base,'results':[]}
        for label, changes in cases:
            params = {**base,**changes}
            try:
                # Keep the non-mutating flag explicit at the call site; no case
                # is permitted to override it.
                params['execution_options'] = ['validate_only']
                assert params['execution_options'] == ['validate_only']
                result = await client.request('POST',client.account+'/adsets',
                                              {**params, 'execution_options':['validate_only']})
                outcome = {'success':result.get('success') is True,'returned_id':bool(result.get('id'))}
                assert not outcome['returned_id'], 'Unexpected ID from validation; stop further probes'
            except MetaError as error:
                outcome = {'success':False,'error':str(error)}
            report['results'].append({'case':label,'changes':changes,**outcome})
            print(label, outcome, flush=True)
        target = Path('local-backups/wedding-budget-validation-explicit-audience.json')
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
        print('Evidence saved:',target)

if __name__ == '__main__':
    asyncio.run(main())
