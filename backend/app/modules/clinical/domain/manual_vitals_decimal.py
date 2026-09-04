from decimal import Decimal, InvalidOperation

from app.core.errors import AppError


def parse_manual_vital_decimal(raw: object, *, field: str = "value") -> Decimal:
    if raw is None:
        raise AppError(
            "invalid_observation_value",
            "Numeric value is required",
            status_code=422,
        )
    try:
        if isinstance(raw, Decimal):
            value = raw
        elif isinstance(raw, bool):
            raise InvalidOperation
        elif isinstance(raw, int):
            value = Decimal(raw)
        elif isinstance(raw, float):
            raise InvalidOperation
        elif isinstance(raw, str):
            stripped = raw.strip()
            if not stripped or "e" in stripped.lower():
                raise InvalidOperation
            value = Decimal(stripped)
        else:
            raise InvalidOperation
    except (InvalidOperation, ValueError):
        raise AppError(
            "invalid_observation_value",
            "Numeric value is not valid",
            status_code=422,
        ) from None
    if not value.is_finite():
        raise AppError(
            "invalid_observation_value",
            "Numeric value is not valid",
            status_code=422,
        )
    sign, digits, exponent = value.as_tuple()
    digit_count = len(digits)
    exponent_value = int(exponent)
    scale = -exponent_value if exponent_value < 0 else 0
    if scale > 4:
        raise AppError(
            "invalid_observation_value",
            "Numeric value exceeds allowed scale",
            status_code=422,
        )
    if digit_count > 14:
        raise AppError(
            "invalid_observation_value",
            "Numeric value exceeds allowed precision",
            status_code=422,
        )
    if exponent_value > 0 and digit_count + exponent_value > 14:
        raise AppError(
            "invalid_observation_value",
            "Numeric value exceeds allowed precision",
            status_code=422,
        )
    return value


def canonical_decimal_fingerprint_text(value: Decimal) -> str:
    normalized = value.normalize()
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text if text else "0"
