from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import LeadStatus


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    whatsapp_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    customer_name: Mapped[str | None] = mapped_column(String(255))
    product_interest: Mapped[str | None] = mapped_column(String(255))
    quantity: Mapped[int | None] = mapped_column(Integer)
    city: Mapped[str | None] = mapped_column(String(128))
    latest_message: Mapped[str | None] = mapped_column(Text)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=LeadStatus.LOW.value, nullable=False)
    campaign_id: Mapped[str | None] = mapped_column(ForeignKey("campaigns.id"))
    ad_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
