from dataclasses import dataclass
from uuid import UUID

from app.core.errors import AppError
from app.modules.mpi.domain.enums import (
    IdentifierType,
    IdentifierVerificationStatus,
    IdentityLifecycle,
)
from app.modules.mpi.domain.identifiers import is_global_identifier
from app.modules.mpi.domain.matching import IdentifierProbe


@dataclass(frozen=True, slots=True)
class MergeValidation:
    source_id: UUID
    target_id: UUID
    source_status: IdentityLifecycle
    target_status: IdentityLifecycle
    source_surviving_id: UUID | None
    target_surviving_id: UUID | None
    source_identifiers: tuple[IdentifierProbe, ...]
    target_identifiers: tuple[IdentifierProbe, ...]


def validate_merge(request: MergeValidation) -> None:
    if request.source_id == request.target_id:
        raise AppError("invalid_merge", "An identity cannot be merged into itself", status_code=409)
    if request.source_status is IdentityLifecycle.RETIRED:
        raise AppError("invalid_merge", "A retired identity cannot be merged", status_code=409)
    if request.target_status is IdentityLifecycle.MERGED:
        raise AppError("invalid_merge", "The target identity is already merged", status_code=409)
    if request.target_status is IdentityLifecycle.RETIRED:
        raise AppError(
            "invalid_merge",
            "A retired identity cannot be a merge target",
            status_code=409,
        )
    if request.source_status is IdentityLifecycle.MERGED:
        if request.source_surviving_id == request.target_id:
            return
        raise AppError("invalid_merge", "The source identity is already merged", status_code=409)
    if request.target_surviving_id == request.source_id:
        raise AppError("invalid_merge", "Merge would create a cycle", status_code=409)
    conflicts = identifier_conflicts(request.source_identifiers, request.target_identifiers)
    if conflicts:
        raise AppError(
            "identifier_conflict",
            "Merge stopped because identifier conflicts exist",
            status_code=409,
            details={"conflicts": ",".join(conflicts)},
        )


def identifier_conflicts(
    source_identifiers: tuple[IdentifierProbe, ...],
    target_identifiers: tuple[IdentifierProbe, ...],
) -> tuple[str, ...]:
    conflicts: list[str] = []
    for left in source_identifiers:
        if left.verification_status in {
            IdentifierVerificationStatus.REJECTED,
            IdentifierVerificationStatus.EXPIRED,
        }:
            continue
        for right in target_identifiers:
            if right.verification_status in {
                IdentifierVerificationStatus.REJECTED,
                IdentifierVerificationStatus.EXPIRED,
            }:
                continue
            if not _same_ownership(left, right):
                continue
            if left.normalized_value != right.normalized_value:
                conflicts.append(f"{left.identifier_system}:{left.identifier_type}")
    return tuple(conflicts)


def _same_ownership(left: IdentifierProbe, right: IdentifierProbe) -> bool:
    if left.identifier_system != right.identifier_system:
        return False
    if left.identifier_type != right.identifier_type:
        return False
    if is_global_identifier(left.identifier_type) or left.identifier_type is IdentifierType.OTHER:
        return True
    return left.organization_id is not None and left.organization_id == right.organization_id


def validate_unmerge(
    source_status: IdentityLifecycle,
    source_surviving_id: UUID | None,
    expected_target_id: UUID,
) -> None:
    if source_status is not IdentityLifecycle.MERGED:
        raise AppError("invalid_unmerge", "Only a merged identity can be unmerged", status_code=409)
    if source_surviving_id != expected_target_id:
        raise AppError(
            "invalid_unmerge",
            "Unmerge target does not match the recorded surviving identity",
            status_code=409,
        )
