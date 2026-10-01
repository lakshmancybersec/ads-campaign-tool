from datetime import datetime, timezone
import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from urllib.parse import urlencode
from app.config import get_settings
import re
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin_key
from app.database import get_db
from app.models.approval import Approval
from app.models.campaign import Campaign
from app.models.catalog import CatalogProduct
from app.models.enums import ApprovalStatus, CampaignStatus, PaymentStatus
from app.models.payment import Payment
from app.models.deployment import CampaignDeployment
from app.models.notification import ApprovalNotification
from app.services.whatsapp import WhatsAppService
from app.services.meta_client import MetaError
from sqlalchemy.exc import IntegrityError
from app.services.approval import parse_owner_approval, refresh_campaign_readiness

router = APIRouter(tags=["approvals"])


@router.get("/approvals", dependencies=[Depends(require_admin_key)])
def list_approvals(db: Session = Depends(get_db)) -> list[dict]:
    return [{"id": item.id, "campaign_id": item.campaign_id, "status": item.status,
             "product_code": item.selected_product_code, "created_at": item.created_at}
            for item in db.scalars(select(Approval).order_by(Approval.created_at.desc()))]


@router.get("/payments", dependencies=[Depends(require_admin_key)])
def list_payments(db: Session = Depends(get_db)) -> list[dict]:
    return [{"id": item.id, "campaign_id": item.campaign_id, "status": item.status,
             "amount_inr": item.amount_inr, "payment_reference": item.payment_reference}
            for item in db.scalars(select(Payment).order_by(Payment.created_at.desc()))]


class ApprovalRequest(BaseModel):
    campaign_id: str
    product_code: str


class OwnerDecision(BaseModel):
    message: str = Field(min_length=1, max_length=200)


class PaymentConfirmation(BaseModel):
    campaign_id: str
    amount_inr: int = Field(gt=0)
    payment_reference: str = Field(min_length=3, max_length=128)


@router.get("/payments/{campaign_id}/whatsapp-request", dependencies=[Depends(require_admin_key)])
async def payment_whatsapp_request(campaign_id: str, db: Session = Depends(get_db)):
    from app.services.meta_workflow import verify_objects
    await verify_objects(db, _get_campaign(db, campaign_id))
    result = payment_request_content(campaign_id, db)
    number = get_settings().owner_whatsapp_number or ""
    if not re.fullmatch(r"[1-9][0-9]{7,14}", number):
        raise HTTPException(409, "Set OWNER_WHATSAPP_NUMBER with country code and digits only.")
    return {**result, "url": f"https://wa.me/{number}?" + urlencode({"text": result['message']}), "sent": False}


def payment_request_content(campaign_id, db):
    campaign = _get_campaign(db, campaign_id)
    deployment = db.get(CampaignDeployment, campaign_id)
    approval = db.get(Approval, deployment.approval_id) if deployment and deployment.approval_id else None
    if campaign.status not in {"PENDING_APPROVAL", "READY"} or not approval or approval.status != "APPROVED":
        raise HTTPException(409, "Save and approve the campaign plan before requesting payment.")
    plan = json.loads(deployment.plan_json)
    if plan["daily_budget_inr"] != campaign.daily_budget_inr or plan["weekly_budget_inr"] != campaign.weekly_budget_limit_inr:
        raise HTTPException(409, "Budget differs from the approved plan. Review the campaign again.")
    confirmed = db.scalar(select(func.coalesce(func.sum(Payment.amount_inr), 0)).where(
        Payment.campaign_id == campaign_id, Payment.status == "CONFIRMED"))
    remaining = max(0, campaign.weekly_budget_limit_inr - confirmed)
    if remaining == 0:
        raise HTTPException(409, "The approved budget is already covered by confirmed payments.")
    message = (f"Lakshiya Dhotis: payment request\nCampaign: {campaign.name}\n"
        f"Product: {plan['product_name']}\nApproved daily budget: INR {campaign.daily_budget_inr}\n"
        f"Approved total limit: INR {campaign.weekly_budget_limit_inr}\n"
        f"Payment still to confirm: INR {remaining}\n"
        "Please pay Meta directly through your ad account billing and share the payment reference. "
        "If already paid, share the reference for verification instead of paying again. "
        "Payment will be checked and recorded separately. This message does not launch an ad.")
    return {"message": message, "remaining_inr": remaining}


@router.post("/payments/{campaign_id}/email-request", dependencies=[Depends(require_admin_key)])
async def payment_email_request(campaign_id: str, db: Session = Depends(get_db)):
    from app.services.meta_workflow import verify_objects
    await verify_objects(db, _get_campaign(db, campaign_id))
    from app.services.email_notifications import validate_email, send_payment_email
    from app.models.notification import PaymentEmailNotification
    content = payment_request_content(campaign_id, db)
    validate_email()
    approval_id = db.get(CampaignDeployment, campaign_id).approval_id
    existing = db.get(PaymentEmailNotification, approval_id)
    if existing:
        return {"status": existing.status, "note": "An email attempt already exists. No duplicate email sent."}
    record = PaymentEmailNotification(approval_id=approval_id, status="SENDING")
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email request already in progress.") from None
    try:
        send_payment_email(content['message'])
        record.status = "ACCEPTED_BY_SMTP"
        db.commit()
    except MetaError:
        record.status = "UNCONFIRMED"
        db.commit()
        raise
    return {"status": record.status, "note": "Email accepted by the mail server; inbox delivery and payment are not verified."}


