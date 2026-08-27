/**
 * Generated from frozen FastAPI source OpenAPI (openapi/iam-shell.json).
 *
 * Regenerate / drift-check:
 *   python3 scripts/export_iam_openapi.py
 *   python3 scripts/generate_iam_types.py
 *   python3 scripts/export_iam_openapi.py --check
 *   python3 scripts/generate_iam_types.py --check
 *
 * Do not hand-edit to invent fields. extra=forbid on the backend.
 */

export interface AccessibleFacilitiesResponse {
  facilities: Array<AccessibleFacilityDTO>;
  facility_scope: FacilityScopeKind;
  organization_id: string;
}

export interface AccessibleFacilityDTO {
  code: string;
  facility_type: string;
  id: string;
  name: string;
  status: string;
}

export interface AccessibleOrganizationDTO {
  code: string;
  name: string;
  organization_id: string;
  organization_type: string;
  role_codes: Array<string>;
  status: string;
}

export type FacilityScopeKind = "ALL_IN_ORGANIZATION" | "EXPLICIT";

export interface StaffContextResponse {
  effective_permissions: Array<string>;
  facility_scope: FacilityScopeKind;
  organization: AccessibleOrganizationDTO;
  provisioned: boolean;
  role_codes: Array<string>;
  user: StaffSessionUserDTO;
  work_facility_required: boolean;
}

export interface StaffOrganizationsResponse {
  organizations?: Array<AccessibleOrganizationDTO>;
  provisioned: boolean;
  user?: StaffSessionUserDTO | null;
}

export interface StaffSessionUserDTO {
  display_name: string;
  id: string;
  subject: string;
}
