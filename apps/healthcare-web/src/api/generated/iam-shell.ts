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

export type AdministrativeSex = "MALE" | "FEMALE" | "OTHER" | "UNKNOWN";

export type ChartSection = "encounters" | "notes" | "conditions" | "observations" | "laboratory" | "medications" | "allergies" | "consents" | "immunizations" | "procedures" | "medical-devices" | "adverse-events" | "family-histories";

export interface ChartShellResponse {
  authorized_sections: Array<ChartSection>;
  canonical_patient_identity_id: string;
  header: PatientHeaderDTO;
  requested_patient_identity_id: string;
}

export interface ClinicalSummaryResponse {
  active_allergies?: Array<SummaryItemDTO> | null;
  active_conditions?: Array<SummaryItemDTO> | null;
  active_medications?: Array<SummaryItemDTO> | null;
  canonical_patient_identity_id: string;
  recent_lab_results?: Array<SummaryItemDTO> | null;
  recent_procedures?: Array<SummaryItemDTO> | null;
  recent_vitals?: Array<SummaryItemDTO> | null;
  requested_patient_identity_id: string;
}

export type FacilityScopeKind = "ALL_IN_ORGANIZATION" | "EXPLICIT";

export type IdentifierVerificationStatus = "UNVERIFIED" | "VERIFIED" | "REJECTED" | "EXPIRED";

export type IdentityKind = "STANDARD" | "ANONYMOUS" | "TEMPORARY";

export type IdentityLifecycle = "ANONYMOUS" | "ACTIVE" | "MERGED" | "RETIRED";

export interface PatientHeaderDTO {
}

export type PatientLookupOutcome = "none" | "one" | "ambiguous" | "review_required";

export interface PatientLookupRequest {
  lookup_type: PatientLookupType;
  lookup_value: string;
}

export interface PatientLookupResponse {
  outcome: PatientLookupOutcome;
  results: Array<PatientLookupResult>;
  truncated: boolean;
}

export interface PatientLookupResult {
  administrative_sex: AdministrativeSex | null;
  birth_date: string | null;
  display_label: string;
  display_name: string;
  identifier_verification: IdentifierVerificationStatus | null;
  identity_kind: IdentityKind;
  lifecycle_status: IdentityLifecycle;
  masked_identifier: string | null;
  organization_mrn: string | null;
  patient_identity_id: string;
  requested_patient_identity_id: string | null;
  resolved_from_merged: boolean;
  review_required: boolean;
  selectable: boolean;
}

export type PatientLookupType = "MRN" | "NIK" | "BPJS" | "PATIENT_IDENTITY_ID";

export interface SectionPageResponse {
  canonical_patient_identity_id: string;
  has_more: boolean;
  items: Array<Record<string, unknown>>;
  next_cursor?: string | null;
  requested_patient_identity_id: string;
  section: ChartSection;
}

export interface SelectedEncounterDTO {
  display_label: string;
  encounter_class: string;
  ended_at: string | null;
  facility_id: string | null;
  id: string;
  started_at: string;
  status: string;
}

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

export interface SummaryItemDTO {
  code?: string | null;
  code_display?: string | null;
  code_system?: string | null;
  occurred_at: string;
  source_id: string;
  source_type: string;
  status: string;
}

export interface TimelineItemDTO {
  canonical_patient_identity_id: string;
  code?: string | null;
  code_display?: string | null;
  code_system?: string | null;
  encounter_id?: string | null;
  facility_id: string | null;
  occurred_at: string;
  organization_id: string;
  source_id: string;
  source_patient_identity_id: string;
  source_type: string;
  status?: string | null;
}

export interface TimelinePageResponse {
  canonical_patient_identity_id: string;
  has_more: boolean;
  items: Array<TimelineItemDTO>;
  next_cursor?: string | null;
  requested_patient_identity_id: string;
}
