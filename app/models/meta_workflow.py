"""Additive workflow tracking; existing deployment IDs remain authoritative."""
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class MetaWorkflow(Base):
    __tablename__ = 'meta_workflows'
    campaign_id: Mapped[str] = mapped_column(ForeignKey('campaigns.id'), primary_key=True)
    ad_account_id: Mapped[str | None] = mapped_column(String(64))
    creation_status: Mapped[str] = mapped_column(String(40), default='DRAFT')
    payment_status: Mapped[str] = mapped_column(String(40), default='NOT_REQUESTED')
    owner_status: Mapped[str] = mapped_column(String(40), default='AWAITING_OWNER_APPROVAL')
    connection_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    retry_safe: Mapped[bool] = mapped_column(Boolean, default=False)
    last_sync: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    remote_campaign_status: Mapped[str | None] = mapped_column(String(64))
    remote_ad_status: Mapped[str | None] = mapped_column(String(64))
    last_error: Mapped[str | None] = mapped_column(Text)

class CampaignCreateRequest(Base):
    __tablename__ = 'campaign_create_requests'
    request_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    campaign_id: Mapped[str] = mapped_column(ForeignKey('campaigns.id'))
    payload_hash: Mapped[str] = mapped_column(String(64))
