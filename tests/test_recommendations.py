from app.services.recommendations import build_recommendations


def test_recommendations_flag_high_cpc_and_low_ctr_without_budget_change():
    report = build_recommendations(ctr=0.5, cpc_inr=20, conversations=0, cost_per_conversation_inr=None)

    assert any("CPC" in item for item in report.cons)
    assert all("budget" not in item.lower() for item in report.recommendations)
