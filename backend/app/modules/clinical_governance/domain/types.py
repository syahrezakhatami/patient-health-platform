from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ClinicalRuleRef:
    """Placeholder identity for a versioned clinical rule. No persistence in Wave 0."""

    rule_id: UUID
    version: int
    policy_reference: str
