import json
import re

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response, status
from sqlalchemy import select

from app.config import get_settings
from app import database
from app.models.approval import Approval
from app.api.approvals import OwnerDecision, apply_owner_decision
from app.models.lead import Lead
from app.models.webhook import WebhookEvent
from app.services.lead_scoring import score_lead_message, classify_lead
from app.services.whatsapp_webhook import extract_messages, payload_hash, verify_meta_signature

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.get("/whatsapp")
def verify_whatsapp_webhook(hub_mode: str | None = Query(default=None, alias="hub.mode"),
                            hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
                            hub_challenge: str | None = Query(default=None, alias="hub.challenge")) -> Response:
    settings = get_settings()
    if not settings.whatsapp_app_secret:
        raise HTTPException(status_code=503, detail="Configure WHATSAPP_APP_SECRET before receiving messages.")
    if hub_mode == "subscribe" and settings.whatsapp_verify_token and hub_verify_token == settings.whatsapp_verify_token:
        return Response(content=hub_challenge or "", media_type="text/plain")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Webhook verification failed.")


@router.post("/whatsapp", status_code=status.HTTP_200_OK)
async def receive_whatsapp_webhook(request: Request, x_hub_signature_256: str | None = Header(default=None)) -> dict[str, int]:
    raw_body = await request.body()
    settings = get_settings()
    if not settings.whatsapp_app_secret:
        raise HTTPException(status_code=503, detail="Configure WHATSAPP_APP_SECRET before receiving messages.")
    if not verify_meta_signature(raw_body, x_hub_signature_256, settings.whatsapp_app_secret):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature.")
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid JSON payload.") from error

    processed, duplicates = 0, 0
    if not isinstance(payload, dict) or not isinstance(payload.get("entry", []), list):
        raise HTTPException(status_code=422, detail="Invalid webhook structure.")
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                if settings.whatsapp_phone_number_id and change.get("value", {}).get("metadata", {}).get("phone_number_id") != settings.whatsapp_phone_number_id:
                    raise HTTPException(status_code=403, detail="Unexpected WhatsApp phone number.")
        incoming_messages = extract_messages(payload)
    except (AttributeError, TypeError, KeyError):
        raise HTTPException(status_code=422, detail="Invalid webhook structure.") from None
    with database.SessionLocal() as db:
        for incoming in incoming_messages:
            if db.scalar(select(WebhookEvent.id).where(WebhookEvent.external_event_id == incoming.message_id)):
                duplicates += 1
                continue
            if incoming.sender == settings.owner_whatsapp_number:
                command = re.fullmatch(r"(APPROVE|REJECT)\s+([a-f0-9-]{36})", incoming.message.strip(), re.IGNORECASE)
                result = "OWNER_COMMAND_IGNORED"
                if command:
                    approval = db.get(Approval, command[2].lower())
                    if approval and approval.status == "PENDING":
                        try:
                            decision = f"APPROVE {approval.selected_product_code}" if command[1].upper() == "APPROVE" else "REJECT"
                            apply_owner_decision(approval.id, OwnerDecision(message=decision), db)
                            result = "OWNER_DECISION_RECORDED"
                        except HTTPException:
                            result = "OWNER_DECISION_REJECTED"
                db.add(WebhookEvent(provider="whatsapp", external_event_id=incoming.message_id,
                    payload_hash=payload_hash(payload), processing_status=result))
                db.flush()
                processed += 1
                continue
            score = score_lead_message(incoming.message)
            lead = db.scalar(select(Lead).where(Lead.whatsapp_number == incoming.sender))
            if not lead:
                lead = Lead(whatsapp_number=incoming.sender, customer_name=incoming.customer_name)
                db.add(lead)
            lead.latest_message = incoming.message
            lead.score = max(lead.score or 0, score.score)
            lead.status = classify_lead(lead.score).value
            db.add(WebhookEvent(provider="whatsapp", external_event_id=incoming.message_id, payload_hash=payload_hash(payload),
                                processing_status="PROCESSED"))
            db.flush()
            processed += 1
        db.commit()
    return {"processed": processed, "duplicates": duplicates}
