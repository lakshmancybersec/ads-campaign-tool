import json
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select, update

from app.config import get_settings
from app.models.approval import Approval
from app.models.catalog import CatalogProduct
from app.models.deployment import CampaignDeployment
from app.models.payment import Payment
from app.models.scheduling import CampaignStatusLog
from app.services.meta_client import MetaClient, MetaError
from app.services.scheduler import TimeWindow, is_inside_peak_window


class Location(BaseModel):
    key: str = Field(pattern=r"^\d+$")
    name: str = Field(min_length=1, max_length=150)
    type: str = Field(pattern=r"^(city|region)$")


class Window(BaseModel):
    start: time
    end: time

    @model_validator(mode="after")
    def validate_window(self):
        if self.start == self.end or self.start.tzinfo or self.end.tzinfo:
            raise ValueError("Use distinct local start and end times.")
        return self


class CampaignPlan(BaseModel):
    product_code: str = Field(min_length=1, max_length=64)
    caption: str = Field(min_length=1, max_length=2000)
    start_date: date
    end_date: date
    age_min: int = Field(default=20, ge=18, le=65)
    age_max: int = Field(default=60, ge=18, le=65)
    locations: list[Location] = Field(min_length=1, max_length=10)
    windows: list[Window] = Field(min_length=1, max_length=6)

    @model_validator(mode="after")
    def valid_range(self):
        if self.age_min > self.age_max:
            raise ValueError("Minimum age must not exceed maximum age.")
        if not 0 <= (self.end_date - self.start_date).days <= 6:
            raise ValueError("Choose a campaign duration of one to seven days.")
        return self


