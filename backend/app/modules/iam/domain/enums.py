from enum import StrEnum


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class MembershipStatus(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
