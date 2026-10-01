from collections.abc import Callable

from app.models.enums import CampaignStatus


class InvalidCampaignTransition(ValueError):
    pass


ALLOWED_TRANSITIONS: dict[CampaignStatus, set[CampaignStatus]] = {
    CampaignStatus.DRAFT: {CampaignStatus.PENDING_APPROVAL},
    CampaignStatus.PENDING_APPROVAL: {CampaignStatus.READY, CampaignStatus.DRAFT},
    CampaignStatus.READY: {CampaignStatus.ACTIVE, CampaignStatus.PAUSED, CampaignStatus.ENDED},
    CampaignStatus.ACTIVE: {CampaignStatus.PAUSED, CampaignStatus.ENDED},
    CampaignStatus.PAUSED: {CampaignStatus.ACTIVE, CampaignStatus.ENDED},
    CampaignStatus.ENDED: set(),
    CampaignStatus.ARCHIVED: set(),
}


class CampaignStateMachine:
    """Enforces lifecycle rules before a scheduler or future API changes campaign state."""

    def transition(self, current: CampaignStatus, target: CampaignStatus, *, approval_confirmed: bool = False,
                   payment_confirmed: bool = False) -> CampaignStatus:
        if current == target:
            return current
        if target not in ALLOWED_TRANSITIONS[current]:
            raise InvalidCampaignTransition(f"Cannot transition from {current.value} to {target.value}.")
        if target is CampaignStatus.ACTIVE and not approval_confirmed:
            raise PermissionError("Campaign activation requires owner approval.")
        return target
