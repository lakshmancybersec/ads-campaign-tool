import asyncio
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import database
from app.config import get_settings
from app.main import create_app
from app.models.campaign import Campaign
from app.models.deployment import CampaignDeployment
from app.models.lead import Lead
from app.models.performance import PerformanceSnapshot
from app.services.deployment import change_delivery
from app.services.meta_client import MetaClient, MetaError


@pytest.fixture
def local(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine, autoflush=False))
    settings = get_settings()
    values = dict(api_admin_key="a" * 40, meta_access_token="test-secret-token", meta_app_secret="test-secret",
                  meta_ad_account_id="act_123", facebook_page_id="456", customer_whatsapp_number="919999999999",
                  instagram_actor_id=None, meta_catalog_id="789", meta_live_writes_enabled=False, meta_paused_preparation_enabled=False, smtp_password=None,
                  scheduler_enabled=True, whatsapp_app_secret="webhook-secret", whatsapp_phone_number_id="555",
                  owner_whatsapp_number="918888888888", whatsapp_notifications_enabled=False,
                  whatsapp_access_token=None, whatsapp_approval_template=None, public_dashboard_url=None)
    for key, value in values.items():
        monkeypatch.setattr(settings, key, value)
    with TestClient(create_app()) as client:
        client.headers.update({"X-Admin-Key": settings.api_admin_key})
        yield client, settings
    engine.dispose()


def test_budget_must_be_entered_by_owner(local):
    client, settings = local
    assert client.post("/campaigns", json={"name": "No budget"}).status_code == 422
    for amount in (0, -1, 1.5):
        assert client.post("/campaigns", json={"name": "Invalid budget", "daily_budget_inr": amount,
            "weekly_budget_limit_inr": 700}).status_code == 422
    response = client.post("/campaigns", json={"name": "Owner budget", "daily_budget_inr": 83,
        "weekly_budget_limit_inr": 499})
    assert response.status_code == 201
    assert response.json()["daily_budget_inr"] == 83
    assert response.json()["weekly_budget_limit_inr"] == 499
    assert response.json()["status"] == "DRAFT"


def make_ready(client, amount=1050, total=1050):
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    product = client.post("/catalog", json={"product_code": "CAT-001", "name": "Dhoti", "category": "Wedding",
        "price_inr": 1000, "image_url": "https://example.com/photo.jpg"})
    assert product.status_code == 201
    campaign = client.post("/campaigns", json={"name": "Approved campaign", "daily_budget_inr": 150, "weekly_budget_limit_inr": total}).json()
    plan = {"product_code": "CAT-001", "caption": "Wedding collection", "start_date": today.isoformat(),
        "end_date": (today + timedelta(days=6)).isoformat(), "locations": [{"key": "99", "name": "Tamil Nadu", "type": "region"}],
        "windows": [{"start": "00:00", "end": "23:59"}]}
    response = client.put(f"/integrations/campaigns/{campaign['id']}/plan", json=plan)
    assert response.status_code == 200, response.text
    approval = client.post("/approvals/request", json={"campaign_id": campaign["id"], "product_code": "CAT-001"}).json()
    assert client.post(f"/approvals/{approval['approval_id']}/decision", json={"message": "APPROVE CAT-001"}).status_code == 200
    if amount:
        response = client.post("/payments/confirm", json={"campaign_id": campaign["id"], "amount_inr": amount,
            "payment_reference": "REFERENCE-001"})
        assert response.status_code == 201
    return campaign["id"], plan, approval["approval_id"]


