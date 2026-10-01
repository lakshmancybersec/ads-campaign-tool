import pytest
from test_live_integration import local, graph, make_ready
from app.services.meta_client import MetaClient
from app.models.meta_workflow import MetaWorkflow
from app import database

def ready(local):
    client, settings = local
    settings.meta_paused_preparation_enabled = True
    identifier, _, _ = make_ready(client, amount=0, total=150)
    return client, identifier

@pytest.mark.parametrize('edge', ['campaigns','adsets','adcreatives','ads'])
@pytest.mark.parametrize('failure', ['reject_edge','fail_edge','missing_edge'])
def test_each_creation_failure_blocks_billing_and_preserves_retry_safety(local, graph, edge, failure):
    client, identifier = ready(local)
    setattr(graph, failure, edge)
    assert client.post(f'/integrations/campaigns/{identifier}/prepare').status_code == 409
    view = client.get('/integrations/campaigns').json()[0]
    assert view['creation_status'] == 'CREATION_FAILED'
    assert not view['prepared']
    assert client.get('/campaigns').json()[0]['status'] == 'FAILED'
    assert view['retry_safe'] == (failure == 'reject_edge')
    assert 'test-secret-token' not in str(view)
    before = len(graph.posts)
    assert client.post(f'/integrations/campaigns/{identifier}/billing').status_code == 409
    setattr(graph, failure, None)
    response = client.post(f'/integrations/campaigns/{identifier}/prepare')
    if failure == 'reject_edge':
        assert response.status_code == 200
        assert len([p for p in graph.posts if p[0] == 'campaigns']) == (2 if edge == 'campaigns' else 1)
    else:
        assert response.status_code == 409
        assert len(graph.posts) == before

def test_verified_objects_then_billing_then_owner_approval(local, graph):
    client, identifier = ready(local)
    assert client.post(f'/integrations/campaigns/{identifier}/billing').status_code == 409
    assert client.post(f'/integrations/campaigns/{identifier}/prepare').status_code == 200
    view = client.get('/integrations/campaigns').json()[0]
    assert view['payment_status'] == 'AWAITING_PAYMENT'
    assert view['last_meta_sync'] and view['ad_account_id'] == 'act_123'
    for field in ['remote_campaign_id','remote_adset_id','remote_creative_id','remote_ad_id']:
        assert view[field]
    body = {'billing_reviewed_in_meta': True}
    assert client.post(f'/integrations/campaigns/{identifier}/launch-approval', json=body).status_code == 409
    billing = client.post(f'/integrations/campaigns/{identifier}/billing').json()
    assert billing['url'].endswith('?act=123')
    assert billing['payment_status'] == 'PAYMENT_PENDING'
    assert client.post(f'/integrations/campaigns/{identifier}/launch-approval', json={'billing_reviewed_in_meta':False}).status_code == 409
    result = client.post(f'/integrations/campaigns/{identifier}/launch-approval', json=body).json()
    assert result['owner_status'] == 'APPROVED'
    assert result['payment_status'] == 'OWNER_REVIEWED_IN_META'
    assert result['payment_status'] != 'PAYMENT_CONFIRMED'
    assert len(graph.posts) == 4  # read-back, billing and approval perform no Meta writes

@pytest.mark.parametrize('wrong_id', ['100','200','300','400'])
def test_wrong_object_account_blocks_payment(local, graph, monkeypatch, wrong_id):
    client, identifier = ready(local)
    assert client.post(f'/integrations/campaigns/{identifier}/prepare').status_code == 200
    original = MetaClient.request
    async def changed(self, method, path, params=None):
        result = await original(self, method, path, params)
        if method == 'GET' and path == wrong_id:
            result['account_id'] = '999'
        return result
    monkeypatch.setattr(MetaClient, 'request', changed)
    assert client.post(f'/integrations/campaigns/{identifier}/billing').status_code == 409
    view = client.get('/integrations/campaigns').json()[0]
    assert not view['verified'] and view['creation_status'] == 'META_SYNC_ERROR'

def test_double_create_and_hard_limits(local):
    client, _ = local
    body = {'name':'One campaign','daily_budget_inr':150,'weekly_budget_limit_inr':1050}
    headers = {'Idempotency-Key':'stable-test-key'}
    first = client.post('/campaigns', json=body, headers=headers)
    second = client.post('/campaigns', json=body, headers=headers)
    assert first.json()['id'] == second.json()['id']
    assert len(client.get('/campaigns').json()) == 1
    assert client.post('/campaigns', json={**body,'name':'Different'}, headers=headers).status_code == 409
    for changes in [{'daily_budget_inr':151},{'weekly_budget_limit_inr':1051}]:
        assert client.post('/campaigns',json={**body,**changes}).status_code == 422

def test_configured_account_change_blocks_retry_and_billing(local, graph):
    client, identifier = ready(local)
    assert client.post(f'/integrations/campaigns/{identifier}/prepare').status_code == 200
    local[1].meta_ad_account_id = 'act_999'
    assert client.post(f'/integrations/campaigns/{identifier}/prepare').status_code == 409
    assert client.post(f'/integrations/campaigns/{identifier}/billing').status_code == 409
    assert len(graph.posts) == 4

def test_meta_sync_network_failure_revokes_verification(local, graph, monkeypatch):
    from app.services.meta_client import MetaError
    client, identifier = ready(local)
    assert client.post(f'/integrations/campaigns/{identifier}/prepare').status_code == 200
    async def unavailable(*args, **kwargs):
        raise MetaError('Meta connection failed.')
    monkeypatch.setattr(MetaClient,'request',unavailable)
    assert client.post(f'/integrations/campaigns/{identifier}/health').status_code == 409
    view = client.get('/integrations/campaigns').json()[0]
    assert view['creation_status'] == 'META_SYNC_ERROR'
    assert not view['verified'] and not view['connection_ok']
    assert view['last_meta_sync']  # retain last successful time, but mark stale
    assert client.post(f'/integrations/campaigns/{identifier}/billing').status_code == 409

def test_activation_requires_post_billing_owner_approval(local, graph):
    client, identifier = ready(local)
    local[1].meta_live_writes_enabled = True
    assert client.post(f'/integrations/campaigns/{identifier}/prepare').status_code == 200
    assert client.post(f'/integrations/campaigns/{identifier}/activate').status_code == 409
    assert len(graph.posts) == 4

def test_database_initialization_is_repeatable(local):
    from sqlalchemy import inspect
    database.init_db()
    database.init_db()
    names = inspect(database.engine).get_table_names()
    assert 'meta_workflows' in names and 'campaign_create_requests' in names

def test_legacy_notifications_cannot_bypass_creation_gate(local):
    client, identifier = ready(local)
    assert client.post(f'/payments/{identifier}/email-request').status_code == 409
    assert client.get(f'/payments/{identifier}/whatsapp-request').status_code == 409

def test_repeated_prepare_does_not_duplicate_remote_objects(local, graph):
    client, identifier = ready(local)
    for _ in range(3):
        assert client.post(f'/integrations/campaigns/{identifier}/prepare').status_code == 200
    assert len(graph.posts) == 4
