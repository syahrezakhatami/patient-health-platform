from datetime import UTC, date, datetime
from json import dumps
from uuid import uuid4

import pytest
from app.core.errors import AppError, NotFoundError
from app.modules.authorization.domain.catalog import Permission
from app.modules.clinical_read.application.schemas import NoteListDTO, PatientHeaderDTO
from app.modules.clinical_read.domain.age import age_years
from app.modules.clinical_read.domain.catalog import (
    SECTION_PERMISSIONS,
    TIMESTAMP_MAP,
    actor_can_read_section,
    authorized_sections,
    occurred_at_value,
    parse_section,
    section_authorize_action,
    validate_section_filters,
)
from app.modules.clinical_read.domain.cursor import (
    ChartCursor,
    decode_cursor,
    encode_cursor,
    parse_limit,
)
from app.modules.clinical_read.domain.enums import ChartSection, TimelineSourceType
from app.modules.clinical_read.domain.timeline import comes_after_cursor, sort_timeline_rows
from app.modules.clinical_read.infrastructure.queries import _unique

pytestmark = pytest.mark.unit


def test_section_catalog_is_closed_and_mapped() -> None:
    assert len(ChartSection) == 13
    assert set(SECTION_PERMISSIONS) == set(ChartSection)
    assert parse_section("conditions") is ChartSection.CONDITIONS
    with pytest.raises(NotFoundError):
        parse_section("vitals")
    with pytest.raises(NotFoundError):
        parse_section("patient_histories")


def test_section_permission_mapping() -> None:
    scopes = frozenset({Permission.MPI_IDENTITY_READ, Permission.CLINICAL_ENCOUNTER_READ})
    assert actor_can_read_section(scopes, ChartSection.ENCOUNTERS)
    assert not actor_can_read_section(scopes, ChartSection.CONDITIONS)
    assert authorized_sections(scopes) == (ChartSection.ENCOUNTERS,)
    lab_scopes = frozenset({Permission.CLINICAL_LAB_RESULT_READ})
    assert actor_can_read_section(lab_scopes, ChartSection.LABORATORY)
    assert section_authorize_action(lab_scopes, ChartSection.LABORATORY) == (
        Permission.CLINICAL_LAB_RESULT_READ
    )
    assert section_authorize_action(frozenset(), ChartSection.LABORATORY) == (
        Permission.CLINICAL_LAB_ORDER_READ
    )


def test_age_years_birthday_boundaries() -> None:
    birth = date(2000, 8, 26)
    assert age_years(birth, date(2000, 8, 26)) == 0
    assert age_years(birth, date(2001, 8, 25)) == 0
    assert age_years(birth, date(2001, 8, 26)) == 1
    assert age_years(date(2004, 2, 29), date(2005, 2, 28)) == 0
    assert age_years(date(2004, 2, 29), date(2005, 3, 1)) == 1
    assert age_years(date(2030, 1, 1), date(2026, 8, 26)) == -4


def test_cursor_round_trip_and_invalid() -> None:
    cursor = ChartCursor(
        occurred_at=datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
        source_type="condition",
        source_id=uuid4(),
    )
    encoded = encode_cursor(cursor)
    decoded = decode_cursor(encoded)
    assert decoded.source_type == cursor.source_type
    assert decoded.source_id == cursor.source_id
    assert decoded.occurred_at == cursor.occurred_at
    with pytest.raises(AppError) as invalid:
        decode_cursor("not-a-cursor")
    assert invalid.value.code == "invalid_cursor"
    assert invalid.value.status_code == 422
    assert parse_limit(None) == 50
    assert parse_limit(100) == 100
    with pytest.raises(AppError) as too_big:
        parse_limit(101)
    assert too_big.value.status_code == 422


