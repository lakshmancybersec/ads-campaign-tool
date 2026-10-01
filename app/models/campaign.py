from datetime import datetime
from uuid import uuid4
import json

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import CampaignStatus


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=CampaignStatus.DRAFT.value, nullable=False)
    meta_campaign_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    daily_budget_inr: Mapped[int] = mapped_column(Integer, nullable=False)
    weekly_budget_limit_inr: Mapped[int] = mapped_column(Integer, nullable=False)
    targeting_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    @property
    def budget_mode(self):
        return json.loads(self.targeting_json or '{}').get('budget_policy', {}).get('mode', 'FIXED')

    @property
    def daily_budget_min_inr(self):
        return json.loads(self.targeting_json or '{}').get('budget_policy', {}).get('min', self.daily_budget_inr)

    @property
    def daily_budget_max_inr(self):
        return json.loads(self.targeting_json or '{}').get('budget_policy', {}).get('max', self.daily_budget_inr)
