"""Local read-only verification. Reports labels/counts, never secret values."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import get_settings
from app.database import engine
from sqlalchemy import inspect
import httpx

s = get_settings()
secrets = {k: getattr(s, k) for k in type(s).model_fields
           if any(x in k for x in ('secret', 'token', 'password', 'admin_key'))
           and isinstance(getattr(s, k), str) and len(getattr(s, k)) >= 8}
matches = []
files = []
for directory in ['app', 'tests', 'scripts', 'docs', 'n8n']:
    files.extend(p for p in Path(directory).rglob('*') if p.is_file()
                 and p.suffix in {'.py', '.js', '.html', '.css', '.md', '.json', '.php'})
for path in files:
    content = path.read_text(encoding='utf-8', errors='replace')
    matches.extend((str(path), key) for key, value in secrets.items() if value in content)
print('Configured-secret matches:', matches, flush=True)
print('PHP source files:', sum(p.suffix == '.php' for p in files), flush=True)
print('Additive tables present:', all(t in inspect(engine).get_table_names()
                                      for t in ['meta_workflows','campaign_create_requests']), flush=True)
with httpx.Client(base_url='http://127.0.0.1:8000', headers={'X-Admin-Key':s.api_admin_key}) as client:
    rows = client.get('/integrations/campaigns').json()
    for row in rows:
        print({key:row.get(key) for key in ['ad_account_id','creation_status','payment_status','prepared','retry_safe','remote_campaign_id','remote_adset_id','remote_creative_id','remote_ad_id']}, flush=True)
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(channel='msedge', headless=True)
    page = browser.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto('http://127.0.0.1:8000/')
    page.locator('#admin-key').fill(s.api_admin_key)
    page.locator('#key-form button').click()
    page.locator('#app').wait_for(state='visible')
    print('Diagnostics visible:', page.locator('.meta-diagnostics').count(), flush=True)
    print('Payment buttons visible:', page.locator('[data-meta-step="billing"]').count(), flush=True)
    print('Activation buttons visible:', page.locator('[data-live-action="activate"]').count(), flush=True)
    print('Browser errors:', errors, flush=True)
    assert not errors
    browser.close()
