import pytest

from app.services.approval import parse_owner_approval


def test_parse_approved_catalog_command():
    command = parse_owner_approval("APPROVE CAT-004")

    assert command.approved is True
    assert command.product_code == "CAT-004"


def test_parse_change_photo_command():
    assert parse_owner_approval("CHANGE PHOTO").approved is False


def test_reject_invalid_approval_command():
    with pytest.raises(ValueError):
        parse_owner_approval("yes please")
