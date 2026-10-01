from app.services.meta_ads import MockMetaAdsService
from app.services.whatsapp import MockWhatsAppService


def test_mock_meta_is_read_only_and_returns_zero_metrics():
    service = MockMetaAdsService()
    insight = service.get_insights("test-campaign")

    assert service.get_campaign_status("test-campaign") == "PAUSED"
    assert insight.spend_inr == 0
    assert insight.clicks == 0


def test_mock_whatsapp_never_sends_an_external_message():
    result = MockWhatsAppService().send_message("919043608303", "Approval required")

    assert result.accepted is True
    assert result.recipient == "919043608303"
