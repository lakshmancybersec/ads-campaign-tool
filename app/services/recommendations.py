from dataclasses import dataclass


@dataclass(frozen=True)
class WeeklyRecommendation:
    pros: list[str]
    cons: list[str]
    recommendations: list[str]


def build_recommendations(*, ctr: float | None, cpc_inr: float | None, conversations: int | None,
                          cost_per_conversation_inr: float | None, cpc_benchmark_inr: float = 15.0) -> WeeklyRecommendation:
    pros, cons, recommendations = [], [], []
    if conversations is None:
        cons.append("Conversation data is unavailable or incomplete; enquiry performance cannot be assessed.")
    if cpc_inr is not None and cpc_inr > cpc_benchmark_inr:
        cons.append("CPC is above the configured benchmark.")
        recommendations.append("Review creative relevance and approved audience configuration.")
    elif cpc_inr is not None:
        pros.append("CPC is at or below the configured benchmark.")
    if ctr is not None and ctr < 0.7:
        cons.append("CTR is low; the creative may not be attracting enough interest.")
        recommendations.append("Test another owner-approved creative; do not change targeting automatically.")
    elif ctr is not None:
        pros.append("CTR indicates the creative is attracting interest.")
    if conversations and conversations > 0:
        pros.append("WhatsApp conversation volume is positive.")
    if cost_per_conversation_inr is not None and cost_per_conversation_inr <= 0:
        cons.append("Cost per conversation is not available or invalid.")
    return WeeklyRecommendation(pros, cons, recommendations)
