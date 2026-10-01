from app.services.whatsapp_webhook import extract_messages, verify_meta_signature


def test_extracts_text_message_from_cloud_api_payload():
    payload = {"entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": "919043608303", "profile": {"name": "Customer"}}],
        "messages": [{"id": "wamid.1", "from": "919043608303", "type": "text", "text": {"body": "Price please"}}]
    }}]}]}
    messages = extract_messages(payload)

    assert messages[0].message_id == "wamid.1"
    assert messages[0].customer_name == "Customer"


def test_unsigned_webhook_is_allowed_only_without_configured_secret():
    assert verify_meta_signature(b"{}", None, None) is True
    assert verify_meta_signature(b"{}", None, "secret") is False
