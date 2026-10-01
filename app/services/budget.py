from dataclasses import dataclass


@dataclass(frozen=True)
class BudgetCheck:
    permitted: bool
    should_pause: bool
    threshold_inr: int
    reason: str


class BudgetGuard:
    """Prevents any automated increase and enforces the weekly safety ceiling."""

    def __init__(self, weekly_budget_inr: int, safety_percent: int = 100) -> None:
        if weekly_budget_inr <= 0 or not 1 <= safety_percent <= 100:
            raise ValueError("Budget and safety percentage must be positive and valid.")
        self.weekly_budget_inr = weekly_budget_inr
        self.safety_percent = safety_percent

    @property
    def threshold_inr(self) -> int:
        return self.weekly_budget_inr * self.safety_percent // 100

    def assess(self, weekly_spend_inr: float) -> BudgetCheck:
        if weekly_spend_inr >= self.threshold_inr:
            return BudgetCheck(False, True, self.threshold_inr, "Weekly safety threshold reached.")
        return BudgetCheck(True, False, self.threshold_inr, "Within weekly safety threshold.")

    def validate_requested_daily_budget(self, current_daily_budget_inr: int, requested_daily_budget_inr: int) -> None:
        if requested_daily_budget_inr > current_daily_budget_inr:
            raise PermissionError("Automatic budget increases require explicit owner approval.")
