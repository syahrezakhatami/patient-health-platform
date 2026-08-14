from collections.abc import Callable
from uuid import UUID

from app.modules.mpi.domain.enums import IdentityLifecycle

MAX_SURVIVOR_HOPS = 8


def resolve_canonical_id(
    identity_id: UUID,
    *,
    status_of: Callable[[UUID], IdentityLifecycle | None],
    surviving_of: Callable[[UUID], UUID | None],
) -> UUID | None:
    """Walk MERGED → surviving_identity_id to the authoritative identity.

    Returns None on cycle, missing row, retired identity, or broken link.
    Does not mutate any identity.
    """
    seen: set[UUID] = set()
    current = identity_id
    for _ in range(MAX_SURVIVOR_HOPS):
        if current in seen:
            return None
        seen.add(current)
        status = status_of(current)
        if status is None:
            return None
        if status is IdentityLifecycle.RETIRED:
            return None
        if status is IdentityLifecycle.MERGED:
            nxt = surviving_of(current)
            if nxt is None or nxt == current:
                return None
            current = nxt
            continue
        return current
    return None
