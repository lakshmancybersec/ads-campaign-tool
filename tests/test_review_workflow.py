from test_live_integration import local, make_ready
from app import database
from app.models.approval import Approval
from app.models.campaign import Campaign


def test_review_card_identifies_existing_approval(local):
    client, _ = local
    identifier, _, approval_id = make_ready(client, amount=0)
    view = client.get('/integrations/campaigns').json()[0]
    assert view['campaign_id'] == identifier
    assert view['approval_id'] == approval_id
    assert view['plan']['product_name']
    assert view['plan']['image_url']


def test_multiple_locations_survive_save_and_approval(local):
    client, _ = local
    identifier, plan, approval_id = make_ready(client, amount=0)
    with database.SessionLocal() as db:
        db.get(Approval, approval_id).status = 'PENDING'
        db.get(Campaign, identifier).status = 'PENDING_APPROVAL'
        db.commit()
    assert client.post(f'/approvals/{approval_id}/decision', json={'message':'REJECT'}).status_code == 200
    plan['locations'] = [{'key':'1', 'name':'Chennai', 'type':'city'},
                         {'key':'2', 'name':'Bengaluru', 'type':'city'},
                         {'key':'3', 'name':'Tamil Nadu', 'type':'region'}]
    assert client.put(f'/integrations/campaigns/{identifier}/plan', json=plan).status_code == 200
    request = client.post('/approvals/request', json={'campaign_id':identifier, 'product_code':'CAT-001'})
    approval_id = request.json()['approval_id']
    assert client.post(f'/approvals/{approval_id}/decision', json={'message':'APPROVE CAT-001'}).status_code == 200
    assert client.get('/integrations/campaigns').json()[0]['plan']['locations'] == plan['locations']
    assert client.get('/payments').json() == []
