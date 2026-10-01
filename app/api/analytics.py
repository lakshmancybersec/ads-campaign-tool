from datetime import date, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin_key
from app.database import get_db
from app.models.performance import PerformanceSnapshot
from app.services.analytics import weekly_summary

router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[Depends(require_admin_key)])


class PerformanceSnapshotCreate(BaseModel):
    snapshot_date: date
    campaign_id: str
    adset_id: str | None = None
    ad_id: str | None = None
    location: str | None = None
    spend_inr: float = Field(ge=0)
    reach: int = Field(ge=0)
    impressions: int = Field(ge=0)
    clicks: int = Field(ge=0)
    conversations: int | None = Field(default=None, ge=0)
    leads: int = Field(default=0, ge=0)
    qualified_leads: int = Field(default=0, ge=0)
    sales: int = Field(default=0, ge=0)
    revenue_inr: float = Field(default=0, ge=0)


@router.post("/snapshots", status_code=201)
def record_snapshot(payload: PerformanceSnapshotCreate, db: Session = Depends(get_db)) -> dict[str, str]:
    values = payload.model_dump()
    values["ctr"] = (values["clicks"] / values["impressions"] * 100) if values["impressions"] else None
    values["cpc_inr"] = (values["spend_inr"] / values["clicks"]) if values["clicks"] else None
    values["cost_per_conversation_inr"] = (values["spend_inr"] / values["conversations"]) if values["conversations"] else None
    values["roas"] = (values["revenue_inr"] / values["spend_inr"]) if values["spend_inr"] else None
    snapshot = PerformanceSnapshot(**values)
    db.add(snapshot)
    db.commit()
    return {"snapshot_id": snapshot.id}


@router.get("/weekly-report")
def get_weekly_report(end_date: date | None = None, db: Session = Depends(get_db)) -> dict:
    final_day = end_date or date.today()
    return weekly_summary(db, final_day - timedelta(days=6), final_day)
