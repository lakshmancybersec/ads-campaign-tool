from app.models.enums import ApprovalStatus, CampaignStatus, PaymentStatus


def test_safety_related_default_states_exist():
    assert CampaignStatus.DRAFT.value == "DRAFT"
    assert ApprovalStatus.PENDING.value == "PENDING"
    assert PaymentStatus.CONFIRMED.value == "CONFIRMED"
