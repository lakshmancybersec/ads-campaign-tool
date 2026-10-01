from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.approvals import router as approvals_router
from app.api.analytics import router as analytics_router
from app.api.campaigns import router as campaigns_router
from app.api.catalog import router as catalog_router
from app.api.dashboard import router as dashboard_router
from app.api.health import router as health_router
from app.api.setup import router as setup_router
from app.api.webhooks import router as webhooks_router
from app.api.integrations import router as integrations_router
from app.services.meta_client import MetaError
from app.config import get_settings
from app.database import init_db


def create_app() -> FastAPI:
    settings = get_settings()
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        init_db()
        task = None
        if settings.scheduler_enabled and settings.meta_live_writes_enabled:
            from app.services.worker import run_worker
            task = asyncio.create_task(run_worker())
        try:
            yield
        finally:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    application = FastAPI(title=settings.app_name, version="0.2.0", lifespan=lifespan)
    application.include_router(health_router)
    application.include_router(setup_router)
    application.include_router(campaigns_router)
    application.include_router(catalog_router)
    application.include_router(dashboard_router)
    application.include_router(approvals_router)
    application.include_router(webhooks_router)
    application.include_router(analytics_router)
    application.include_router(integrations_router)

    @application.exception_handler(MetaError)
    async def meta_error_handler(request, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc)})
    application.mount("/static", StaticFiles(directory="app/static"), name="static")

    @application.get("/", include_in_schema=False)
    def dashboard() -> FileResponse:
        return FileResponse("app/static/dashboard.html", headers={"Cache-Control": "no-store"})
    return application


app = create_app()
