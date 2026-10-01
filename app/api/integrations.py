import json
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm import object_session
from pydantic import BaseModel
from app.models.meta_workflow import MetaWorkflow
from app.services.meta_workflow import verify_objects, workflow

from app.api.dependencies import require_admin_key
from app.config import get_settings
from app.database import get_db
from app.models.campaign import Campaign
from app.models.catalog import CatalogProduct
from app.models.deployment import CampaignDeployment
from app.models.performance import PerformanceSnapshot
from app.services.deployment import CampaignPlan, save_plan, prepare, change_delivery, claim, log_status
from app.services.meta_client import MetaClient, MetaError
from app.services.scheduler import TimeWindow, is_inside_peak_window

router = APIRouter(prefix="/integrations", tags=["integrations"], dependencies=[Depends(require_admin_key)])


@router.post("/meta/mcp/check")
async def check_ads_mcp():
    from app.services.ads_mcp import probe_ads_mcp
    return await probe_ads_mcp()


def campaign_or_404(db, identifier):
    campaign = db.get(Campaign, identifier)
    if not campaign:
        raise HTTPException(404, "Campaign not found.")
    return campaign


def deployment_view(item):
    db = object_session(item)
    state = db.get(MetaWorkflow, item.campaign_id) if db else None
    from app.services.budget_diagnosis import diagnose_budget
    error = state.last_error if state and state.last_error else item.last_error
    return {"campaign_id": item.campaign_id, "approval_id": item.approval_id, "plan": json.loads(item.plan_json),
        "prepared": bool(state and state.verified), "remote_campaign_id": item.remote_campaign_id,
        "remote_adset_id": item.remote_adset_id, "remote_creative_id": item.remote_creative_id, "remote_ad_id": item.remote_ad_id,
        "ad_account_id": state.ad_account_id if state else None,
        "creation_status": state.creation_status if state else ('CREATION_FAILED' if item.operation else 'DRAFT'),
        "payment_status": state.payment_status if state else 'NOT_REQUESTED',
        "owner_status": state.owner_status if state else 'AWAITING_OWNER_APPROVAL',
        "connection_ok": bool(state and state.connection_ok), "verified": bool(state and state.verified),
        "last_meta_sync": state.last_sync if state else None,
        "meta_campaign_status": state.remote_campaign_status if state else None,
        "meta_ad_status": state.remote_ad_status if state else None,
        "billing_note": 'Billing/payment is not verified by this API. Review it in Meta.',
        "budget_diagnosis": diagnose_budget(json.loads(item.plan_json), error),
        "retry_safe": bool(state and state.retry_safe and not item.operation),
        "operation": item.operation, "last_error": state.last_error if state and state.last_error else item.last_error,
        "automation_enabled": item.automation_enabled}

@router.post('/campaigns/{campaign_id}/health')
async def campaign_health(campaign_id: str, db: Session = Depends(get_db)):
    campaign = campaign_or_404(db, campaign_id)
    await verify_objects(db, campaign)
    return deployment_view(db.get(CampaignDeployment, campaign_id))

@router.post('/campaigns/{campaign_id}/billing')
async def campaign_billing(campaign_id: str, db: Session = Depends(get_db)):
    campaign = campaign_or_404(db, campaign_id)
    state = await verify_objects(db, campaign)
    state.payment_status = 'PAYMENT_PENDING'
    db.commit()
    return {'url': 'https://adsmanager.facebook.com/adsmanager/billing/transactions/?act=' + state.ad_account_id.removeprefix('act_'),
            'payment_status': state.payment_status, 'note': 'Complete billing in Meta; opening this link does not confirm payment.'}

class LaunchApproval(BaseModel):
    billing_reviewed_in_meta: bool

class ScheduleUpdate(BaseModel):
    start_date: date
    end_date: date

