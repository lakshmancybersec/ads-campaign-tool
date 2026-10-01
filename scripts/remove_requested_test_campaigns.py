"""One-time cleanup of the specific local test campaigns requested by the owner."""
import json
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app.models
from app.database import Base, engine
from sqlalchemy import select, delete

ids = ['ef7383cf-207d-4f92-ab60-e806174550e6', '22eff85f-228b-4e20-b635-37514f56c5c8',
       'c9fd8f8a-397b-4832-91e2-dd98dc39605f', '9bc3e26b-166d-4cfd-b13b-9cd3954aeced']
tables = Base.metadata.tables
with engine.begin() as connection:
    campaigns = list(connection.execute(select(tables['campaigns']).where(tables['campaigns'].c.id.in_(ids))).mappings())
    deployments = list(connection.execute(select(tables['campaign_deployments']).where(tables['campaign_deployments'].c.campaign_id.in_(ids))).mappings())
    assert not any(c['meta_campaign_id'] for c in campaigns), 'Remote campaign requires separate review'
    assert not any(d[k] for d in deployments for k in ['remote_campaign_id','remote_adset_id','remote_ad_id','remote_creative_id','automation_enabled']), 'Remote activity requires separate review'
    approvals = list(connection.execute(select(tables['approvals'].c.id).where(tables['approvals'].c.campaign_id.in_(ids))).scalars())
    backup = {}
    predicates = {}
    for table in reversed(Base.metadata.sorted_tables):
        predicate = table.c.campaign_id.in_(ids) if 'campaign_id' in table.c else table.c.approval_id.in_(approvals) if 'approval_id' in table.c else table.c.id.in_(ids) if table.name == 'campaigns' else None
        if predicate is not None:
            predicates[table.name] = predicate
            backup[table.name] = [dict(r) for r in connection.execute(select(table).where(predicate)).mappings()]
    folder = Path('local-backups')
    folder.mkdir(exist_ok=True)
    target = folder / ('campaign-cleanup-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.json')
    target.write_text(json.dumps(backup, default=str), encoding='utf-8')
    for name, predicate in predicates.items():
        connection.execute(delete(tables[name]).where(predicate))
    print('Removed local campaigns:', len(campaigns), '; recovery copy:', target)
