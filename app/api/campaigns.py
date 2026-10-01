from datetime import datetime, date
import json
from app.services.deployment import CampaignPlan, save_plan

from fastapi import APIRouter, Depends, HTTPException, status, Header
import hashlib
from sqlalchemy.exc import IntegrityError
from app.models.meta_workflow import MetaWorkflow, CampaignCreateRequest
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.api.dependencies import require_admin_key
from app.database import get_db
from app.models.campaign import Campaign
from app.models.enums import CampaignStatus
from app.models.approval import Approval
from app.models.deployment import CampaignDeployment
from app.models.notification import ApprovalNotification, PaymentEmailNotification
from app.models.payment import Payment
from app.models.lead import Lead
from app.models.performance import PerformanceSnapshot
from app.models.scheduling import CampaignStatusLog

router = APIRouter(prefix="/campaigns", tags=["campaigns"], dependencies=[Depends(require_admin_key)])


class CampaignCreate(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    daily_budget_inr: int = Field(gt=0, le=200, strict=True)
    weekly_budget_limit_inr: int = Field(gt=0, le=1050, strict=True)
    budget_mode: Literal['FIXED', 'DYNAMIC'] = 'FIXED'
    daily_budget_min_inr: int | None = Field(default=None, ge=150, le=200, strict=True)
    daily_budget_max_inr: int | None = Field(default=None, ge=150, le=200, strict=True)

    @model_validator(mode='after')
    def budget_bounds(self):
        if self.budget_mode == 'FIXED':
            if self.daily_budget_inr > 150:
                raise ValueError('Fixed budgets are capped at INR 150/day; explicitly select Dynamic to approve a higher range.')
        elif (self.daily_budget_min_inr is None or self.daily_budget_max_inr is None
              or self.daily_budget_min_inr > self.daily_budget_max_inr
              or self.daily_budget_inr != self.daily_budget_max_inr):
            raise ValueError('Dynamic mode requires an ordered approved range; daily limit must equal its maximum.')
        return self

def store_budget_policy(campaign, payload):
    data = json.loads(campaign.targeting_json or '{}')
    data['budget_policy'] = {'mode':payload.budget_mode,
        'min':payload.daily_budget_min_inr if payload.budget_mode == 'DYNAMIC' else payload.daily_budget_inr,
        'max':payload.daily_budget_inr}
    campaign.targeting_json = json.dumps(data)


class CampaignRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    status: str
    daily_budget_inr: int
    weekly_budget_limit_inr: int
    created_at: datetime
    budget_mode: str
    daily_budget_min_inr: int
    daily_budget_max_inr: int


class CampaignReuse(CampaignCreate):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_dates(self):
        if not 0 <= (self.end_date - self.start_date).days <= 6:
            raise ValueError("Choose a campaign duration of one to seven days.")
        return self


@router.get("/reusable")
def reusable_campaigns(db: Session = Depends(get_db)):
    return [{"id": c.id, "name": c.name, "status": c.status,
             "previously_run": c.status in {"ACTIVE", "PAUSED", "ENDED"}}
            for c, d in db.execute(select(Campaign, CampaignDeployment).join(
                CampaignDeployment, CampaignDeployment.campaign_id == Campaign.id)) if not d.operation]


@router.post("/{campaign_id}/reuse", response_model=CampaignRead, status_code=201)
def reuse_campaign(campaign_id: str, payload: CampaignReuse, db: Session = Depends(get_db)):
    source = db.get(Campaign, campaign_id)
    deployment = db.get(CampaignDeployment, campaign_id)
    if not source:
        raise HTTPException(404, "Campaign not found.")
    if not deployment or deployment.operation:
        raise HTTPException(409, "Select a campaign with a saved plan and no pending operation.")
    old = json.loads(deployment.plan_json)
    plan = CampaignPlan(**{**{k: old[k] for k in CampaignPlan.model_fields},
                            "start_date": payload.start_date, "end_date": payload.end_date})
    campaign = Campaign(name=payload.name, status="DRAFT", daily_budget_inr=payload.daily_budget_inr,
                        weekly_budget_limit_inr=payload.weekly_budget_limit_inr)
    store_budget_policy(campaign, payload)
    db.add(campaign)
    db.flush()
    try:
        save_plan(db, campaign, plan)
    except Exception:
        db.rollback()
        raise
    db.refresh(campaign)
    return campaign


@router.get("", response_model=list[CampaignRead])
def list_campaigns(include_archived: bool = False, db: Session = Depends(get_db)) -> list[Campaign]:
    query = select(Campaign)
    if not include_archived:
        query = query.where(Campaign.status != "ARCHIVED")
    return list(db.scalars(query.order_by(Campaign.created_at.desc())))


@router.post("", response_model=CampaignRead, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(require_admin_key)])
def create_campaign(payload: CampaignCreate, db: Session = Depends(get_db),
                    idempotency_key: str | None = Header(default=None, max_length=64)) -> Campaign:
    digest = hashlib.sha256(payload.model_dump_json().encode()).hexdigest()
    if idempotency_key:
        existing = db.get(CampaignCreateRequest, idempotency_key)
        if existing:
            if existing.payload_hash != digest:
                raise HTTPException(409, 'This creation request was already used with different details.')
            return db.get(Campaign, existing.campaign_id)
    campaign = Campaign(name=payload.name, status=CampaignStatus.DRAFT.value,
                        daily_budget_inr=payload.daily_budget_inr,
                        weekly_budget_limit_inr=payload.weekly_budget_limit_inr)
    store_budget_policy(campaign, payload)
    db.add(campaign)
    db.flush()
    if idempotency_key:
        db.add(CampaignCreateRequest(request_key=idempotency_key, campaign_id=campaign.id, payload_hash=digest))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.get(CampaignCreateRequest, idempotency_key) if idempotency_key else None
        if not existing or existing.payload_hash != digest:
            raise HTTPException(409, 'Campaign request conflict.') from None
        return db.get(Campaign, existing.campaign_id)
    db.refresh(campaign)
    return campaign


