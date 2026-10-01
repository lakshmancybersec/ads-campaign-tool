from test_live_integration import local, graph, make_ready
from app.services import email_notifications


def test_email_request_deduplicates_and_does_not_confirm_payment(local, monkeypatch, graph):
    client, settings = local
    for key, value in dict(smtp_host='smtp.gmail.com', smtp_port=587, smtp_username='sender@example.com',
                           smtp_password='test-secret', owner_email='owner@example.com').items():
        monkeypatch.setattr(settings, key, value)
    settings.owner_whatsapp_number = None
    campaign, _, _ = make_ready(client, amount=0)
    settings.meta_paused_preparation_enabled = True
    assert client.post(f'/integrations/campaigns/{campaign}/prepare').status_code == 200
    sent = []
    monkeypatch.setattr(email_notifications, 'send_payment_email', lambda message: sent.append(message))
    for _ in range(2):
        response = client.post(f'/payments/{campaign}/email-request')
        assert response.status_code == 200
        assert response.json()['status'] == 'ACCEPTED_BY_SMTP'
    assert len(sent) == 1
    assert 'INR 1050' in sent[0]
    assert client.get('/payments').json() == []
    assert client.delete(f'/campaigns/{campaign}').status_code == 409
    client.headers.clear()
    assert client.post(f'/payments/{campaign}/email-request').status_code == 401


def test_missing_password_blocks_email(local, monkeypatch):
    client, settings = local
    monkeypatch.setattr(settings, 'smtp_password', None)
    campaign, _, _ = make_ready(client, amount=0)
    assert client.post(f'/payments/{campaign}/email-request').status_code == 409
