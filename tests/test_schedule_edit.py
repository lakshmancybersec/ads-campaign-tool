from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytest
from test_live_integration import local, graph, make_ready
from app.services.meta_client import MetaClient, MetaError

@pytest.mark.parametrize('scenario', ['success', 'active', 'rejected', 'timeout', 'mismatch'])
def test_schedule_update(local, graph, monkeypatch, scenario):
    client, settings = local
    settings.meta_paused_preparation_enabled = True
    identifier, _, _ = make_ready(client, amount=0, total=150)
    assert client.post(f'/integrations/campaigns/{identifier}/prepare').status_code == 200
    original = MetaClient.request
    writes = []
    async def request(self, method, path, params=None):
        if method == 'POST' and path == '200':
            writes.append(params)
            if scenario == 'rejected':
                raise MetaError('Budget too small for this schedule', definitive=True)
            if scenario == 'timeout':
                raise MetaError('Connection interrupted')
            graph.end = params['end_time']
            return {'success': True}
        result = await original(self, method, path, params)
        if path == '200' and scenario == 'active':
            result['status'] = 'ACTIVE'
        if path == '200' and writes:
            result['start_time'] = writes[0]['start_time'] if scenario != 'mismatch' else 'invalid'
        return result
    monkeypatch.setattr(MetaClient, 'request', request)
    day = (datetime.now(ZoneInfo('Asia/Kolkata')) + timedelta(days=1)).date().isoformat()
    response = client.put(f'/integrations/campaigns/{identifier}/schedule', json={'start_date':day,'end_date':day})
    view = client.get('/integrations/campaigns').json()[0]
    if scenario == 'success':
        assert response.status_code == 200, response.text
        assert view['plan']['start_date'] == day
        assert view['verified']
        assert view['owner_status'] == 'AWAITING_OWNER_APPROVAL'
    else:
        assert response.status_code == 409
        if scenario in {'timeout','mismatch'}:
            assert view['operation'] == 'update:schedule'
            assert not view['verified']
        if scenario == 'rejected':
            assert view['operation'] is None
    assert view['plan']['weekly_budget_inr'] == 150
    assert len(graph.posts) == 4
    assert len(writes) == (0 if scenario == 'active' else 1)
    if writes:
        assert set(writes[0]) == {'start_time','end_time'}
