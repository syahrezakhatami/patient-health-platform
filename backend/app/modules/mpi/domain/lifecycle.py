from app.core.errors import AppError
from app.modules.mpi.domain.enums import IdentityLifecycle

ALLOWED_TRANSITIONS: dict[IdentityLifecycle, frozenset[IdentityLifecycle]] = {
    IdentityLifecycle.ANONYMOUS: frozenset(
        {
            IdentityLifecycle.ACTIVE,
            IdentityLifecycle.MERGED,
            IdentityLifecycle.RETIRED,
        }
    ),
    IdentityLifecycle.ACTIVE: frozenset(
        {
            IdentityLifecycle.MERGED,
            IdentityLifecycle.RETIRED,
        }
    ),
    IdentityLifecycle.MERGED: frozenset({IdentityLifecycle.ACTIVE}),
    IdentityLifecycle.RETIRED: frozenset(),
}


def assert_transition(current: IdentityLifecycle, target: IdentityLifecycle) -> None:
    if current == target:
        return
    allowed = ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise AppError(
            "invalid_lifecycle_transition",
            f"Identity cannot transition from {current} to {target}",
            status_code=409,
        )


def is_authoritative(status: IdentityLifecycle) -> bool:
    return status in {IdentityLifecycle.ACTIVE, IdentityLifecycle.ANONYMOUS}
