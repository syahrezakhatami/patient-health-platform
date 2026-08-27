import type { PatientHeaderDTO } from "../api/generated/iam-shell";

/**
 * Frozen Clinical Read PatientHeaderDTO runtime shape.
 * OpenAPI collapses this schema because of a custom @model_serializer that omits
 * null documented_allergy_exists and selected_encounter. JSON keys below are the
 * source-of-truth contract. Do not log or stringify the raw payload on failure.
 */
export interface ChartPatientHeader {
  requested_patient_identity_id: string;
  canonical_patient_identity_id: string;
  lifecycle_status: string;
  identity_kind: string;
  display_label: string;
  given_name: string | null;
  family_name: string | null;
  birth_date: string | null;
  age_years: number | null;
  administrative_sex: string | null;
  mrn: string[];
  documentedAllergy: "true" | "false" | "omitted";
}

export const HEADER_CONTRACT_FAILURE = "chart_header_invalid";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
}

function requiredUuid(value: unknown): string | null {
  return typeof value === "string" && UUID_RE.test(value) ? value : null;
}

function requiredString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function optionalString(value: unknown): string | null | undefined {
  if (value === undefined) {
    return undefined;
  }
  if (value === null || typeof value === "string") {
    return value;
  }
  return undefined;
}

function optionalAge(value: unknown): number | null | undefined {
  if (value === undefined) {
    return undefined;
  }
  if (value === null) {
    return null;
  }
  if (typeof value === "number" && Number.isFinite(value) && Number.isInteger(value)) {
    return value;
  }
  return undefined;
}

function parseMrn(value: unknown): string[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  if (!value.every((item) => typeof item === "string")) {
    return null;
  }
  return value;
}

function parseAllergy(data: Record<string, unknown>): ChartPatientHeader["documentedAllergy"] | null {
  if (!("documented_allergy_exists" in data)) {
    return "omitted";
  }
  if (data.documented_allergy_exists === true) {
    return "true";
  }
  if (data.documented_allergy_exists === false) {
    return "false";
  }
  if (data.documented_allergy_exists === null) {
    return "omitted";
  }
  return null;
}

/**
 * Parse the frozen chart-shell header. Returns null on contract drift.
 * Never includes the raw payload in the result or thrown errors.
 */
export function parseChartHeader(
  raw: unknown,
  envelopeRequestedId: string,
  envelopeCanonicalId: string,
): ChartPatientHeader | null {
  const data = asRecord(raw);
  if (!data) {
    return null;
  }
  const requested = requiredUuid(data.requested_patient_identity_id);
  const canonical = requiredUuid(data.canonical_patient_identity_id);
  const lifecycle = requiredString(data.lifecycle_status);
  const kind = requiredString(data.identity_kind);
  const label = requiredString(data.display_label);
  const mrn = parseMrn(data.mrn);
  const age = optionalAge(data.age_years);
  const allergy = parseAllergy(data);
  const given = optionalString(data.given_name);
  const family = optionalString(data.family_name);
  const dob = optionalString(data.birth_date);
  const sex = optionalString(data.administrative_sex);
  if (
    !requested ||
    !canonical ||
    lifecycle === null ||
    kind === null ||
    label === null ||
    mrn === null ||
    age === undefined ||
    allergy === null ||
    given === undefined ||
    family === undefined ||
    dob === undefined ||
    sex === undefined
  ) {
    return null;
  }
  if (requested !== envelopeRequestedId || canonical !== envelopeCanonicalId) {
    return null;
  }
  return {
    requested_patient_identity_id: requested,
    canonical_patient_identity_id: canonical,
    lifecycle_status: lifecycle,
    identity_kind: kind,
    display_label: label,
    given_name: given,
    family_name: family,
    birth_date: dob,
    age_years: age,
    administrative_sex: sex,
    mrn,
    documentedAllergy: allergy,
  };
}

/** @deprecated Use parseChartHeader; kept as a named alias for call sites. */
export function readChartHeader(
  raw: PatientHeaderDTO,
  requestedId: string,
  canonicalId: string,
): ChartPatientHeader | null {
  return parseChartHeader(raw, requestedId, canonicalId);
}

export function headerDisplayName(header: ChartPatientHeader, fallback: string): string {
  const combined = [header.given_name, header.family_name].filter(Boolean).join(" ").trim();
  return combined || header.display_label || fallback;
}
