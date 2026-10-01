import pytest

from app.models.enums import CampaignStatus
from app.services.campaign import CampaignStateMachine, InvalidCampaignTransition


def test_campaign_needs_approval_and_payment_to_start():
    machine = CampaignStateMachine()

    with pytest.raises(PermissionError):
        machine.transition(CampaignStatus.READY, CampaignStatus.ACTIVE, approval_confirmed=False)

    assert machine.transition(CampaignStatus.READY, CampaignStatus.ACTIVE,
                              approval_confirmed=True, payment_confirmed=True) is CampaignStatus.ACTIVE


def test_ended_campaign_cannot_restart():
    with pytest.raises(InvalidCampaignTransition):
        CampaignStateMachine().transition(CampaignStatus.ENDED, CampaignStatus.ACTIVE)
