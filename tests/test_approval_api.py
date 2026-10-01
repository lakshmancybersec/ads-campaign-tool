from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.database as database
from app.config import get_settings
from app.main import app
from datetime import datetime
from zoneinfo import ZoneInfo


def test_campaign_requires_both_payment_and_approval_before_ready(monkeypatch):
    monkeypatch.setattr(get_settings(), "facebook_page_id", "123")
    monkeypatch.setattr(get_settings(), "customer_whatsapp_number", "919999999999")
    test_engine = create_engine(
        "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    original_engine, original_session = database.engine, database.SessionLocal
    database.engine = test_engine
    database.SessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    try:
        with TestClient(app) as client:
            headers = {"X-Admin-Key": get_settings().api_admin_key or ""}
            campaign = client.post("/campaigns", json={"name": "Wedding Dhoti Collection", "daily_budget_inr": 150, "weekly_budget_limit_inr": 1050}, headers=headers).json()
            product = client.post("/catalog", json={
                "product_code": "CAT-004", "name": "Wedding Dhoti", "category": "Wedding Dhoti Set",
                "image_url": "https://example.com/dhoti.jpg", "price_inr": 1500
            }, headers=headers).json()
            today = datetime.now(ZoneInfo(get_settings().timezone)).date().isoformat()
            plan_response = client.put(f"/integrations/campaigns/{campaign['id']}/plan", headers=headers, json={
                "product_code": product["product_code"], "caption": "Wedding collection",
                "start_date": today, "end_date": today,
                "locations": [{"key": "123", "name": "Test location", "type": "city"}],
                "windows": [{"start": "09:00", "end": "18:00"}]})
            assert plan_response.status_code == 200
            approval = client.post("/approvals/request", json={
                "campaign_id": campaign["id"], "product_code": product["product_code"]
            }, headers=headers).json()
            duplicate = client.post("/approvals/request", json={
                "campaign_id": campaign["id"], "product_code": product["product_code"]
            }, headers=headers)
            assert duplicate.status_code == 409
            assert client.get("/approvals", headers=headers).json()[0]["status"] == "PENDING"
            payment = client.post("/payments/confirm", json={
                "campaign_id": campaign["id"], "amount_inr": 1050, "payment_reference": "SAFE-REF-001"
            }, headers=headers).json()

            assert payment["campaign_status"] == "PENDING_APPROVAL"
            payments = client.get("/payments", headers=headers).json()
            assert payments[0]["payment_reference"] == "SAFE-REF-001"
            assert payments[0]["amount_inr"] == 1050

            decision = client.post(f"/approvals/{approval['approval_id']}/decision", json={
                "message": "APPROVE CAT-004"
            }, headers=headers)
            assert decision.status_code == 200
            assert decision.json()["campaign_status"] == "READY"
            assert client.get("/approvals", headers=headers).json()[0]["status"] == "APPROVED"
            assert client.get("/campaigns", headers=headers).json()[0]["status"] == "READY"
            assert client.post(f"/approvals/{approval['approval_id']}/decision", json={
                "message": "REJECT"
            }, headers=headers).status_code == 409
            assert client.get("/approvals", headers={"X-Admin-Key": "wrong-key"}).status_code == 401
            assert client.get("/payments", headers={"X-Admin-Key": "wrong-key"}).status_code == 401
    finally:
        database.engine = original_engine
        database.SessionLocal = original_session
