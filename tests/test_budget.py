import pytest

from app.services.budget import BudgetGuard


def test_weekly_budget_threshold_pauses_campaign():
    result = BudgetGuard(1050).assess(1050)

    assert result.permitted is False
    assert result.should_pause is True
    assert result.threshold_inr == 1050


def test_budget_increase_is_never_automatic():
    with pytest.raises(PermissionError, match="owner approval"):
        BudgetGuard(1050).validate_requested_daily_budget(150, 200)
