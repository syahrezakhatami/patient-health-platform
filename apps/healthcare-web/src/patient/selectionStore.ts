import type { PatientLookupResult } from "../api/generated/iam-shell";

export interface SelectedPatientSummary {
  patientIdentityId: string;
  organizationId: string;
  displayName: string;
  displayLabel: string;
  birthDate: string | null;
  administrativeSex: string | null;
  organizationMrn: string | null;
  identityKind: string;
  lifecycleStatus: string;
  selectedAt: string;
}

let selectedPatient: SelectedPatientSummary | null = null;
let selectionEpoch = 0;
const listeners = new Set<() => void>();

export function getSelectionEpoch(): number {
  return selectionEpoch;
}

export function getSelectedPatient(): SelectedPatientSummary | null {
  return selectedPatient;
}

export function subscribeSelectedPatient(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function setSelectedPatient(next: SelectedPatientSummary | null): void {
  selectionEpoch += 1;
  selectedPatient = next;
  for (const listener of listeners) {
    listener();
  }
}

/** Update identity from Clinical Read canonical header without starting a new selection. */
export function applyCanonicalChartPatient(
  next: SelectedPatientSummary,
  expected: { epoch: number; organizationId: string; requestedPatientId: string },
): boolean {
  if (selectionEpoch !== expected.epoch || !selectedPatient) {
    return false;
  }
  if (selectedPatient.patientIdentityId === next.patientIdentityId) {
    return false;
  }
  if (selectedPatient.organizationId !== expected.organizationId) {
    return false;
  }
  if (
    selectedPatient.patientIdentityId !== expected.requestedPatientId &&
    selectedPatient.patientIdentityId !== next.patientIdentityId
  ) {
    return false;
  }
  selectedPatient = { ...next, selectedAt: selectedPatient.selectedAt };
  for (const listener of listeners) {
    listener();
  }
  return true;
}

export function clearSelectedPatient(): void {
  setSelectedPatient(null);
}

export function selectedPatientForOrganization(
  organizationId: string | null,
): SelectedPatientSummary | null {
  if (!organizationId || selectedPatient?.organizationId !== organizationId) {
    return null;
  }
  return selectedPatient;
}

export function summaryFromLookupResult(
  result: PatientLookupResult,
  organizationId: string,
): SelectedPatientSummary {
  return {
    patientIdentityId: result.patient_identity_id,
    organizationId,
    displayName: result.display_name,
    displayLabel: result.display_label,
    birthDate: result.birth_date,
    administrativeSex: result.administrative_sex,
    organizationMrn: result.organization_mrn,
    identityKind: result.identity_kind,
    lifecycleStatus: result.lifecycle_status,
    selectedAt: new Date().toISOString(),
  };
}
