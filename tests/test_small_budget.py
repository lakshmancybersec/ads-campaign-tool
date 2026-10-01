import asyncio
from datetime import datetime
import pytest
from test_live_integration import local, graph, make_ready
from app import database
from app.models.campaign import Campaign
from app.services.deployment import change_delivery
from app.services.meta_client import MetaError

@pytest.mark.parametrize('tampered', [False, True])
def test_small_total_has_remote_lifetime_limit_and_activation_verifies_it(local, graph, tampered):
    client, settings = local
    identifier, plan, _ = make_ready(client, amount=0, total=150)
    settings.meta_live_writes_enabled = True
    assert client.post(f'/integrations/campaigns/{identifier}/prepare').status_code == 200
    assert 'spend_cap' not in graph.posts[0][1]
    assert graph.posts[1][1]['lifetime_budget'] == '15000'
    assert 'daily_budget' not in graph.posts[1][1]
    assert all(p.get('status', 'PAUSED') == 'PAUSED' for _, p in graph.posts)
    if tampered:
        graph.lifetime_budget = '30000'
    with database.SessionLocal() as db:
        from app.models.meta_workflow import MetaWorkflow
        db.get(MetaWorkflow, identifier).owner_status = 'APPROVED'
        db.commit()
        operation = change_delivery(db, db.get(Campaign, identifier), 'activate',
                                   now=datetime.fromisoformat(plan['start_date'] + 'T12:00:00+05:30'))
        if tampered:
            with pytest.raises(MetaError, match='budget differs'):
                asyncio.run(operation)
            assert len(graph.posts) == 4
        else:
            asyncio.run(operation)
            assert len(graph.posts) == 7
