from datetime import datetime, time, timezone

from app.models.enums import CampaignStatus
from app.services.scheduler import TimeWindow, decide_peak_time_transition, is_inside_peak_window


WINDOWS = [TimeWindow(time(7), time(9)), TimeWindow(time(12), time(14)), TimeWindow(time(18), time(22))]


def test_peak_window_uses_asia_kolkata_timezone():
    # 01:45 UTC is 07:15 in Asia/Kolkata.
    moment = datetime(2026, 9, 13, 1, 45, tzinfo=timezone.utc)
    assert is_inside_peak_window(moment, WINDOWS) is True


def test_scheduler_avoids_unnecessary_status_change():
    moment = datetime(2026, 9, 13, 1, 45, tzinfo=timezone.utc)
    decision = decide_peak_time_transition(CampaignStatus.ACTIVE, moment, WINDOWS)

    assert decision.should_change is False


def test_scheduler_pauses_outside_peak_windows():
    moment = datetime(2026, 9, 13, 5, 0, tzinfo=timezone.utc)  # 10:30 IST
    decision = decide_peak_time_transition(CampaignStatus.ACTIVE, moment, WINDOWS)

    assert decision.should_change is True
    assert decision.target_status is CampaignStatus.PAUSED
