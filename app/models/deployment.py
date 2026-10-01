from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CampaignDeployment(Base):
    """Frozen review material and durable checkpoints for remote operations."""

    __tablename__ = "campaign_deployments"
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"), primary_key=True)
    plan_json: Mapped[str] = mapped_column(Text, nullable=False)
    approval_id: Mapped[str | None] = mapped_column(ForeignKey("approvals.id"))
    remote_campaign_id: Mapped[str | None] = mapped_column(String(128))
    remote_adset_id: Mapped[str | None] = mapped_column(String(128))
    remote_creative_id: Mapped[str | None] = mapped_column(String(128))
    remote_ad_id: Mapped[str | None] = mapped_column(String(128))
    # Commit before each remote creation. An interrupted request must be reconciled,
    # never automatically repeated: Meta may have accepted it before the disconnect.
    operation: Mapped[str | None] = mapped_column(String(64))
    last_error: Mapped[str | None] = mapped_column(String(500))
    automation_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
