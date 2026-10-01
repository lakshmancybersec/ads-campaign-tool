"""Read-only live account and campaign reconciliation check; no Meta writes."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.meta_client import MetaClient, MetaError


async def main():
    client = MetaClient()
    checks = [
        ("Account", lambda: client.validate_account()),
        ("Page", lambda: client.request("GET", client.settings.facebook_page_id, {"fields": "id,name"})),
        ("Campaign reconciliation", lambda: client.all_pages(f"{client.account}/campaigns", {"fields": "id,name,status", "limit": 100})),
    ]
    for name, check in checks:
        try:
            result = await check()
            if isinstance(result, list):
                matches = [r for r in result if r.get("name", "").lower() in {"wedding group set", "diwali festival campaign"}]
                print(name, "scanned:", len(result), "matching campaigns:", matches)
            else:
                print(name, "OK")
        except MetaError as error:
            print(name, str(error))


asyncio.run(main())
