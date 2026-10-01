"""Read-only browser check; never submits campaign or Meta actions."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import get_settings
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto("http://127.0.0.1:8000/")
    page.locator("#admin-key").fill(get_settings().api_admin_key)
    page.locator("#key-form button").click()
    page.locator("#app").wait_for(state="visible")
    for selector in ["#plan-campaign", "#plan-product"]:
        control = page.locator(selector)
        values = control.locator("option").evaluate_all("items => items.map(i => i.value).filter(Boolean)")
        print(selector, "enabled:", control.is_enabled(), "options:", len(values))
        if values:
            control.select_option(values[0])
            assert control.input_value() == values[0]
            control.click()
            page.keyboard.press("Escape")
    page.locator('#plan-form textarea').fill("Browser interaction check (not saved)")
    page.locator('#campaign-form input[name=name]').fill("Browser check (not saved)")
    history = page.locator("button[data-reuse-id]")
    if history.count():
        history.first.click()
        assert page.locator("#reuse-campaign").input_value()
        print("History selection: passed")
    print("Editable fields: passed")
    delete_button = page.locator("[data-delete-campaign]").first
    delete_button.click()
    assert page.locator(".delete-confirmation").is_visible()
    assert page.locator("[data-confirm-delete]").is_visible()
    assert page.locator("[data-confirm-archive]").is_visible()
    page.locator("[data-cancel-delete]").click()
    assert page.locator(".delete-confirmation").count() == 0
    print("Delete/archive choices and cancellation: passed (no deletion submitted)")
    # Intercept every write before testing approval; leave real records untouched.
    writes = []
    def intercept(route):
        if route.request.method not in {"GET", "HEAD"}:
            writes.append(route.request.url.split("8000")[-1])
            route.fulfill(status=409, json={"detail": "Browser test: approval blocked deliberately"})
        else:
            route.continue_()
    page.route("**/*", intercept)
    approve = page.locator('button[data-review-action="approve"]')
    if approve.count():
        approve.first.click()
        confirmation = page.locator(".approval-confirmation")
        assert confirmation.is_visible()
        assert not writes
        confirmation.locator('[data-review-action="cancel-approval"]').click()
        assert page.locator(".approval-confirmation").count() == 0
        approve.first.click()
        page.locator('[data-review-action="confirm-approval"]').click()
        page.get_by_text("Browser test: approval blocked deliberately", exact=True).last.wait_for()
        assert page.locator(".approval-result").is_visible()
        assert page.locator('[data-review-action="confirm-approval"]').is_enabled()
        assert writes == ["/approvals/request"]
        print("Approval confirmation, cancellation and inline failure recovery: passed (writes intercepted)")
    print("Disabled buttons:", page.locator("button:disabled").all_text_contents())
    print("Browser errors:", errors)
    assert not errors
    browser.close()
