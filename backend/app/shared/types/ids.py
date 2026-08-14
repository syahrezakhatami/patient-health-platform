from uuid import UUID, uuid4


def new_id() -> UUID:
    """Platform-generated opaque identifier. Never derived from NIK, MRN, phone, or email."""
    return uuid4()
