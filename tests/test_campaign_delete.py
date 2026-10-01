import pytest
from sqlalchemy import select
from test_live_integration import local, make_ready
from app import database
from app.models.approval import Approval
from app.models.campaign import Campaign
from app.models.deployment import CampaignDeployment


def test_delete_pending_removes_plan_and_approvals_keeps_product(local):
    client, _ = local
    identifier, _, _ = make_ready(client, amount=0)
    with database.SessionLocal() as db:
        db.get(Campaign, identifier).status = 'PENDING_APPROVAL'
        db.commit()
    assert client.delete('/campaigns/' + identifier).status_code == 200
    assert client.get('/campaigns').json() == []
    assert len(client.get('/catalog').json()) == 1
    assert client.get('/approvals').json() == []
    assert client.get('/integrations/campaigns').json() == []
    assert client.delete('/campaigns/' + identifier).status_code == 404


def test_delete_requires_auth(local):
    client, _ = local
    identifier, _, _ = make_ready(client, amount=0)
    client.headers.clear()
    assert client.delete('/campaigns/' + identifier).status_code == 401


@pytest.mark.parametrize('status', ['READY', 'FAILED'])
def test_delete_local_unlaunched_campaign(local, status):
    client, _ = local
    identifier, _, _ = make_ready(client, amount=0)
    with database.SessionLocal() as db:
        db.get(Campaign, identifier).status = status
        db.commit()
    assert client.delete('/campaigns/' + identifier).status_code == 200
    assert client.get('/integrations/campaigns').json() == []


def test_archive_preserves_payment_and_hides_campaign(local):
    client, _ = local
    identifier, _, _ = make_ready(client)
    with database.SessionLocal() as db:
        db.get(Campaign, identifier).status = 'PENDING_APPROVAL'
        db.commit()
    assert client.post('/campaigns/' + identifier + '/archive').status_code == 200
    assert client.get('/campaigns').json() == []
    assert client.get('/campaigns?include_archived=true').json()[0]['status'] == 'ARCHIVED'
    assert len(client.get('/payments').json()) == 1
    assert client.get('/dashboard/overview').json()['counts']['campaigns'] == 0


@pytest.mark.parametrize('guard', ['payment', 'remote', 'operation', 'active'])
def test_delete_protects_business_records_and_remote_operations(local, guard):
    client, _ = local
    identifier, _, _ = make_ready(client, amount=1050 if guard == 'payment' else 0)
    with database.SessionLocal() as db:
        campaign = db.get(Campaign, identifier)
        campaign.status = 'ACTIVE' if guard == 'active' else 'PENDING_APPROVAL'
        deployment = db.get(CampaignDeployment, identifier)
        if guard == 'remote': deployment.remote_campaign_id = '123'
        if guard == 'operation': deployment.operation = 'create:campaigns'
        db.commit()
    assert client.delete('/campaigns/' + identifier).status_code == 409
    assert len(client.get('/campaigns').json()) == 1
    assert len(client.get('/approvals').json()) == 1


def test_reopen_saved_campaign_invalidates_approval(local):
    client, _ = local
    identifier, _, _ = make_ready(client, amount=0)
    assert client.post('/campaigns/' + identifier + '/edit').status_code == 200
    assert client.get('/campaigns').json()[0]['status'] == 'DRAFT'
    assert all(a['status'] == 'REJECTED' for a in client.get('/approvals').json())
    with database.SessionLocal() as db:
        assert db.get(CampaignDeployment, identifier).approval_id is None


@pytest.mark.parametrize('field', ['remote_campaign_id', 'remote_adset_id', 'remote_creative_id', 'remote_ad_id', 'operation'])
def test_reopen_blocks_remote_objects_and_uncertain_writes(local, field):
    client, _ = local
    identifier, _, _ = make_ready(client, amount=0)
    with database.SessionLocal() as db:
        setattr(db.get(CampaignDeployment, identifier), field, '123')
        db.commit()
    assert client.post('/campaigns/' + identifier + '/edit').status_code == 409
