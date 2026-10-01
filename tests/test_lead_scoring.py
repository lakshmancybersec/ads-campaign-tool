from app.models.enums import LeadStatus
from app.services.lead_scoring import score_lead_message


def test_lead_scoring_scores_multiple_real_intent_signals():
    result = score_lead_message("What is the price? Is it available and can you deliver to Hyderabad?", quantity=2)

    assert result.score == 90
    assert result.status is LeadStatus.VERY_HOT
