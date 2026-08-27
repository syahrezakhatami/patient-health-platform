#!/usr/bin/env python3
"""Export IAM shell OpenAPI from the frozen FastAPI source app (not Docker :9100).

    python3 scripts/export_iam_openapi.py
    python3 scripts/export_iam_openapi.py --check
    python3 scripts/generate_iam_types.py
    python3 scripts/generate_iam_types.py --check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from fastapi import FastAPI  # noqa: E402

from app.api.router import build_api_router  # noqa: E402
from app.core.config import Settings  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "openapi" / "iam-shell.json"

SHELL_PATHS = (
    "/api/v1/iam/me/organizations",
    "/api/v1/iam/me/context",
    "/api/v1/organizations/{organization_id}/facilities/accessible",
    "/api/v1/mpi/patients/lookup",
    "/api/v1/clinical/patients/{patient_identity_id}/chart",
    "/api/v1/clinical/patients/{patient_identity_id}/chart/summary",
    "/api/v1/clinical/patients/{patient_identity_id}/chart/timeline",
    "/api/v1/clinical/patients/{patient_identity_id}/chart/sections/{section}",
)


def build_document() -> dict:
    settings = Settings(app_env="test")
    app = FastAPI(title="PHP IAM shell (Healthcare Web subset)", version="iam-shell-context-frozen")
    app.include_router(build_api_router(settings))
    full = app.openapi()
    paths = {}
    missing = [path for path in SHELL_PATHS if path not in full.get("paths", {})]
    if missing:
        raise SystemExit(f"frozen source OpenAPI missing shell paths: {missing}")
    for path in SHELL_PATHS:
        paths[path] = full["paths"][path]
    schemas = full.get("components", {}).get("schemas", {})
    used = {
        "StaffOrganizationsResponse",
        "StaffContextResponse",
        "AccessibleFacilitiesResponse",
        "AccessibleOrganizationDTO",
        "StaffSessionUserDTO",
        "FacilityScopeKind",
        "AccessibleFacilityDTO",
        "PatientLookupRequest",
        "PatientLookupResponse",
        "PatientLookupResult",
        "PatientLookupType",
        "PatientLookupOutcome",
        "IdentityLifecycle",
        "IdentityKind",
        "AdministrativeSex",
        "IdentifierVerificationStatus",
        "ChartShellResponse",
        "ClinicalSummaryResponse",
        "TimelinePageResponse",
        "SectionPageResponse",
        "PatientHeaderDTO",
        "SelectedEncounterDTO",
        "SummaryItemDTO",
        "TimelineItemDTO",
        "ChartSection",
    }
    missing_schemas = sorted(name for name in used if name not in schemas)
    if missing_schemas:
        raise SystemExit(f"frozen source OpenAPI missing schemas: {missing_schemas}")
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "PHP IAM shell (Healthcare Web subset)",
            "version": "iam-shell-context-frozen",
            "description": "Generated from frozen FastAPI source, not live Docker OpenAPI.",
        },
        "paths": paths,
        "components": {"schemas": {name: schemas[name] for name in used}},
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    document = build_document()
    serialized = json.dumps(document, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not OUT.exists() or OUT.read_text() != serialized:
            raise SystemExit(f"OpenAPI drift: {OUT} does not match frozen FastAPI source")
        print(f"ok {OUT}")
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(serialized)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
