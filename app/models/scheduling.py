from datetime import datetime, time
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PeakTimeWindow(Base):
    """A configurable local-time advertising window, stored in Asia/Kolkata time."""

    __tablename__ = "peak_time_windows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CampaignStatusLog(Base):
    """Auditable record of every system-requested campaign state change."""

    __tablename__ = "campaign_status_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), nullable=False, index=True)
    previous_status: Mapped[str] = mapped_column(String(32), nullable=False)
    new_status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), default="system", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
