/**
 * Selected patient is a future in-memory placeholder.
 * This pass has no patient lookup or chart. The slot exists so organization
 * switch and logout already clear it.
 *
 * Work facility is independent of any future clinical chart facility filter.
 * Never copy workFacilityId into chartFacilityFilterId.
 */
let selectedPatientId: string | null = null;
let chartFacilityFilterId: string | null = null;

export function getSelectedPatientId(): string | null {
  return selectedPatientId;
}

export function setSelectedPatientId(patientId: string | null): void {
  selectedPatientId = patientId;
}

export function getChartFacilityFilterId(): string | null {
  return chartFacilityFilterId;
}

export function setChartFacilityFilterId(facilityId: string | null): void {
  chartFacilityFilterId = facilityId;
}

export function clearPatientAndChartFilter(): void {
  selectedPatientId = null;
  chartFacilityFilterId = null;
}

export function clearFacilityDependentCommandState(): void {
  // No clinical forms yet. Keep the hook so facility switch has a defined boundary.
}

export function workFacilityMustNotBecomeChartFilter(
  workFacilityId: string | null,
  chartFilter: string | null,
): boolean {
  if (!workFacilityId) {
    return true;
  }
  return chartFilter !== workFacilityId || chartFilter === null;
}
