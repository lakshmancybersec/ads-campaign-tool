from dataclasses import dataclass

from app.models.enums import LeadStatus


@dataclass(frozen=True)
class LeadScoreResult:
    score: int
    status: LeadStatus
    reasons: list[str]


DEFAULT_RULES: dict[str, tuple[int, tuple[str, ...]]] = {
    "price_enquiry": (20, ("price", "rate", "cost", "how much", "vilai")),
    "availability": (20, ("available", "availability", "stock", "irukka")),
    "quantity": (20, ("quantity", "pieces", "set", "dozen", "pcs")),
    "city": (15, ("chennai", "bengaluru", "bangalore", "hyderabad", "vijayawada", "visakhapatnam")),
    "delivery": (15, ("delivery", "deliver", "shipping", "courier", "dispatch")),
    "payment": (10, ("payment", "upi", "gpay", "phonepe", "pay")),
}


def classify_lead(score: int) -> LeadStatus:
    if score >= 81:
        return LeadStatus.VERY_HOT
    if score >= 61:
        return LeadStatus.HOT
    if score >= 31:
        return LeadStatus.INTERESTED
    return LeadStatus.LOW


def score_lead_message(message: str, *, city: str | None = None, quantity: int | None = None) -> LeadScoreResult:
    lower = message.lower()
    score, reasons = 0, []
    for name, (points, terms) in DEFAULT_RULES.items():
        found = any(term in lower for term in terms)
        if name == "city" and city:
            found = True
        if name == "quantity" and quantity is not None:
            found = True
        if found:
            score += points
            reasons.append(name)
    score = min(score, 100)
    return LeadScoreResult(score, classify_lead(score), reasons)