class GraphStub:
    def __init__(self):
        self.posts = []
        self.fail_edge = None
        self.reject_edge = None
        self.missing_edge = None
        self.spend = "10.00"
        self.daily_budget = "15000"
        self.lifetime_budget = "0"
        self.daily_spend_cap = "0"
        self.end = None
        self.rows = []

    def __call__(self, request):
        assert request.headers["Authorization"] == "Bearer test-secret-token"
        assert "access_token" not in request.url.params
        edge = request.url.path.split("/")[-1]
        if request.method == "POST":
            data = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
            self.posts.append((edge, data))
            if edge == self.fail_edge:
                raise httpx.ReadTimeout("simulated", request=request)
            if edge == self.reject_edge:
                return httpx.Response(400, json={'error':{'code':100, 'error_subcode':4834011, 'message':'test-secret-token'}})
            if edge == self.missing_edge:
                return httpx.Response(200, json={})
            ids = {"campaigns": "100", "adsets": "200", "adcreatives": "300", "ads": "400"}
            if edge == "adsets":
                self.end = data["end_time"]
                self.lifetime_budget = data.get("lifetime_budget", "0")
                self.daily_budget = data.get("daily_budget", "0")
                self.daily_spend_cap = data.get("daily_spend_cap", "0")
            return httpx.Response(200, json={"id": ids[edge]} if edge in ids else {"success": True})
        if edge == "act_123":
            return httpx.Response(200, json={"id": "act_123", "name": "Test account", "account_status": 1, "currency": "INR"})
        if edge == "100":
            return httpx.Response(200, json={"id":"100", "account_id": "123", "status":"PAUSED", "spend_cap": "0"})
        if edge == "200":
            return httpx.Response(200, json={"id":"200", "account_id":"123", "status":"PAUSED", "campaign_id": "100", "daily_budget": self.daily_budget, "lifetime_budget": self.lifetime_budget, "daily_spend_cap":self.daily_spend_cap, "end_time": self.end})
        if edge == "300":
            return httpx.Response(200, json={"id":"300", "account_id":"123"})
        if edge == "400":
            return httpx.Response(200, json={"id":"400", "account_id":"123", "campaign_id":"100", "adset_id":"200", "creative":{"id":"300"}, "status":"PAUSED"})
        if edge == "insights":
            return httpx.Response(200, json={"data": self.rows if request.url.params.get("time_increment") else [{"spend": self.spend}]})
        if edge == "products":
            return httpx.Response(200, json={"data": [{"id": "17", "name": "Imported dhoti", "currency": "INR",
                "price": "125000", "image_url": "https://example.com/image.jpg", "availability": "in stock"}]})
        raise AssertionError(str(request.url))


@pytest.fixture
def graph(monkeypatch):
    stub = GraphStub()
    original = MetaClient.__init__
    monkeypatch.setattr(MetaClient, "__init__", lambda self: original(self, transport=httpx.MockTransport(stub)))
    return stub


def test_prepare_without_payment_cannot_activate_with_preparation_only(local, graph):
    client, settings = local
    identifier, _, _ = make_ready(client, amount=0)
    assert client.get('/campaigns').json()[0]['status'] == 'READY'
    settings.meta_paused_preparation_enabled = True
    assert client.post(f'/integrations/campaigns/{identifier}/prepare').status_code == 200
    assert len(graph.posts) == 4
    assert client.post(f'/integrations/campaigns/{identifier}/activate').status_code == 409
    assert len(graph.posts) == 4
    assert client.get('/payments').json() == []


def test_payment_is_optional_and_plan_is_frozen(local):
    client, settings = local
    campaign_id, plan, approval_id = make_ready(client, amount=1)
    assert client.get("/campaigns").json()[0]["status"] == "READY"
    assert client.put(f"/integrations/campaigns/{campaign_id}/plan", json=plan).status_code == 409
    response = client.post("/payments/confirm", json={"campaign_id": campaign_id, "amount_inr": 1049,
        "payment_reference": "REFERENCE-002"})
    assert response.json()["campaign_status"] == "READY"
    assert client.post(f"/integrations/campaigns/{campaign_id}/prepare").status_code == 409


def test_prepare_paused_idempotent_and_activate_parent_last(local, graph):
    client, settings = local
    campaign_id, plan, _ = make_ready(client)
    settings.meta_live_writes_enabled = True
    response = client.post(f"/integrations/campaigns/{campaign_id}/prepare")
    assert response.status_code == 200, response.text
    assert response.json()["prepared"] is True
    assert len(graph.posts) == 4
    assert 'spend_cap' not in graph.posts[0][1]
    assert graph.posts[0][1]['is_adset_budget_sharing_enabled'] == 'false'
    assert graph.posts[1][1]["lifetime_budget"] == "105000"
    assert graph.posts[1][1]["daily_spend_cap"] == "15000"
    assert all(data.get("status", "PAUSED") == "PAUSED" for _, data in graph.posts)
    assert client.post(f"/integrations/campaigns/{campaign_id}/prepare").status_code == 200
    assert len(graph.posts) == 4
    with database.SessionLocal() as db:
        from app.models.meta_workflow import MetaWorkflow
        db.get(MetaWorkflow, campaign_id).owner_status = 'APPROVED'
        db.commit()
        campaign = db.get(Campaign, campaign_id)
        moment = datetime.fromisoformat(plan["start_date"] + "T12:00:00+05:30")
        asyncio.run(change_delivery(db, campaign, "activate", now=moment))
        assert campaign.status == "ACTIVE"
        assert db.get(CampaignDeployment, campaign_id).automation_enabled is True
    assert [edge for edge, _ in graph.posts[-3:]] == ["200", "400", "100"]
    assert client.post(f"/integrations/campaigns/{campaign_id}/pause").status_code == 200
    assert client.get("/integrations/campaigns").json()[0]["automation_enabled"] is False


