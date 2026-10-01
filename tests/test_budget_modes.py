import json
import pytest
from test_live_integration import local, graph, make_ready
from app import database
from app.models.campaign import Campaign
from app.models.approval import Approval

def policy(**changes):
    return {'budget_mode':'DYNAMIC','daily_budget_min_inr':150,'daily_budget_max_inr':200,
            'daily_budget_inr':200,'weekly_budget_limit_inr':1050, **changes}

def test_draft_mode_saved_and_enforced_on_meta(local, graph):
    client, settings = local
    identifier, plan, approval = make_ready(client, amount=0)
    with database.SessionLocal() as db:
        db.get(Approval,approval).status = 'PENDING'
        db.get(Campaign,identifier).status = 'PENDING_APPROVAL'
        db.commit()
    assert client.post(f'/approvals/{approval}/decision',json={'message':'REJECT'}).status_code == 200
    response = client.put(f'/campaigns/{identifier}/budget',json=policy())
    assert response.status_code == 200
    assert response.json()['budget_mode'] == 'DYNAMIC'
    assert response.json()['daily_budget_min_inr'] == 150
    snapshot = client.get('/integrations/campaigns').json()[0]['plan']
    assert snapshot['budget_mode'] == 'DYNAMIC'
    assert snapshot['daily_budget_inr'] == 200 and snapshot['weekly_budget_inr'] == 1050
    approval = client.post('/approvals/request',json={'campaign_id':identifier,'product_code':'CAT-001'}).json()['approval_id']
    assert client.post(f'/approvals/{approval}/decision',json={'message':'APPROVE CAT-001'}).status_code == 200
    assert client.put(f'/campaigns/{identifier}/budget',json=policy()).status_code == 409
    settings.meta_paused_preparation_enabled = True
    assert client.post(f'/integrations/campaigns/{identifier}/prepare').status_code == 200
    assert graph.posts[1][1]['daily_spend_cap'] == '20000'
    assert graph.posts[1][1]['lifetime_budget'] == '105000'

@pytest.mark.parametrize('changes',[{'daily_budget_max_inr':201,'daily_budget_inr':201},
    {'daily_budget_min_inr':200,'daily_budget_max_inr':150,'daily_budget_inr':150},
    {'weekly_budget_limit_inr':1051},{'daily_budget_min_inr':149},
    {'daily_budget_inr':175},{'budget_mode':'FIXED','daily_budget_inr':200}])
def test_invalid_or_unapproved_budget_range_rejected(local, changes):
    client,_ = local
    assert client.post('/campaigns',json={'name':'Dynamic draft',**policy(**changes)}).status_code == 422

def test_dynamic_requires_explicit_mode_and_range(local):
    client,_ = local
    assert client.post('/campaigns',json={'name':'Fixed draft','daily_budget_inr':200,'weekly_budget_limit_inr':1050}).status_code == 422
    result = client.post('/campaigns',json={'name':'Dynamic draft',**policy()})
    assert result.status_code == 201
    assert result.json()['weekly_budget_limit_inr'] == 1050
