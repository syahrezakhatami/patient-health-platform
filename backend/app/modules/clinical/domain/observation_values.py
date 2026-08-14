from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.core.errors import AppError
from app.modules.clinical.domain.enums import ObservationValueType
from app.modules.clinical.domain.terminology import CodeableConcept, parse_codeable_concept

_MAX_TEXT = 2000
_MAX_UNIT = 32


@dataclass(frozen=True, slots=True)
class ObservationValue:
    value_type: ObservationValueType
    numeric: Decimal | None = None
    text: str | None = None
    boolean: bool | None = None
    coded: CodeableConcept | None = None
    unit: str | None = None
    range_low: Decimal | None = None
    range_high: Decimal | None = None


def parse_decimal(raw: object, *, field: str) -> Decimal:
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise AppError(
            "invalid_observation_value",
            f"Observation {field} must be a number",
            status_code=422,
        ) from exc
    if not value.is_finite():
        raise AppError(
            "invalid_observation_value",
            f"Observation {field} must be a finite number",
            status_code=422,
        )
    return value


def parse_observation_value(
    *,
    value_type: ObservationValueType,
    value_numeric: object | None,
    value_text: str | None,
    value_boolean: bool | None,
    value_coded: dict[str, str | None] | None,
    unit: str | None,
    range_low: object | None,
    range_high: object | None,
) -> ObservationValue:
    numeric = None if value_numeric is None else parse_decimal(value_numeric, field="value_numeric")
    text = None if value_text is None else value_text.strip()
    if text == "":
        text = None
    coded = parse_codeable_concept(value_coded)
    unit_text = None if unit is None else unit.strip()
    if unit_text == "":
        unit_text = None
    low = None if range_low is None else parse_decimal(range_low, field="reference_range_low")
    high = None if range_high is None else parse_decimal(range_high, field="reference_range_high")
    present = {
        "numeric": numeric is not None,
        "text": text is not None,
        "boolean": value_boolean is not None,
        "coded": coded is not None,
    }
    if value_type is ObservationValueType.NUMERIC:
        if numeric is None or present["text"] or present["boolean"] or present["coded"]:
            raise AppError(
                "invalid_observation_value",
                "A numeric observation requires value_numeric only",
                status_code=422,
            )
        if unit_text is None:
            raise AppError(
                "invalid_observation_value",
                "A numeric observation requires a unit",
                status_code=422,
            )
        if len(unit_text) > _MAX_UNIT:
            raise AppError(
                "invalid_observation_value",
                "Observation unit is too long",
                status_code=422,
            )
        if low is not None and high is not None and high < low:
            raise AppError(
                "invalid_observation_value",
                "Observation reference range high cannot precede low",
                status_code=422,
            )
        return ObservationValue(
            value_type=value_type,
            numeric=numeric,
            unit=unit_text,
            range_low=low,
            range_high=high,
        )
    if unit_text is not None or low is not None or high is not None:
        raise AppError(
            "invalid_observation_value",
            "Unit and reference range are only valid for numeric observations",
            status_code=422,
        )
    if value_type is ObservationValueType.TEXT:
        if text is None or present["numeric"] or present["boolean"] or present["coded"]:
            raise AppError(
                "invalid_observation_value",
                "A text observation requires value_text only",
                status_code=422,
            )
        if len(text) > _MAX_TEXT:
            raise AppError(
                "invalid_observation_value",
                "Observation text exceeds 2000 characters",
                status_code=422,
            )
        return ObservationValue(value_type=value_type, text=text)
    if value_type is ObservationValueType.BOOLEAN:
        if value_boolean is None or present["numeric"] or present["text"] or present["coded"]:
            raise AppError(
                "invalid_observation_value",
                "A boolean observation requires value_boolean only",
                status_code=422,
            )
        return ObservationValue(value_type=value_type, boolean=value_boolean)
    if coded is None or present["numeric"] or present["text"] or present["boolean"]:
        raise AppError(
            "invalid_observation_value",
            "A coded observation requires value_coded only",
            status_code=422,
        )
    return ObservationValue(value_type=value_type, coded=coded)


def observation_values_equal(current: ObservationValue, incoming: ObservationValue) -> bool:
    return (
        current.value_type is incoming.value_type
        and current.numeric == incoming.numeric
        and current.text == incoming.text
        and current.boolean == incoming.boolean
        and current.coded == incoming.coded
        and current.unit == incoming.unit
        and current.range_low == incoming.range_low
        and current.range_high == incoming.range_high
    )