@router.delete("/{campaign_id}")
def delete_campaign(campaign_id: str, db: Session = Depends(get_db)):
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found.")
    deployment = db.get(CampaignDeployment, campaign_id)
    if campaign.status not in {"DRAFT", "PENDING_APPROVAL", "READY", "FAILED"} or campaign.meta_campaign_id or (
        deployment and any((deployment.operation, deployment.automation_enabled,
            deployment.remote_campaign_id, deployment.remote_adset_id,
            deployment.remote_creative_id, deployment.remote_ad_id))
    ):
        raise HTTPException(409, "Only local campaigns without Meta objects or pending operations can be deleted. Pause or end Meta campaigns instead.")
    for model in (Payment, Lead, PerformanceSnapshot):
        if db.scalar(select(model).where(model.campaign_id == campaign_id).limit(1)):
            raise HTTPException(409, "This campaign has payment, lead or performance records and cannot be deleted.")
    approval_ids = select(Approval.id).where(Approval.campaign_id == campaign_id)
    if db.scalar(select(PaymentEmailNotification).where(PaymentEmailNotification.approval_id.in_(approval_ids)).limit(1)):
        raise HTTPException(409, "This campaign has email notification history. Archive it instead.")
    if db.scalar(select(ApprovalNotification).where(ApprovalNotification.approval_id.in_(approval_ids)).limit(1)):
        raise HTTPException(409, "This campaign has a WhatsApp notification history and cannot be deleted.")
    db.execute(delete(CampaignDeployment).where(CampaignDeployment.campaign_id == campaign_id))
    db.execute(delete(MetaWorkflow).where(MetaWorkflow.campaign_id == campaign_id))
    db.execute(delete(CampaignCreateRequest).where(CampaignCreateRequest.campaign_id == campaign_id))
    db.execute(delete(Approval).where(Approval.campaign_id == campaign_id))
    db.execute(delete(CampaignStatusLog).where(CampaignStatusLog.campaign_id == campaign_id))
    db.delete(campaign)
    db.commit()
    return {"deleted": campaign_id}


@router.post('/{campaign_id}/edit')
def reopen_campaign(campaign_id: str, db: Session = Depends(get_db)):
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(404, 'Campaign not found.')
    deployment = db.get(CampaignDeployment, campaign_id)
    if campaign.status not in {'DRAFT', 'PENDING_APPROVAL', 'READY', 'FAILED'} or campaign.meta_campaign_id or (
        deployment and any((deployment.operation, deployment.automation_enabled, deployment.remote_campaign_id,
                            deployment.remote_adset_id, deployment.remote_creative_id, deployment.remote_ad_id))):
        raise HTTPException(409, 'This campaign has Meta activity. Use campaign history to create an editable copy; the original stays unchanged.')
    for approval in db.scalars(select(Approval).where(Approval.campaign_id == campaign_id,
                                                     Approval.status.in_(['PENDING', 'APPROVED']))):
        approval.status = 'REJECTED'
        approval.decision_note = 'Owner reopened campaign for editing; fresh approval required.'
        approval.decided_at = datetime.now()
    if deployment:
        deployment.approval_id = None
        deployment.last_error = None
    state = db.get(MetaWorkflow, campaign_id)
    if state:
        state.creation_status = 'DRAFT'
        state.owner_status = 'AWAITING_OWNER_APPROVAL'
        state.verified = False
        state.retry_safe = False
        state.last_error = None
    campaign.status = 'DRAFT'
    db.commit()
    return {'id': campaign_id, 'status': 'DRAFT'}


class BudgetUpdate(CampaignCreate):
    name: str = 'Budget settings'

@router.put('/{campaign_id}/budget', response_model=CampaignRead)
def update_budget(campaign_id: str, payload: BudgetUpdate, db: Session = Depends(get_db)):
    campaign = db.get(Campaign, campaign_id)
    deployment = db.get(CampaignDeployment, campaign_id)
    if not campaign:
        raise HTTPException(404, 'Campaign not found.')
    if campaign.status != 'DRAFT' or campaign.meta_campaign_id or (deployment and deployment.operation):
        raise HTTPException(409, 'Budget changes require an editable draft. Use campaign history to create a new draft for a campaign already approved or sent to Meta.')
    campaign.daily_budget_inr = payload.daily_budget_inr
    campaign.weekly_budget_limit_inr = payload.weekly_budget_limit_inr
    store_budget_policy(campaign, payload)
    if deployment:
        save_plan(db, campaign, CampaignPlan(**json.loads(deployment.plan_json)))
    else:
        db.commit()
    db.refresh(campaign)
    return campaign


@router.post("/{campaign_id}/archive")
def archive_campaign(campaign_id: str, db: Session = Depends(get_db)):
    campaign = db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(404, "Campaign not found.")
    deployment = db.get(CampaignDeployment, campaign_id)
    if campaign.status not in {"DRAFT", "PENDING_APPROVAL", "ARCHIVED"} or campaign.meta_campaign_id or (
        deployment and any((deployment.operation, deployment.automation_enabled, deployment.remote_campaign_id,
                            deployment.remote_adset_id, deployment.remote_creative_id, deployment.remote_ad_id))):
        raise HTTPException(409, "Only unlaunched draft or pending campaigns can be archived.")
    campaign.status = "ARCHIVED"
    db.commit()
    return {"archived": campaign_id}
