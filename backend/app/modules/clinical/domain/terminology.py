from dataclasses import dataclass

from app.core.errors import AppError


@dataclass(frozen=True, slots=True)
class CodeableConcept:
    """Wave 2A terminology stub. Not a terminology server and not a FHIR ValueSet."""

    system: str
    code: str
    display: str | None = None

    def as_stored(self) -> dict[str, str]:
        stored = {"system": self.system, "code": self.code}
        if self.display:
            stored["display"] = self.display
        return stored


def parse_codeable_concept(payload: dict[str, str | None] | None) -> CodeableConcept | None:
    if payload is None:
        return None
    system = (payload.get("system") or "").strip()
    code = (payload.get("code") or "").strip()
    display = (payload.get("display") or "").strip() or None
    if not system and not code and display is None:
        return None
    if not system or not code:
        raise AppError(
            "invalid_codeable_concept",
            "Codeable concept requires system and code",
            status_code=422,
        )
    if len(system) > 128 or len(code) > 64:
        raise AppError(
            "invalid_codeable_concept",
            "Codeable concept system or code is too long",
            status_code=422,
        )
    if display is not None and len(display) > 255:
        raise AppError(
            "invalid_codeable_concept",
            "Codeable concept display is too long",
            status_code=422,
        )
    return CodeableConcept(system=system, code=code, display=display)
