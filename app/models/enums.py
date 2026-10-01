from enum import Enum


class CampaignStatus(str, Enum):
    DRAFT = "DRAFT"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    READY = "READY"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ENDED = "ENDED"
    ARCHIVED = "ARCHIVED"
    FAILED = "FAILED"


class ApprovalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class LeadStatus(str, Enum):
    LOW = "LOW"
    INTERESTED = "INTERESTED"
    HOT = "HOT"
    VERY_HOT = "VERY_HOT"
