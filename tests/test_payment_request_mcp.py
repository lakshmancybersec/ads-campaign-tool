import asyncio
from urllib.parse import urlparse, parse_qs
import httpx
import pytest
from test_live_integration import local, graph, make_ready
from app.services.ads_mcp import probe_ads_mcp


def test_payment_request_manual_and_no_state_change(local, graph):
    client, settings = local
    campaign, _, _ = make_ready(client, amount=50)
    settings.meta_paused_preparation_enabled = True
    assert client.post(f'/integrations/campaigns/{campaign}/prepare').status_code == 200
    before = client.get('/campaigns').json()
    response = client.get(f'/payments/{campaign}/whatsapp-request')
    assert response.status_code == 200
    body = response.json()
    assert body['remaining_inr'] == 1000
    assert body['sent'] is False
    url = urlparse(body['url'])
    assert url.netloc == 'wa.me'
    assert url.path == '/' + settings.owner_whatsapp_number
    assert parse_qs(url.query)['text'] == [body['message']]
    assert 'INR 1050' in body['message']
    assert 'INR 1000' in body['message']
    assert client.get('/campaigns').json() == before
    assert len(client.get('/payments').json()) == 1
    client.headers.clear()
    assert client.get(f'/payments/{campaign}/whatsapp-request').status_code == 401


def test_paid_campaign_does_not_request_more_money(local):
    client, _ = local
    campaign, _, _ = make_ready(client)
    assert client.get(f'/payments/{campaign}/whatsapp-request').status_code == 409


def test_owner_number_required(local):
    client, settings = local
    campaign, _, _ = make_ready(client, amount=0)
    settings.owner_whatsapp_number = None
    assert client.get(f'/payments/{campaign}/whatsapp-request').status_code == 409


@pytest.mark.parametrize('status', [200, 401, 403, 302, 500])
def test_mcp_probe_never_sends_credentials_or_claims_connected(status):
    def respond(request):
        assert 'authorization' not in request.headers
        assert 'x-admin-key' not in request.headers
        assert b'tools/call' not in request.content
        assert b'initialize' in request.content
        return httpx.Response(status, json={})
    result = asyncio.run(probe_ads_mcp(httpx.MockTransport(respond)))
    assert result['connected'] is False
    assert result['tool_execution_enabled'] is False


def test_mcp_probe_network_failure():
    def fail(request):
        raise httpx.ConnectError('offline')
    result = asyncio.run(probe_ads_mcp(httpx.MockTransport(fail)))
    assert result['status'] == 'unreachable'