def test_cursor_rejects_extra_fields_and_unknown_source_type() -> None:
    from base64 import urlsafe_b64encode

    cursor = ChartCursor(
        occurred_at=datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
        source_type="condition",
        source_id=uuid4(),
    )
    extra = {
        "t": cursor.occurred_at.isoformat(),
        "k": cursor.source_type,
        "id": str(cursor.source_id),
        "org": str(uuid4()),
    }
    encoded_extra = urlsafe_b64encode(
        dumps(extra, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).decode("ascii")
    with pytest.raises(AppError) as extra_error:
        decode_cursor(encoded_extra)
    assert extra_error.value.code == "invalid_cursor"
    unknown_type = {
        "t": cursor.occurred_at.isoformat(),
        "k": "vitals",
        "id": str(cursor.source_id),
    }
    encoded_unknown = urlsafe_b64encode(
        dumps(unknown_type, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).decode("ascii")
    with pytest.raises(AppError) as unknown_error:
        decode_cursor(encoded_unknown)
    assert unknown_error.value.status_code == 422


def test_section_filters_require_closed_domain_enums() -> None:
    scopes = frozenset({Permission.CLINICAL_CONDITION_READ})
    validate_section_filters(
        ChartSection.CONDITIONS, status="ACTIVE", category="PROBLEM_LIST_ITEM", scopes=scopes
    )
    with pytest.raises(AppError) as bad_status:
        validate_section_filters(
            ChartSection.CONDITIONS, status="NOPE", category=None, scopes=scopes
        )
    assert bad_status.value.code == "invalid_status"
    assert bad_status.value.status_code == 422
    with pytest.raises(AppError) as bad_category:
        validate_section_filters(
            ChartSection.OBSERVATIONS, status=None, category="LAB", scopes=scopes
        )
    assert bad_category.value.code == "invalid_category"
    with pytest.raises(AppError):
        validate_section_filters(
            ChartSection.NOTES, status=None, category="PROGRESS", scopes=scopes
        )
    lab_result = frozenset({Permission.CLINICAL_LAB_RESULT_READ})
    validate_section_filters(
        ChartSection.LABORATORY, status="FINAL", category=None, scopes=lab_result
    )
    with pytest.raises(AppError):
        validate_section_filters(
            ChartSection.LABORATORY, status="REGISTERED", category=None, scopes=lab_result
        )


def test_timeline_ordering_and_cursor_bound() -> None:
    t1 = datetime(2026, 1, 1, tzinfo=UTC)
    t2 = datetime(2026, 2, 1, tzinfo=UTC)
    id_a = uuid4()
    id_b = uuid4()
    id_c = uuid4()
    rows = [
        (t1, TimelineSourceType.CONDITION, id_a, "a"),
        (t2, TimelineSourceType.ALLERGY, id_b, "b"),
        (t2, TimelineSourceType.CONDITION, id_c, "c"),
    ]
    ordered = sort_timeline_rows(rows)
    assert [item[3] for item in ordered][0] in {"b", "c"}
    assert ordered[0][0] == t2
    if ordered[0][1] is TimelineSourceType.ALLERGY:
        assert ordered[1][1] is TimelineSourceType.CONDITION
    cursor = ChartCursor(occurred_at=t2, source_type="condition", source_id=id_c)
    assert comes_after_cursor(t1, "condition", id_a, cursor)
    assert not comes_after_cursor(t2, "allergy", id_b, cursor)


def test_timestamp_map_covers_every_source() -> None:
    assert set(TIMESTAMP_MAP) == set(TimelineSourceType)
    assert TIMESTAMP_MAP[TimelineSourceType.ENCOUNTER].fallback is None
    assert TIMESTAMP_MAP[TimelineSourceType.CONDITION].primary == "onset_at"
    assert TIMESTAMP_MAP[TimelineSourceType.CONDITION].fallback == "recorded_at"


def test_timestamp_fallback() -> None:
    primary = datetime(2026, 1, 1, tzinfo=UTC)
    fallback = datetime(2026, 2, 1, tzinfo=UTC)
    assert occurred_at_value(None, fallback) == fallback
    assert occurred_at_value(primary, fallback) == primary


def test_read_dto_projection_and_header_omission() -> None:
    assert "body_text" not in NoteListDTO.model_fields
    header = PatientHeaderDTO(
        requested_patient_identity_id=uuid4(),
        canonical_patient_identity_id=uuid4(),
        lifecycle_status="ACTIVE",
        identity_kind="PERSON",
        display_label="Test Patient",
        given_name="Test",
        family_name="Patient",
        birth_date=date(1990, 1, 1),
        age_years=36,
        administrative_sex=None,
        mrn=["MRN-1"],
        selected_encounter=None,
        documented_allergy_exists=None,
    )
    dumped = header.model_dump()
    assert "documented_allergy_exists" not in dumped
    assert "selected_encounter" not in dumped
    assert dumped["age_years"] == 36
    authorized = header.model_copy(update={"documented_allergy_exists": False})
    assert authorized.model_dump()["documented_allergy_exists"] is False
    missing_age = header.model_copy(update={"birth_date": None, "age_years": None})
    assert "age_years" in missing_age.model_dump()
    assert missing_age.model_dump()["age_years"] is None


def test_physical_fact_dedupe_by_id_only() -> None:
    class Fact:
        def __init__(self, fact_id: object, code: str) -> None:
            self.id = fact_id
            self.code = code

    first_id = uuid4()
    rows = [Fact(first_id, "A"), Fact(first_id, "B"), Fact(uuid4(), "C")]
    unique = _unique(rows)
    assert len(unique) == 2
    assert {item.id for item in unique} == {rows[0].id, rows[2].id}


def test_unauthorized_section_omission() -> None:
    registrar = frozenset(
        {
            Permission.MPI_IDENTITY_READ,
            Permission.CLINICAL_ENCOUNTER_READ,
        }
    )
    officer = frozenset({Permission.MPI_IDENTITY_READ})
    assert ChartSection.CONDITIONS not in authorized_sections(registrar)
    assert authorized_sections(officer) == ()
    clinician = frozenset(Permission)
    assert ChartSection.FAMILY_HISTORIES in authorized_sections(clinician)
