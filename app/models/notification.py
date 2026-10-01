from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ApprovalNotification(Base):
    __tablename__ = "approval_notifications"
    approval_id: Mapped[str] = mapped_column(ForeignKey("approvals.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="SENDING")
    message_id: Mapped[str | None] = mapped_column(String(255))


class PaymentEmailNotification(Base):
    __tablename__ = "payment_email_notifications"
    approval_id: Mapped[str] = mapped_column(ForeignKey("approvals.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
