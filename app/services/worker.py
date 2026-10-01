import asyncio
import logging

from app.config import get_settings


async def run_worker():
    """Application-owned scheduler; no n8n installation required for safety checks."""
    from app import database
    from app.api.integrations import scheduler, collect
    interval = get_settings().scheduler_interval_seconds
    ticks = 0
    while True:
        try:
            with database.SessionLocal() as db:
                result = await scheduler(db)
                if any("error" in item for item in result["campaigns"]):
                    logging.getLogger(__name__).warning("A campaign needs attention; inspect integration status.")
            if ticks % max(1, 3600 // interval) == 0:
                with database.SessionLocal() as db:
                    await collect(db)
        except Exception:
            # Never log provider request objects or credential-bearing exceptions.
            logging.getLogger(__name__).error("Campaign worker failed; inspect account connectivity and campaign operations.")
        ticks += 1
        await asyncio.sleep(interval)
