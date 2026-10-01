from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


def test_dashboard_page_and_overview_require_valid_admin_key():
    client = TestClient(app)
    assert client.get("/").status_code == 200
    assert client.get("/dashboard/overview").status_code == 401
    response = client.get("/dashboard/overview", headers={"X-Admin-Key": get_settings().api_admin_key})
    assert response.status_code == 200
    assert response.json()["counts"]["campaigns"] >= 0
