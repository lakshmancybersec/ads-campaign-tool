"""Local regression checks; isolated database, no provider writes."""
import asyncio
import re
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException

from test_live_integration import local, make_ready
from app.api.dependencies import require_admin_key
from app.services.meta_client import MetaClient


@pytest.mark.parametrize("path", ["/campaigns", "/catalog", "/setup/status", "/dashboard/overview",
    "/approvals", "/payments", "/integrations/campaigns", "/analytics/weekly-report"])
def test_private_reads_require_auth(local, path):
    client, settings = local
    client.headers.clear()
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"X-Admin-Key": "incorrect"}).status_code == 401
    assert client.get(path, headers={"X-Admin-Key": settings.api_admin_key}).status_code == 200


@pytest.mark.parametrize("path", ["/campaigns", "/catalog", "/approvals/request", "/payments/confirm",
    "/integrations/meta/catalog/import", "/integrations/meta/scheduler", "/analytics/snapshots"])
def test_writes_require_auth(local, path):
    client, _ = local
    client.headers.clear()
    assert client.post(path, json={}).status_code == 401


def test_non_ascii_wrong_key_is_rejected(local):
    with pytest.raises(HTTPException) as error:
        require_admin_key("wrong-\u20b9")
    assert error.value.status_code == 401


def test_smoke_static_assets_and_secret_files(local):
    client, _ = local
    assert client.get("/health").json()["status"] == "ok"
    html = client.get("/")
    assert html.status_code == 200
    assert "daily_budget_inr" in html.text
    for path in ["/static/dashboard.js", "/static/dashboard.css"]:
        assert client.get(path).status_code == 200
    for path in ["/.env", "/static/.env", "/static/%2e%2e/.env"]:
        assert client.get(path).status_code == 404
    ids = set(re.findall(r'id="([^"]+)"', html.text))
    js = Path("app/static/dashboard.js").read_text(encoding="utf-8")
    assert set(re.findall(r'el\("([^"]+)"\)', js)) <= ids


@pytest.mark.parametrize("price,expected", [("\u20b9\u00a02,770.00", 2770), ("125000", 1250), ("\u20b9 99.50", None)])
def test_import_price_formats(local, monkeypatch, price, expected):
    client, _ = local
    original = MetaClient.__init__
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"data": [{
        "id": "123", "name": "Test dhoti", "price": price, "currency": "INR",
        "image_url": "https://example.com/photo.jpg", "availability": "in stock"}]}))
    monkeypatch.setattr(MetaClient, "__init__", lambda self: original(self, transport=transport))
    response = client.post("/integrations/meta/catalog/import")
    assert response.status_code == 200
    assert response.json()["imported"] == (0 if expected is None else 1)
    products = client.get("/catalog").json()
    assert not products if expected is None else products[0]["price_inr"] == expected


def test_analytics_and_duplicate_payment(local):
    client, _ = local
    campaign, plan, _ = make_ready(client)
    payload = {"campaign_id": campaign, "amount_inr": 1050, "payment_reference": "REFERENCE-001"}
    assert client.post("/payments/confirm", json=payload).status_code == 409
    snapshot = {"campaign_id": campaign, "snapshot_date": plan["start_date"], "spend_inr": 100,
        "reach": 100, "impressions": 200, "clicks": 10, "conversations": 2, "sales": 1, "revenue_inr": 500}
    assert client.post("/analytics/snapshots", json=snapshot).status_code == 201
    report = client.get("/analytics/weekly-report", params={"end_date": plan["start_date"]}).json()["metrics"]
    assert report["cpc_inr"] == 10
    assert report["ctr"] == 5
    assert report["roas"] == 5
    snapshot["spend_inr"] = -1
    assert client.post("/analytics/snapshots", json=snapshot).status_code == 422


def test_meta_rejects_arbitrary_remote_paths(local):
    with pytest.raises(ValueError):
        asyncio.run(MetaClient().request("GET", "https://example.com/steal"))
