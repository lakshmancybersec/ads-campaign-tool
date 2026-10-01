from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.models.enums import CampaignStatus


@dataclass(frozen=True)
class TimeWindow:
    start: time
    end: time
    enabled: bool = True


def is_inside_peak_window(moment: datetime, windows: Iterable[TimeWindow], timezone: str = "Asia/Kolkata") -> bool:
    """Evaluate windows in business timezone, including overnight windows."""
    local_time = moment.astimezone(ZoneInfo(timezone)).time().replace(tzinfo=None)
    for window in windows:
        if not window.enabled:
            continue
        if window.start <= window.end and window.start <= local_time < window.end:
            return True
        if window.start > window.end and (local_time >= window.start or local_time < window.end):
            return True
    return False


def desired_campaign_status(moment: datetime, windows: Iterable[TimeWindow], timezone: str = "Asia/Kolkata") -> CampaignStatus:
    return CampaignStatus.ACTIVE if is_inside_peak_window(moment, windows, timezone) else CampaignStatus.PAUSED


@dataclass(frozen=True)
class SchedulerDecision:
    should_change: bool
    target_status: CampaignStatus
    reason: str


def decide_peak_time_transition(current: CampaignStatus, moment: datetime, windows: Iterable[TimeWindow],
                                timezone: str = "Asia/Kolkata") -> SchedulerDecision:
    target = desired_campaign_status(moment, windows, timezone)
    if current not in {CampaignStatus.ACTIVE, CampaignStatus.PAUSED}:
        return SchedulerDecision(False, current, "Campaign is not scheduler-manageable in its current lifecycle state.")
    if current is target:
        return SchedulerDecision(False, target, "Campaign already has the required peak-time status.")
    reason = "Inside configured peak-time window." if target is CampaignStatus.ACTIVE else "Outside configured peak-time windows."
    return SchedulerDecision(True, target, reason)
