/**
 * URL privacy: never put NIK, BPJS, MRN, patient names, or clinical text in routes.
 * Canonical patient UUID is the only future patient path parameter.
 */
const FORBIDDEN_URL_PATTERN =
  /(nik|bpjs|mrn|patient[_-]?name|nomor[_-]?rm|matching_value)/i;

export function pathContainsForbiddenIdentifier(path: string): boolean {
  return FORBIDDEN_URL_PATTERN.test(path);
}

export function patientChartPath(canonicalPatientId: string): string {
  if (!/^[0-9a-f-]{36}$/i.test(canonicalPatientId)) {
    throw new Error("Patient routes accept canonical UUID only");
  }
  return `/app/clinical/patients/${canonicalPatientId}`;
}

export const APP_PATHS = {
  login: "/login",
  callback: "/auth/callback",
  sessionExpired: "/session-expired",
  selectOrganization: "/select-organization",
  unassigned: "/unassigned",
  app: "/app",
  registration: "/app/registration",
  clinical: "/app/clinical",
  identity: "/app/identity",
  audit: "/app/audit",
  admin: "/app/admin",
} as const;