def save_plan(db, campaign, payload):
    from app.services.meta_workflow import enforce_limits
    enforce_limits({'daily_budget_inr': campaign.daily_budget_inr, 'weekly_budget_inr': campaign.weekly_budget_limit_inr,
                    'budget_mode':campaign.budget_mode, 'daily_budget_min_inr':campaign.daily_budget_min_inr})
    if campaign.status != "DRAFT":
        raise MetaError("Only draft campaigns can be edited. Reject a pending approval first, or create a new campaign.")
    deployment = db.get(CampaignDeployment, campaign.id)
    if deployment and (deployment.operation or deployment.remote_campaign_id):
        raise MetaError("A remotely prepared campaign cannot be edited locally.")
    product = db.scalar(select(CatalogProduct).where(CatalogProduct.product_code == payload.product_code))
    if not product or not product.available:
        raise MetaError("Select an available catalog product.")
    s = get_settings()
    if not (s.facebook_page_id or "").isdigit() or not (s.customer_whatsapp_number or "").isdigit():
        raise MetaError("Configure FACEBOOK_PAGE_ID and CUSTOMER_WHATSAPP_NUMBER before preparing a live campaign.")
    if payload.start_date < datetime.now(ZoneInfo(s.timezone)).date():
        raise MetaError("The start date cannot be in the past.")
    plan = payload.model_dump(mode="json")
    plan.update(product_name=product.name, image_url=product.image_url,
                budget_mode=campaign.budget_mode, daily_budget_min_inr=campaign.daily_budget_min_inr,
                daily_budget_inr=campaign.daily_budget_inr, weekly_budget_inr=campaign.weekly_budget_limit_inr,
                safety_threshold_inr=max(1, campaign.weekly_budget_limit_inr * s.weekly_budget_safety_percent // 100),
                page_id=s.facebook_page_id, instagram_actor_id=s.instagram_actor_id,
                whatsapp_number=s.customer_whatsapp_number, timezone=s.timezone,
                objective="OUTCOME_TRAFFIC", optimization_goal="LINK_CLICKS",
                destination=f"https://wa.me/{s.customer_whatsapp_number}")
    # This first adapter uses an ordinary WhatsApp link, not conversation optimization.
    encoded = json.dumps(plan, sort_keys=True)
    if not deployment:
        deployment = CampaignDeployment(campaign_id=campaign.id, plan_json=encoded)
        db.add(deployment)
    else:
        deployment.plan_json = encoded
        deployment.approval_id = None
    db.commit()
    return deployment


def approved_plan(db, campaign, deployment):
    if not deployment:
        raise MetaError("Save campaign targeting, caption and schedule before requesting approval.")
    approval = db.get(Approval, deployment.approval_id) if deployment.approval_id else None
    plan = json.loads(deployment.plan_json)
    if not approval or approval.status != "APPROVED" or approval.campaign_id != campaign.id or approval.selected_product_code != plan["product_code"]:
        raise MetaError("The exact campaign plan must have owner approval.")
    product = db.scalar(select(CatalogProduct).where(CatalogProduct.product_code == plan["product_code"]))
    if not product or not product.available or product.image_url != plan["image_url"]:
        raise MetaError("The approved product is unavailable or its photo changed. Create a new campaign approval.")
    if campaign.daily_budget_inr != plan["daily_budget_inr"] or campaign.weekly_budget_limit_inr != plan["weekly_budget_inr"]:
        raise MetaError("Campaign budgets changed after review.")
    if campaign.budget_mode != plan.get('budget_mode', 'FIXED') or campaign.daily_budget_min_inr != plan.get('daily_budget_min_inr', plan['daily_budget_inr']):
        raise MetaError('Budget mode or approved range changed after review.')
    return plan


def claim(db, deployment, name, automatic=False):
    statement = update(CampaignDeployment).where(
        CampaignDeployment.campaign_id == deployment.campaign_id,
        CampaignDeployment.operation.is_(None))
    if automatic:
        statement = statement.where(CampaignDeployment.automation_enabled.is_(True))
    result = db.execute(statement.values(operation=name, last_error=None))
    if result.rowcount != 1:
        db.rollback()
        raise MetaError("Another operation is running, or an interrupted write needs reconciliation in Ads Manager.")
    db.commit()
    db.refresh(deployment)


def log_status(db, campaign, target, reason):
    if campaign.status != target:
        db.add(CampaignStatusLog(campaign_id=campaign.id, previous_status=campaign.status,
            new_status=target, reason=reason, actor="owner-or-scheduler"))
        campaign.status = target


async def prepare(db, campaign, client=None):
    from app.services.meta_workflow import workflow, verify_objects, enforce_limits
    client = client or MetaClient()
    client.require_writes(preparation=True)
    deployment = db.get(CampaignDeployment, campaign.id)
    plan = approved_plan(db, campaign, deployment)
    enforce_limits(plan)
    state = workflow(db, campaign.id)
    if state.ad_account_id and state.ad_account_id != client.account:
        raise MetaError('Configured ad account changed; do not retry this campaign in another account.')
    if campaign.status not in {"READY", "FAILED"}:
        raise MetaError("Only READY campaigns can be prepared on Meta.")
    await client.validate_account()
    if datetime.now(ZoneInfo(plan["timezone"])).date() > date.fromisoformat(plan["end_date"]):
        raise MetaError("This campaign schedule has ended.")
    claim(db, deployment, "prepare")
    state.ad_account_id = client.account
    state.creation_status = 'CREATING_META_OBJECTS'
    state.verified = False
    state.retry_safe = False
    state.last_error = None
    state.owner_status = 'AWAITING_OWNER_APPROVAL'
    db.commit()
    geo = {"regions": [], "cities": []}
    for location in plan["locations"]:
        geo["regions" if location["type"] == "region" else "cities"].append({"key": location["key"]})
    targeting = {"age_min": plan["age_min"], "age_max": plan["age_max"],
                 "targeting_automation": {"advantage_audience": 0},
                 "geo_locations": {k: v for k, v in geo.items() if v},
                 "publisher_platforms": ["facebook", "instagram"] if plan.get("instagram_actor_id") else ["facebook"]}
    zone = ZoneInfo(plan["timezone"])
    start = datetime.combine(date.fromisoformat(plan["start_date"]), time.min, zone)
    end = datetime.combine(date.fromisoformat(plan["end_date"]) + timedelta(days=1), time.min, zone)
    async def create(field, edge, params):
        if getattr(deployment, field):
            return getattr(deployment, field)
        deployment.operation = f"create:{edge}"
        db.commit()
        response = await client.request("POST", f"{client.account}/{edge}", params)
        identifier = str(response.get("id", ""))
        if not identifier.isdigit():
            raise MetaError("Meta did not return an object ID. Reconcile the operation in Ads Manager.")
        setattr(deployment, field, identifier)
        if field == "remote_campaign_id":
            campaign.meta_campaign_id = identifier
        db.commit()
        return identifier
    try:
        # When the entire budget fits within one day's allowance, a lifetime
        # budget enforces both limits without Meta's larger campaign-cap minimum.
        lifetime_only = plan["weekly_budget_inr"] <= plan["daily_budget_inr"]
        campaign_id = await create("remote_campaign_id", "campaigns", {
            "name": campaign.name, "objective": plan["objective"], "status": "PAUSED",
            "special_ad_categories": [], "buying_type": "AUCTION",
            "is_adset_budget_sharing_enabled": False})
        adset_id = await create("remote_adset_id", "adsets", {
            "name": f"{campaign.name} audience", "campaign_id": campaign_id,
            "lifetime_budget": plan["weekly_budget_inr"] * 100,
            **({} if lifetime_only else {"daily_spend_cap": plan["daily_budget_inr"] * 100}), "billing_event": "IMPRESSIONS",
            "optimization_goal": "LINK_CLICKS", "bid_strategy": "LOWEST_COST_WITHOUT_CAP",
            "destination_type": "WEBSITE", "targeting": targeting, "status": "PAUSED",
            "start_time": max(start, datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
            "end_time": end.isoformat()})
        story = {"page_id": plan["page_id"], "link_data": {
            "link": plan["destination"], "picture": plan["image_url"], "message": plan["caption"],
            "name": plan["product_name"], "call_to_action": {"type": "LEARN_MORE", "value": {"link": plan["destination"]}}}}
        if plan.get("instagram_actor_id"):
            story["instagram_user_id"] = plan["instagram_actor_id"]
        creative_id = await create("remote_creative_id", "adcreatives", {
            "name": f"{campaign.name} approved creative", "object_story_spec": story})
        await create("remote_ad_id", "ads", {"name": campaign.name, "adset_id": adset_id,
            "creative": {"creative_id": creative_id}, "status": "PAUSED"})
        deployment.operation = None
        deployment.last_error = None
        db.commit()
        await verify_objects(db, campaign, client)
        campaign.status = 'READY'
        db.commit()
    except MetaError as error:
        deployment.last_error = str(error)
        state.creation_status = 'CREATION_FAILED' if deployment.operation else 'META_SYNC_ERROR'
        state.last_error = str(error)
        state.verified = False
        state.retry_safe = bool(error.definitive and (deployment.operation or '').startswith('create:'))
        campaign.status = 'FAILED'
        if state.retry_safe:
            deployment.operation = None
        # Keep checkpoint locked, including uncertain transport failures. No blind retry.
        db.commit()
        raise
    return deployment


async def change_delivery(db, campaign, action, client=None, now=None, automatic=False):
    client = client or MetaClient()
    client.require_writes()
    deployment = db.get(CampaignDeployment, campaign.id)
    if not deployment or not deployment.remote_campaign_id:
        raise MetaError("Prepare the campaign on Meta first.")
    if campaign.status == "ENDED":
        raise MetaError("Ended campaigns cannot be restarted. Create a new campaign for a new advertising period.")
    moment = now or datetime.now(timezone.utc)
    if action == "activate":
        from app.services.meta_workflow import workflow, verify_objects
        state = workflow(db, campaign.id)
        if state.owner_status != 'APPROVED':
            raise MetaError('Re-check Meta and confirm owner launch approval after reviewing billing in Meta.')
        await verify_objects(db, campaign, client)
        if state.remote_ad_status in {'PENDING_BILLING_INFO', 'DISAPPROVED', 'WITH_ISSUES'}:
            raise MetaError('Meta reports an ad delivery or billing issue. Resolve it before activation.')
        if not get_settings().scheduler_enabled:
            raise MetaError("Enable the application scheduler before activating a campaign.")
        plan = approved_plan(db, campaign, deployment)
        if campaign.status not in {"READY", "PAUSED", "ACTIVE"} or not deployment.remote_ad_id:
            raise MetaError("The campaign is not ready for activation.")
        local_day = moment.astimezone(ZoneInfo(plan["timezone"])).date()
        if not date.fromisoformat(plan["start_date"]) <= local_day <= date.fromisoformat(plan["end_date"]):
            raise MetaError("Activation is outside the approved campaign dates.")
        windows = [TimeWindow(time.fromisoformat(w["start"]), time.fromisoformat(w["end"])) for w in plan["windows"]]
        if not is_inside_peak_window(moment, windows, plan["timezone"]):
            raise MetaError("Activation is outside the approved peak hours.")
        await client.validate_account()
        remote = await client.request("GET", deployment.remote_campaign_id, {"fields": "account_id,spend_cap"})
        adset = await client.request("GET", deployment.remote_adset_id, {"fields": "campaign_id,daily_budget,lifetime_budget,daily_spend_cap,end_time"})
        lifetime_only = plan["weekly_budget_inr"] <= plan["daily_budget_inr"]
        budget_matches = (str(adset.get("lifetime_budget")) == str(plan["weekly_budget_inr"] * 100)
                          and str(adset.get("daily_budget", "0")) == "0"
                          and (lifetime_only or str(adset.get('daily_spend_cap')) == str(plan['daily_budget_inr'] * 100)))
        if (str(remote.get("account_id")) != client.account.removeprefix("act_")
                or not budget_matches
                or str(adset.get("campaign_id")) != deployment.remote_campaign_id):
            raise MetaError("Remote account or budget differs from the approved plan. Review Ads Manager before activation.")
        expected_end = datetime.combine(date.fromisoformat(plan["end_date"]) + timedelta(days=1), time.min, ZoneInfo(plan["timezone"]))
        try:
            remote_end = datetime.fromisoformat(adset.get("end_time", ""))
        except ValueError:
            raise MetaError("Meta campaign end time could not be verified.") from None
        if remote_end != expected_end:
            raise MetaError("Remote end time differs from the approved schedule.")
        spend = await client.spend(deployment.remote_campaign_id, plan["start_date"], local_day.isoformat())
        if spend >= plan.get("safety_threshold_inr", plan["weekly_budget_inr"]):
            raise MetaError("The approved campaign spend limit has been reached.")
        if campaign.status == "ACTIVE":
            return deployment
    claim(db, deployment, action, automatic=automatic)
    try:
        if action == "activate":
            # Parent is activated last; failures before that leave delivery blocked.
            for identifier in (deployment.remote_adset_id, deployment.remote_ad_id, deployment.remote_campaign_id):
                result = await client.request("POST", identifier, {"status": "ACTIVE"})
                if result.get("success") is not True:
                    raise MetaError("Meta did not confirm the status change; reconcile in Ads Manager.")
            deployment.automation_enabled = True
            log_status(db, campaign, "ACTIVE", "Owner-approved activation within dates, peak hours and spend limit.")
        else:
            result = await client.request("POST", deployment.remote_campaign_id, {"status": "PAUSED"})
            if result.get("success") is not True:
                raise MetaError("Meta did not confirm pausing; check Ads Manager immediately.")
            deployment.automation_enabled = automatic and action != "end"
            log_status(db, campaign, "ENDED" if action == "end" else "PAUSED", "Owner requested " + action)
        deployment.operation = None
        deployment.last_error = None
        db.commit()
    except MetaError as error:
        deployment.last_error = str(error)
        db.commit()
        raise
    return deployment
