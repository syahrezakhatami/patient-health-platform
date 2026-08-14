from app.modules.clinical.domain.enums import LaboratoryResultValueType, ObservationValueType
from app.modules.clinical.domain.observation_values import (
    ObservationValue,
    observation_values_equal,
    parse_observation_value,
)

LaboratoryResultValue = ObservationValue
laboratory_result_values_equal = observation_values_equal


def parse_laboratory_result_value(
    *,
    value_type: LaboratoryResultValueType,
    value_numeric: object | None,
    value_text: str | None,
    value_boolean: bool | None,
    value_coded: dict[str, str | None] | None,
    unit: str | None,
    range_low: object | None,
    range_high: object | None,
) -> LaboratoryResultValue:
    return parse_observation_value(
        value_type=ObservationValueType(value_type.value),
        value_numeric=value_numeric,
        value_text=value_text,
        value_boolean=value_boolean,
        value_coded=value_coded,
        unit=unit,
        range_low=range_low,
        range_high=range_high,
    )