@router.put('/campaigns/{campaign_id}/schedule')
async def update_schedule(campaign_id: str, payload: ScheduleUpdate, db: Session = Depends(get_db)):
    from app.services.deployment import approved_plan
    campaign = campaign_or_404(db, campaign_id)
    d = db.get(CampaignDeployment, campaign_id)
    client = MetaClient()
    client.require_writes(preparation=True)
    plan = approved_plan(db, campaign, d)
    zone = ZoneInfo(plan['timezone'])
    if payload.start_date < datetime.now(zone).date() or not 0 <= (payload.end_date - payload.start_date).days <= 6:
        raise HTTPException(422, 'Choose today or a future start date and a duration of one to seven days.')
    if d.operation or d.automation_enabled or campaign.status not in {'READY', 'PAUSED', 'FAILED'}:
        raise HTTPException(409, 'Pause delivery and resolve pending operations before editing the schedule.')
    state = await verify_objects(db, campaign, client)
    for identifier in [d.remote_campaign_id, d.remote_adset_id, d.remote_ad_id]:
        remote = await client.request('GET', identifier, {'fields':'id,status'})
        if remote.get('status') != 'PAUSED':
            raise HTTPException(409, 'Campaign, Ad Set and Ad must all be paused before editing dates.')
    start = max(datetime.combine(payload.start_date, time.min, zone), datetime.now(zone) + timedelta(minutes=5)).replace(microsecond=0)
    end = datetime.combine(payload.end_date + timedelta(days=1), time.min, zone)
    if start >= end:
        raise HTTPException(422, 'Not enough time remains today. Choose a future schedule.')
    claim(db, d, 'update:schedule')
    state.verified = False
    state.owner_status = 'AWAITING_OWNER_APPROVAL'
    db.commit()
    try:
        result = await client.request('POST', d.remote_adset_id, {'start_time':start.isoformat(), 'end_time':end.isoformat()})
        if result.get('success') is not True:
            raise MetaError('Meta did not confirm the date update. Reconcile the schedule before retrying.')
        remote = await client.request('GET', d.remote_adset_id, {'fields':'id,start_time,end_time'})
        if (datetime.fromisoformat(remote.get('start_time', '')) != start.replace(microsecond=0)
                or datetime.fromisoformat(remote.get('end_time', '')) != end):
            raise MetaError('Meta schedule read-back differs from the requested dates; review before retrying.')
        plan.update(start_date=payload.start_date.isoformat(), end_date=payload.end_date.isoformat())
        d.plan_json = json.dumps(plan, sort_keys=True)
        d.operation = None
        d.last_error = None
        db.commit()
        await verify_objects(db, campaign, client)
        return deployment_view(d)
    except (MetaError, ValueError) as error:
        message = str(error) if isinstance(error, MetaError) else 'Meta returned an invalid schedule; reconcile before retrying.'
        if isinstance(error, MetaError) and error.definitive:
            d.operation = None
        d.last_error = state.last_error = message
        state.verified = False
        state.creation_status = 'META_SYNC_ERROR'
        db.commit()
        raise MetaError(message) from None

@router.post('/campaigns/{campaign_id}/launch-approval')
async def launch_approval(campaign_id: str, payload: LaunchApproval, db: Session = Depends(get_db)):
    if not payload.billing_reviewed_in_meta:
        raise HTTPException(409, 'Review billing in Meta before approving launch.')
    campaign = campaign_or_404(db, campaign_id)
    d = db.get(CampaignDeployment, campaign_id)
    from app.services.deployment import approved_plan
    approved_plan(db, campaign, d)
    state = await verify_objects(db, campaign)
    if state.remote_ad_status in {'PENDING_BILLING_INFO', 'DISAPPROVED', 'WITH_ISSUES'}:
        raise HTTPException(409, 'Resolve the ad delivery or billing issue in Meta before approving launch.')
    if state.payment_status not in {'PAYMENT_PENDING', 'OWNER_REVIEWED_IN_META'}:
        raise HTTPException(409, 'Open Meta billing and review payment setup first.')
    state.payment_status = 'OWNER_REVIEWED_IN_META'
    state.owner_status = 'APPROVED'
    db.commit()
    return deployment_view(d)


@router.post("/meta/check")
async def check_meta():
    return {"account": await MetaClient().validate_account(),
            "note": "Account read access verified. Publishing permissions and creatives require a separate paused preparation test."}


@router.get("/meta/locations")
async def locations(q: str = Query(min_length=2, max_length=100)):
    data = await MetaClient().request("GET", "search", {"type": "adgeolocation", "q": q,
        "country_code": "IN", "location_types": ["city", "region"], "limit": 25})
    return [{"key": str(row["key"]), "name": row["name"], "type": row["type"]}
            for row in data.get("data", []) if row.get("country_code") == "IN" and row.get("type") in {"city", "region"}]


