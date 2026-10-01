import re
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.approval import Approval
from app.models.campaign import Campaign
from app.models.enums import ApprovalStatus, CampaignStatus, PaymentStatus
from app.models.payment import Payment
from app.models.deployment import CampaignDeployment

APPROVE_PATTERN = re.compile(r"^\s*APPROVE\s+([A-Za-z0-9_-]{1,64})\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class ApprovalCommand:
    approved: bool
    product_code: str | None = None


def parse_owner_approval(message: str) -> ApprovalCommand:
    match = APPROVE_PATTERN.match(message)
    if match:
        return ApprovalCommand(approved=True, product_code=match.group(1).upper())
    if message.strip().upper() in {"CHANGE PHOTO", "REJECT", "REJECTED"}:
        return ApprovalCommand(approved=False)
    raise ValueError("Invalid approval command. Use APPROVE <PRODUCT_CODE> or CHANGE PHOTO.")


def refresh_campaign_readiness(db: Session, campaign: Campaign) -> CampaignStatus:
    """Owner approval of the saved plan permits preparation; never activates ads."""
    deployment = db.get(CampaignDeployment, campaign.id)
    approval = db.get(Approval, deployment.approval_id) if deployment and deployment.approval_id else None
    approved = approval and approval.campaign_id == campaign.id and approval.status == ApprovalStatus.APPROVED.value
    if campaign.status == CampaignStatus.PENDING_APPROVAL.value and approved:
        campaign.status = CampaignStatus.READY.value
    return CampaignStatus(campaign.status)
