from dataclasses import dataclass
import httpx
from urllib.parse import urlparse

from app.config import get_settings
from app.services.meta_client import MetaError, configured


@dataclass(frozen=True)
class MockNotification:
    recipient: str
    message: str
    accepted: bool = True


class MockWhatsAppService:
    """Development-only WhatsApp substitute. Messages are never sent externally."""

    def send_message(self, recipient: str, message: str) -> MockNotification:
        return MockNotification(recipient=recipient, message=message)


class WhatsAppService:
    def __init__(self, transport=None):
        self.transport = transport

    def validate(self):
        s = get_settings()
        required = [s.whatsapp_access_token, s.whatsapp_phone_number_id, s.whatsapp_app_secret,
                    s.owner_whatsapp_number, s.whatsapp_approval_template]
        if not s.whatsapp_notifications_enabled or not all(configured(v) for v in required):
            raise MetaError("Configure WhatsApp credentials, owner number and approved template; then enable WHATSAPP_NOTIFICATIONS_ENABLED.")
        if not (s.whatsapp_phone_number_id or "").isdigit() or not (s.owner_whatsapp_number or "").isdigit():
            raise MetaError("WhatsApp identifiers and owner number must contain digits only.")
        url = urlparse(s.public_dashboard_url or "")
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise MetaError("Configure a public HTTPS dashboard URL without credentials or query parameters.")
        return s

    async def send_approval(self, campaign_name, product_code, approval_id):
        s = self.validate()
        values = [campaign_name, product_code, approval_id, s.public_dashboard_url]
        payload = {"messaging_product": "whatsapp", "to": s.owner_whatsapp_number, "type": "template",
            "template": {"name": s.whatsapp_approval_template, "language": {"code": s.whatsapp_template_language},
                "components": [{"type": "body", "parameters": [{"type": "text", "text": value} for value in values]}]}}
        try:
            async with httpx.AsyncClient(timeout=25, transport=self.transport) as client:
                response = await client.post(f"https://graph.facebook.com/{s.meta_api_version}/{s.whatsapp_phone_number_id}/messages",
                    headers={"Authorization": f"Bearer {s.whatsapp_access_token}"}, json=payload)
            body = response.json()
            if response.is_error:
                raise ValueError()
            return body["messages"][0]["id"]
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            raise MetaError("WhatsApp delivery was not confirmed. Check the template, permissions and delivery logs before resending.") from None