@router.post("/meta/catalog/import")
async def import_catalog(db: Session = Depends(get_db)):
    catalog_id = get_settings().meta_catalog_id or ""
    if not catalog_id.isdigit():
        raise MetaError("Configure META_CATALOG_ID using the product catalog ID from Commerce Manager.")
    rows = await MetaClient().all_pages(f"{catalog_id}/products", {
        "fields": "id,retailer_id,name,description,image_url,price,currency,availability", "limit": 100})
    imported, skipped = 0, 0
    for row in rows:
        # Prefix by Meta item ID to avoid overwriting manually entered product codes.
        code = "META-" + str(row.get("id", ""))
        try:
            raw_price = str(row.get("price", "")).strip()
            # Meta may return a formatted rupee amount instead of numeric paise.
            if raw_price.startswith("₹"):
                amount = Decimal(raw_price[1:].strip().replace(",", ""))
            else:
                amount = Decimal(raw_price) / 100
            if row.get("currency") != "INR" or amount <= 0 or amount != amount.to_integral_value():
                raise ValueError()
            from urllib.parse import urlparse
            if urlparse(row.get("image_url", "")).scheme not in {"https", "http"} or not row.get("name") or len(code) > 64:
                raise ValueError()
        except (ValueError, InvalidOperation):
            skipped += 1
            continue
        product = db.scalar(select(CatalogProduct).where(CatalogProduct.product_code == code))
        if not product:
            product = CatalogProduct(product_code=code, category="Meta catalog")
            db.add(product)
        if product.image_url != row["image_url"]:
            product.owner_approved = False
        product.name = row["name"][:255]
        product.description = row.get("description")
        product.image_url = row["image_url"]
        product.price_inr = int(amount)
        product.available = row.get("availability") in {"in stock", "in_stock", "available for order"}
        imported += 1
    db.commit()
    return {"imported": imported, "skipped": skipped,
        "note": "Skipped unsupported currencies, fractional-rupee prices or incomplete records. Missing remote items are not deleted locally."}


@router.get("/campaigns")
def plans(db: Session = Depends(get_db)):
    return [deployment_view(item) for item in db.scalars(select(CampaignDeployment))]


@router.put("/campaigns/{campaign_id}/plan")
def configure_plan(campaign_id: str, payload: CampaignPlan, db: Session = Depends(get_db)):
    return deployment_view(save_plan(db, campaign_or_404(db, campaign_id), payload))


@router.post("/campaigns/{campaign_id}/prepare")
async def prepare_campaign(campaign_id: str, db: Session = Depends(get_db)):
    campaign = campaign_or_404(db, campaign_id)
    try:
        return deployment_view(await prepare(db, campaign))
    except MetaError as error:
        state = workflow(db, campaign_id)
        if state.creation_status not in {'CREATION_FAILED', 'META_SYNC_ERROR'}:
            state.creation_status = 'API_ERROR'
        state.last_error = str(error)
        db.commit()
        raise


@router.post("/campaigns/{campaign_id}/activate")
async def activate_campaign(campaign_id: str, db: Session = Depends(get_db)):
    return deployment_view(await change_delivery(db, campaign_or_404(db, campaign_id), "activate"))


@router.post("/campaigns/{campaign_id}/pause")
async def pause_campaign(campaign_id: str, db: Session = Depends(get_db)):
    return deployment_view(await change_delivery(db, campaign_or_404(db, campaign_id), "pause"))


@router.post("/campaigns/{campaign_id}/end")
async def end_campaign(campaign_id: str, db: Session = Depends(get_db)):
    return deployment_view(await change_delivery(db, campaign_or_404(db, campaign_id), "end"))