@router.post("/approvals/{approval_id}/notify", dependencies=[Depends(require_admin_key)])
async def notify_owner(approval_id: str, db: Session = Depends(get_db)):
    approval = db.get(Approval, approval_id)
    if not approval or approval.status != "PENDING":
        raise HTTPException(409, "Only pending approvals can be sent.")
    campaign = _get_campaign(db, approval.campaign_id)
    deployment = db.get(CampaignDeployment, campaign.id)
    if not deployment or deployment.approval_id != approval.id:
        raise HTTPException(409, "Save and request approval of a complete campaign plan first.")
    service = WhatsAppService()
    service.validate()
    existing = db.get(ApprovalNotification, approval_id)
    if existing:
        return {"status": existing.status, "note": "An attempt already exists; no duplicate message sent."}
    notification = ApprovalNotification(approval_id=approval_id, status="SENDING")
    db.add(notification)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Notification already requested.") from None
    try:
        notification.message_id = await service.send_approval(campaign.name, approval.selected_product_code, approval.id)
        notification.status = "SENT"
        db.commit()
    except MetaError:
        notification.status = "UNCONFIRMED"
        db.commit()
        raise
    return {"status": notification.status}


def _get_campaign(db: Session, campaign_id: str) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found.")
    return campaign


@router.post("/approvals/request", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin_key)])
def request_approval(payload: ApprovalRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    campaign = _get_campaign(db, payload.campaign_id)
    product = db.scalar(select(CatalogProduct).where(CatalogProduct.product_code == payload.product_code))
    if not product or not product.available:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Selected product is unavailable.")
    if campaign.status not in {CampaignStatus.DRAFT.value, CampaignStatus.PENDING_APPROVAL.value}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Campaign cannot request approval in its current state.")
    if db.scalar(select(Approval.id).where(Approval.campaign_id == campaign.id,
                                         Approval.status.in_([ApprovalStatus.PENDING.value, ApprovalStatus.APPROVED.value]))):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This campaign already has a pending or approved creative.")
    deployment = db.get(CampaignDeployment, campaign.id)
    if not deployment:
        raise HTTPException(409, "Save a complete campaign plan before requesting approval.")
    if json.loads(deployment.plan_json)["product_code"] != payload.product_code:
        raise HTTPException(status_code=409, detail="Select the product in the saved campaign plan.")
    approval = Approval(campaign_id=campaign.id, selected_product_code=product.product_code)
    campaign.status = CampaignStatus.PENDING_APPROVAL.value
    db.add(approval)
    db.flush()
    if deployment:
        deployment.approval_id = approval.id
    db.commit()
    return {"approval_id": approval.id, "campaign_status": campaign.status}


@router.post("/approvals/{approval_id}/decision", dependencies=[Depends(require_admin_key)])
def record_owner_decision(approval_id: str, payload: OwnerDecision, db: Session = Depends(get_db)) -> dict[str, str]:
    result = apply_owner_decision(approval_id, payload, db)
    db.commit()
    return result


def apply_owner_decision(approval_id: str, payload: OwnerDecision, db: Session) -> dict[str, str]:
    approval = db.get(Approval, approval_id)
    if not approval:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Approval request not found.")
    if approval.status != ApprovalStatus.PENDING.value:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Approval was already decided.")
    try:
        command = parse_owner_approval(payload.message)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error
    campaign = _get_campaign(db, approval.campaign_id)
    if campaign.status != CampaignStatus.PENDING_APPROVAL.value:
        raise HTTPException(status_code=409, detail="Campaign is no longer awaiting approval.")
    if command.approved and command.product_code.casefold() != (approval.selected_product_code or "").casefold():
        raise HTTPException(status_code=409, detail="Approve the requested product, or reject and request another photo.")
    if command.approved and command.product_code:
        deployment = db.get(CampaignDeployment, campaign.id)
        if not deployment or deployment.approval_id != approval.id:
            raise HTTPException(409, "This approval has no saved campaign plan. Reject it, save the plan and request approval again.")
        product = db.scalar(select(CatalogProduct).where(CatalogProduct.product_code == approval.selected_product_code))
        if not product or not product.available:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Approved product is unavailable.")
        product.owner_approved = True
    elif not command.approved:
        campaign.status = CampaignStatus.DRAFT.value
    approval.status = ApprovalStatus.APPROVED.value if command.approved else ApprovalStatus.REJECTED.value
    approval.decision_note = payload.message
    approval.decided_at = datetime.now(timezone.utc)
    db.flush()
    campaign_status = refresh_campaign_readiness(db, campaign).value
    return {"approval_status": approval.status, "campaign_status": campaign_status}


@router.post("/payments/confirm", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin_key)])
def confirm_payment(payload: PaymentConfirmation, db: Session = Depends(get_db)) -> dict[str, str]:
    campaign = _get_campaign(db, payload.campaign_id)
    if campaign.status not in {CampaignStatus.DRAFT.value, CampaignStatus.PENDING_APPROVAL.value, CampaignStatus.READY.value}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment cannot be recorded for this campaign state.")
    if db.scalar(select(Payment).where(Payment.payment_reference == payload.payment_reference)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Payment reference already recorded.")
    payment = Payment(campaign_id=campaign.id, amount_inr=payload.amount_inr,
                      payment_reference=payload.payment_reference, status=PaymentStatus.CONFIRMED.value,
                      confirmed_at=datetime.now(timezone.utc))
    db.add(payment)
    db.flush()
    campaign_status = refresh_campaign_readiness(db, campaign).value
    db.commit()
    return {"payment_status": payment.status, "campaign_status": campaign_status}
