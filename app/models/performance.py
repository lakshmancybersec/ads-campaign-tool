from datetime import date, datetime
from uuid import uuid4

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PerformanceSnapshot(Base):
    __tablename__ = "performance_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False, index=True)
    adset_id: Mapped[str | None] = mapped_column(String(128))
    ad_id: Mapped[str | None] = mapped_column(String(128))
    location: Mapped[str | None] = mapped_column(String(128))
    spend_inr: Mapped[float] = mapped_column(Float, default=0)
    reach: Mapped[int] = mapped_column(Integer, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    ctr: Mapped[float | None] = mapped_column(Float)
    cpc_inr: Mapped[float | None] = mapped_column(Float)
    conversations: Mapped[int | None] = mapped_column(Integer)
    cost_per_conversation_inr: Mapped[float | None] = mapped_column(Float)
    leads: Mapped[int] = mapped_column(Integer, default=0)
    qualified_leads: Mapped[int] = mapped_column(Integer, default=0)
    sales: Mapped[int] = mapped_column(Integer, default=0)
    revenue_inr: Mapped[float] = mapped_column(Float, default=0)
    roas: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
