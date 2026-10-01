"""Real browser + isolated application database; no live Meta requests."""
import pytest
from test_live_integration import local, graph, make_ready
from app import database
from app.models.approval import Approval
from app.models.campaign import Campaign


def test_owner_can_save_review_and_approve_in_browser(local, graph):
    playwright = pytest.importorskip("playwright.sync_api")
    client, settings = local
    settings.meta_paused_preparation_enabled = True
    settings.meta_live_writes_enabled = True
    campaign_id, plan, approval_id = make_ready(client, amount=0)
    with database.SessionLocal() as db:
        db.get(Approval, approval_id).status = "PENDING"
        db.get(Campaign, campaign_id).status = "PENDING_APPROVAL"
        db.commit()
    client.post(f"/approvals/{approval_id}/decision", json={"message": "REJECT"})
    errors = []
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        def route_request(route):
            from urllib.parse import urlsplit
            url = urlsplit(route.request.url)
            if url.netloc != "dashboard.test":
                route.abort()
                return
            response = client.request(route.request.method, url.path + ("?" + url.query if url.query else ""),
                                      content=route.request.post_data_buffer,
                                      headers={"X-Admin-Key": settings.api_admin_key, "Content-Type": "application/json"})
            route.fulfill(status=response.status_code, body=response.content,
                          headers={"content-type": response.headers.get("content-type", "text/plain")})
        page.route("**/*", route_request)
        page.goto("http://dashboard.test/")
        page.locator("#admin-key").fill(settings.api_admin_key)
        page.locator("#key-form button").click()
        page.locator("#app").wait_for(state="visible")
        page.locator("#plan-campaign").select_option(campaign_id)
        page.locator('#budget-mode-form input[value="DYNAMIC"]').check()
        assert page.locator('#budget-fixed-fields').is_hidden()
        assert page.locator('#budget-range-fields').is_visible()
        page.locator('#budget-min').fill('150')
        page.locator('#budget-max').fill('200')
        page.locator('#budget-weekly').fill('1050')
        page.locator('#budget-mode-form button').click()
        page.get_by_text('Budget settings saved to this draft.', exact=False).wait_for()
        assert client.get('/campaigns').json()[0]['budget_mode'] == 'DYNAMIC'
        page.locator('#plan-form textarea').fill("Reviewed browser campaign")
        page.locator("#plan-form button").click()
        page.get_by_text("Plan saved.", exact=False).wait_for()
        page.locator('[data-review-action="approve"]').click()
        page.locator('[data-review-action="confirm-approval"]').click()
        page.get_by_text("Plan approved. Next:", exact=False).wait_for()
        assert client.get('/campaigns').json()[0]['status'] == 'READY'
        assert page.locator('#request-payment-email').count() == 0
        assert page.get_by_text('Payment confirmed:', exact=False).count() == 0
        assert page.get_by_role('link', name='Open Meta payment').count() == 0
        assert page.locator('[data-meta-step="billing"]').count() == 0
        page.get_by_role('link', name='Continue to Meta setup').click()
        assert page.locator('#launch-section').is_visible()
        page.locator('[data-live-action="prepare"]').click()
        page.locator('[data-meta-step="billing"]').wait_for(state='visible')
        page.locator('[data-meta-step="billing"]').click()
        billing = page.get_by_role('link', name='Open verified Meta billing account')
        billing.wait_for(state='visible')
        assert billing.get_attribute('href').endswith('?act=123')
        assert billing.get_attribute('target') == '_blank'
        page.locator('.billing-reviewed').check()
        page.locator('[data-meta-step="launch-approval"]').click()
        page.locator('[data-live-action="activate"]').wait_for(state='visible')
        assert len(graph.posts) == 4  # no activation or payment writes
        page.locator("#refresh").click()
        page.get_by_text("Dashboard refreshed.", exact=False).wait_for()
        assert page.locator("#plan-campaign").input_value() == campaign_id
        assert page.locator('[data-review-action="approve"]').count() == 0
        page.locator("#logout").click()
        page.locator("#key-panel").wait_for(state="visible")
        assert page.locator("#app").is_hidden()
        assert page.locator("#admin-key").input_value() == ""
        assert not errors
        browser.close()
