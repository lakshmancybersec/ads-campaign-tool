import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IncomingWhatsAppMessage:
    message_id: str
    sender: str
    message: str
    customer_name: str | None


def verify_meta_signature(raw_body: bytes, signature: str | None, app_secret: str | None) -> bool:
    """Validate X-Hub-Signature-256 when the app secret is configured."""
    if not app_secret:
        return True  # Development only; production configuration must set the secret.
    if not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature.removeprefix("sha256="), expected)


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def extract_messages(payload: dict[str, Any]) -> list[IncomingWhatsAppMessage]:
    messages: list[IncomingWhatsAppMessage] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            contacts = {contact.get("wa_id"): contact.get("profile", {}).get("name") for contact in value.get("contacts", [])}
            for message in value.get("messages", []):
                if message.get("type") != "text":
                    continue
                sender = message.get("from")
                message_id = message.get("id")
                text = message.get("text", {}).get("body", "").strip()
                if sender and message_id and text:
                    messages.append(IncomingWhatsAppMessage(message_id, sender, text, contacts.get(sender)))
    return messages
