import json
from test_live_integration import local, make_ready
from app import database
from app.models.campaign import Campaign
from app.models.deployment import CampaignDeployment
from app.models.catalog import CatalogProduct
from sqlalchemy import select


def test_reuse_ended_campaign_creates_fresh_owner_budget_draft(local):
    client, _ = local
    source, plan, _ = make_ready(client)
    with database.SessionLocal() as db:
        db.get(Campaign, source).status = 'ENDED'
        db.get(CampaignDeployment, source).remote_campaign_id = '123'
        db.commit()
    assert client.get('/campaigns/reusable').json()[0]['previously_run'] is True
    response = client.post(f'/campaigns/{source}/reuse', json={
        'name': 'Second run', 'daily_budget_inr': 75, 'weekly_budget_limit_inr': 225,
        'start_date': plan['start_date'], 'end_date': plan['end_date']})
    assert response.status_code == 201
    new = response.json()
    assert new['id'] != source and new['status'] == 'DRAFT'
    with database.SessionLocal() as db:
        d = db.get(CampaignDeployment, new['id'])
        assert not d.approval_id and not d.remote_campaign_id and not d.automation_enabled
        copy = json.loads(d.plan_json)
        assert copy['daily_budget_inr'] == 75 and copy['weekly_budget_inr'] == 225
        assert copy['locations'] == plan['locations']
        assert db.get(Campaign, source).status == 'ENDED'
    assert len(client.get('/payments').json()) == 1
    assert len(client.get('/approvals').json()) == 1


def test_reuse_validation_and_unavailable_product_leave_no_draft(local):
    client, _ = local
    source, plan, _ = make_ready(client)
    payload = {'name': 'Second run', 'daily_budget_inr': 75, 'weekly_budget_limit_inr': 225,
        'start_date': plan['start_date'], 'end_date': plan['end_date']}
    assert client.post(f'/campaigns/{source}/reuse', json={'name': 'Missing budget'}).status_code == 422
    assert client.post(f'/campaigns/{source}/reuse', json={**payload, 'end_date':'2000-01-01'}).status_code == 422
    with database.SessionLocal() as db:
        db.scalar(select(CatalogProduct)).available = False
        db.commit()
    assert client.post(f'/campaigns/{source}/reuse', json=payload).status_code == 409
    assert len(client.get('/campaigns').json()) == 1
    client.headers.clear()
    assert client.post(f'/campaigns/{source}/reuse', json=payload).status_code == 401