def test_uncertain_creation_does_not_retry(local, graph):
    client, settings = local
    campaign_id, _, _ = make_ready(client)
    settings.meta_live_writes_enabled = True
    graph.fail_edge = "adsets"
    assert client.post(f"/integrations/campaigns/{campaign_id}/prepare").status_code == 409
    assert client.post(f"/integrations/campaigns/{campaign_id}/prepare").status_code == 409
    assert [edge for edge, _ in graph.posts] == ["campaigns", "adsets"]
    assert client.get("/integrations/campaigns").json()[0]["operation"] == "create:adsets"


@pytest.mark.parametrize("blocked", ["spend", "budget", "expired", "outside_hours"])
def test_activation_guards_make_no_status_writes(local, graph, blocked):
    client, settings = local
    campaign_id, plan, _ = make_ready(client)
    settings.meta_live_writes_enabled = True
    assert client.post(f"/integrations/campaigns/{campaign_id}/prepare").status_code == 200
    moment = datetime.fromisoformat(plan["start_date"] + "T12:00:00+05:30")
    if blocked == "spend": graph.spend = "1050.00"
    if blocked == "budget": graph.daily_budget = "20000"
    if blocked == "expired": moment += timedelta(days=8)
    if blocked == "outside_hours": moment = moment.replace(hour=23, minute=59, second=30)
    with database.SessionLocal() as db:
        with pytest.raises(MetaError):
            asyncio.run(change_delivery(db, db.get(Campaign, campaign_id), "activate", now=moment))
    assert len(graph.posts) == 4


def test_catalog_import_is_repeatable(local, graph):
    client, _ = local
    for _ in range(2):
        response = client.post("/integrations/meta/catalog/import")
        assert response.status_code == 200
        assert response.json()["imported"] == 1
    products = client.get("/catalog").json()
    assert len(products) == 1
    assert products[0]["price_inr"] == 1250
    assert products[0]["owner_approved"] is False


def test_collection_updates_without_duplicating_days(local, graph):
    client, settings = local
    campaign_id, plan, _ = make_ready(client)
    settings.meta_live_writes_enabled = True
    assert client.post(f"/integrations/campaigns/{campaign_id}/prepare").status_code == 200
    graph.rows = [{"date_start": plan["start_date"], "spend": "40", "reach": "100", "impressions": "200", "clicks": "10"}]
    for _ in range(2):
        assert client.post("/integrations/meta/collect").json()["campaigns"][0]["days_updated"] == 1
    with database.SessionLocal() as db:
        rows = db.scalars(select(PerformanceSnapshot)).all()
        assert len(rows) == 1
        assert rows[0].spend_inr == 40
        assert rows[0].cpc_inr == 4


def test_scheduler_ends_campaign_at_budget(local, graph):
    client, settings = local
    campaign_id, _, _ = make_ready(client)
    settings.meta_live_writes_enabled = True
    assert client.post(f"/integrations/campaigns/{campaign_id}/prepare").status_code == 200
    with database.SessionLocal() as db:
        db.get(Campaign, campaign_id).status = "ACTIVE"
        db.get(CampaignDeployment, campaign_id).automation_enabled = True
        db.commit()
    graph.spend = "1050"
    response = client.post("/integrations/meta/scheduler")
    assert response.json()["campaigns"][0]["status"] == "ENDED"
    assert graph.posts[-1] == ("100", {"status": "PAUSED", "appsecret_proof": graph.posts[-1][1]["appsecret_proof"]})


def test_missing_admin_key_fails_closed(local):
    client, settings = local
    settings.api_admin_key = None
    assert client.get("/approvals").status_code == 503


