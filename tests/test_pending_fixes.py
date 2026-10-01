from datetime import date
import pytest
from test_live_integration import local, make_ready
from app import database
from app.models.approval import Approval
from app.models.campaign import Campaign
from app.models.deployment import CampaignDeployment


def test_missing_plan_cannot_request_or_approve_but_can_reject(local):
    client, _ = local
    identifier, _, approval_id = make_ready(client, amount=0)
    with database.SessionLocal() as db:
        db.delete(db.get(CampaignDeployment, identifier))
        db.get(Approval, approval_id).status = 'PENDING'
        db.get(Campaign, identifier).status = 'PENDING_APPROVAL'
        db.commit()
    assert client.post(f'/approvals/{approval_id}/decision', json={'message': 'APPROVE CAT-001'}).status_code == 409
    assert client.post(f'/approvals/{approval_id}/decision', json={'message': 'REJECT'}).status_code == 200
    assert client.post('/approvals/request', json={'campaign_id': identifier, 'product_code': 'CAT-001'}).status_code == 409
    assert client.get('/campaigns').json()[0]['status'] == 'DRAFT'


@pytest.mark.parametrize('counts,expected', [([], None), ([None], None), ([0], 0), ([2], 2), ([2, None], None), ([2, 3], 5)])
def test_conversation_unknown_zero_and_partial_coverage(local, counts, expected):
    client, _ = local
    identifier, plan, _ = make_ready(client, amount=0)
    for count in counts:
        assert client.post('/analytics/snapshots', json={
            'campaign_id': identifier, 'snapshot_date': plan['start_date'],
            'spend_inr': 10, 'reach': 10, 'impressions': 20, 'clicks': 2,
            'conversations': count}).status_code == 201
    report = client.get('/analytics/weekly-report', params={'end_date': plan['start_date']}).json()
    assert report['metrics']['conversations'] == expected
    assert report['conversation_data_complete'] == (expected is not None)
    if expected is None:
        assert report['metrics']['cost_per_conversation_inr'] is None
        assert any('unavailable or incomplete' in text for text in report['recommendations']['cons'])
        assert not any('volume is positive' in text for text in report['recommendations']['pros'])
