from fastapi.testclient import TestClient

from app.main import app
from app.config import get_settings


def test_setup_status_returns_non_secret_profile_and_missing_requirements(monkeypatch):
    monkeypatch.setattr(get_settings(), "meta_access_token", None)
    monkeypatch.setattr(get_settings(), "meta_live_writes_enabled", False)
    monkeypatch.setattr(get_settings(), "meta_ad_account_id", "act_249780244315816")
    response = TestClient(app).get("/setup/status", headers={"X-Admin-Key": get_settings().api_admin_key})

    assert response.status_code == 200
    body = response.json()
    assert body["live_operations_enabled"] is False
    assert body["profile"]["meta_ad_account_id"] == "act_249780244315816"
    assert "META_ACCESS_TOKEN" in body["missing_live_configuration"]
    assert "meta_access_token" not in body["profile"]