async def collect_campaign(db, deployment, client):
    plan = json.loads(deployment.plan_json)
    today = datetime.now(ZoneInfo(plan["timezone"])).date()
    end = min(today, date.fromisoformat(plan["end_date"]))
    if end < date.fromisoformat(plan["start_date"]):
        return 0
    rows = await client.all_pages(f"{deployment.remote_campaign_id}/insights", {
        "fields": "date_start,spend,reach,impressions,clicks,actions", "time_increment": 1,
        "time_range": {"since": plan["start_date"], "until": end.isoformat()}, "limit": 100})
    for row in rows:
        day = date.fromisoformat(row["date_start"])
        snapshot = db.scalar(select(PerformanceSnapshot).where(
            PerformanceSnapshot.campaign_id == deployment.campaign_id, PerformanceSnapshot.snapshot_date == day,
            PerformanceSnapshot.adset_id.is_(None), PerformanceSnapshot.ad_id.is_(None), PerformanceSnapshot.location.is_(None)))
        if not snapshot:
            snapshot = PerformanceSnapshot(campaign_id=deployment.campaign_id, snapshot_date=day)
            db.add(snapshot)
        for name in ("reach", "impressions", "clicks"):
            setattr(snapshot, name, int(row.get(name, 0)))
        snapshot.spend_inr = float(row.get("spend", 0))
        snapshot.ctr = snapshot.clicks / snapshot.impressions * 100 if snapshot.impressions else None
        snapshot.cpc_inr = snapshot.spend_inr / snapshot.clicks if snapshot.clicks else None
        conversations = next((int(a["value"]) for a in row.get("actions", [])
                              if a["action_type"] == "onsite_conversion.messaging_conversation_started_7d"), None)
        snapshot.conversations = conversations
        snapshot.cost_per_conversation_inr = snapshot.spend_inr / conversations if conversations else None
    db.commit()
    return len(rows)


@router.post("/meta/collect")
async def collect(db: Session = Depends(get_db)):
    outcomes = []
    for deployment in db.scalars(select(CampaignDeployment).where(CampaignDeployment.remote_campaign_id.is_not(None))).all():
        if deployment.operation:
            outcomes.append({"campaign_id": deployment.campaign_id, "error": "Operation pending; collection skipped."})
            continue
        claim(db, deployment, "collect")
        try:
            count = await collect_campaign(db, deployment, MetaClient())
            outcomes.append({"campaign_id": deployment.campaign_id, "days_updated": count})
        except (MetaError, ValueError, KeyError):
            db.rollback()
            outcomes.append({"campaign_id": deployment.campaign_id, "error": "Collection failed; no partial data saved."})
        finally:
            deployment.operation = None
            db.commit()
    return {"campaigns": outcomes}


@router.post("/meta/scheduler")
async def scheduler(db: Session = Depends(get_db)):
    client = MetaClient()
    client.require_writes()
    outcomes = []
    for deployment in db.scalars(select(CampaignDeployment).where(CampaignDeployment.automation_enabled.is_(True))).all():
        campaign = db.get(Campaign, deployment.campaign_id)
        if deployment.operation or campaign.status not in {"ACTIVE", "PAUSED"}:
            continue
        plan = json.loads(deployment.plan_json)
        now = datetime.now(timezone.utc)
        today = now.astimezone(ZoneInfo(plan["timezone"])).date()
        try:
            spent = await client.spend(deployment.remote_campaign_id, plan["start_date"], today.isoformat())
            ended = today > date.fromisoformat(plan["end_date"]) or spent >= plan.get("safety_threshold_inr", plan["weekly_budget_inr"])
            windows = [TimeWindow(time.fromisoformat(w["start"]), time.fromisoformat(w["end"])) for w in plan["windows"]]
            desired = "ENDED" if ended else "ACTIVE" if today >= date.fromisoformat(plan["start_date"]) and is_inside_peak_window(now, windows, plan["timezone"]) else "PAUSED"
            if campaign.status != desired:
                await change_delivery(db, campaign, "end" if ended else "activate" if desired == "ACTIVE" else "pause", client, now, automatic=True)
            outcomes.append({"campaign_id": campaign.id, "status": campaign.status,
                             "spend_inr": str(spent), "budget_warning": spent >= Decimal(plan["weekly_budget_inr"]) * Decimal("0.95")})
        except MetaError as error:
            # Failed spend lookup must never cause resumption. For an active campaign,
            # attempt a pause and disable automatic resumption until owner review.
            if campaign.status == "ACTIVE" and not deployment.operation:
                try:
                    await change_delivery(db, campaign, "pause", client, now)
                except MetaError:
                    pass
            outcomes.append({"campaign_id": campaign.id, "error": str(error)})
    return {"campaigns": outcomes}