def test_whatsapp_owner_decision_requires_signature_and_is_idempotent(local):
    client, settings = local
    campaign_id, _, approval_id = make_ready(client)
    # Reuse helper-created campaign by reverting approval solely in this isolated fixture.
    from app.models.approval import Approval
    with database.SessionLocal() as db:
        db.get(Approval, approval_id).status = "PENDING"
        db.get(Campaign, campaign_id).status = "PENDING_APPROVAL"
        db.commit()
    payload = {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "555"}, "messages": [
        {"id": "message-1", "from": settings.owner_whatsapp_number, "type": "text",
         "text": {"body": f"APPROVE {approval_id}"}}]}}]}]}
    raw = json.dumps(payload).encode()
    assert client.post("/webhooks/whatsapp", content=raw).status_code == 401
    signature = "sha256=" + hmac.new(settings.whatsapp_app_secret.encode(), raw, hashlib.sha256).hexdigest()
    response = client.post("/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": signature})
    assert response.json() == {"processed": 1, "duplicates": 0}
    assert client.post("/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": signature}).json()["duplicates"] == 1
    assert client.get("/campaigns").json()[0]["status"] == "READY"
    with database.SessionLocal() as db:
        assert db.scalars(select(Lead)).all() == []
    settings.whatsapp_app_secret = None
    assert client.post("/webhooks/whatsapp", content=raw).status_code == 503


def test_graph_errors_do_not_expose_token(local):
    client = MetaClient()
    client.transport = httpx.MockTransport(lambda request: httpx.Response(400, json={"error": {
        "code": 190, "message": "do not expose test-secret-token"}}))
    with pytest.raises(MetaError) as error:
        asyncio.run(client.validate_account())
    assert "test-secret-token" not in str(error.value)
    assert "190" in str(error.value)


def test_whatsapp_template_sends_once(local, monkeypatch):
    from app.models.approval import Approval
    from app.services.whatsapp import WhatsAppService
    client, settings = local
    campaign_id, _, approval_id = make_ready(client)
    with database.SessionLocal() as db:
        db.get(Approval, approval_id).status = "PENDING"
        db.get(Campaign, campaign_id).status = "PENDING_APPROVAL"
        db.commit()
    settings.whatsapp_notifications_enabled = True
    settings.whatsapp_access_token = "whatsapp-test-token"
    settings.whatsapp_approval_template = "campaign_review"
    settings.public_dashboard_url = "https://dashboard.example.com"
    sent = []
    def respond(request):
        payload = json.loads(request.content)
        sent.append(payload)
        assert request.headers["Authorization"] == "Bearer whatsapp-test-token"
        assert payload["to"] == settings.owner_whatsapp_number
        assert len(payload["template"]["components"][0]["parameters"]) == 4
        return httpx.Response(200, json={"messages": [{"id": "wamid.test"}]})
    original = WhatsAppService.__init__
    monkeypatch.setattr(WhatsAppService, "__init__", lambda self: original(self, transport=httpx.MockTransport(respond)))
    for _ in range(2):
        response = client.post(f"/approvals/{approval_id}/notify")
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "SENT"
    assert len(sent) == 1


def test_customer_cannot_approve_and_malformed_webhook_is_rejected(local):
    client, settings = local
    campaign_id, _, approval_id = make_ready(client, amount=0)
    payload = {"entry": [{"changes": [{"value": {"metadata": {"phone_number_id": "555"}, "messages": [
        {"id": "customer-message", "from": "917777777777", "type": "text", "text": {"body": f"APPROVE {approval_id}"}}]}}]}]}
    def send(value):
        raw = json.dumps(value).encode()
        sig = "sha256=" + hmac.new(settings.whatsapp_app_secret.encode(), raw, hashlib.sha256).hexdigest()
        return client.post("/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig})
    assert send(payload).status_code == 200
    assert client.get("/campaigns").json()[0]["status"] == "READY"
    assert send({"entry": [None]}).status_code == 422


def test_ended_campaign_cannot_be_reopened(local, graph):
    client, settings = local
    campaign_id, _, _ = make_ready(client)
    settings.meta_live_writes_enabled = True
    assert client.post(f"/integrations/campaigns/{campaign_id}/prepare").status_code == 200
    assert client.post(f"/integrations/campaigns/{campaign_id}/end").status_code == 200
    assert client.post(f"/integrations/campaigns/{campaign_id}/pause").status_code == 409
    assert client.post(f"/integrations/campaigns/{campaign_id}/activate").status_code == 409
