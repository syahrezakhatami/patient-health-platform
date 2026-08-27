import type { AccessibleFacilityDTO, FacilityScopeKind } from "../api/generated/iam-shell";

export type WorkFacilityResolution =
  | { kind: "unset" }
  | { kind: "auto"; facilityId: string }
  | { kind: "choose"; facilities: AccessibleFacilityDTO[] }
  | { kind: "restore"; facilityId: string };

/**
 * Work facility is request/UI context, not a chart filter.
 *
 * Safe auto-select only when EXPLICIT (work_facility_required) and exactly one
 * accessible facility. Never pick facilities[0] when multiple exist.
 * ALL_IN_ORGANIZATION does not invent an "All Facilities" identifier.
 */
export function resolveWorkFacilityChoice(input: {
  facilityScope: FacilityScopeKind;
  workFacilityRequired: boolean;
  facilities: AccessibleFacilityDTO[];
  storedFacilityId: string | null;
}): WorkFacilityResolution {
  const stored = input.storedFacilityId
    ? input.facilities.find((facility) => facility.id === input.storedFacilityId)
    : undefined;
  if (stored) {
    return { kind: "restore", facilityId: stored.id };
  }

  if (input.facilityScope === "EXPLICIT" && input.workFacilityRequired && input.facilities.length === 1) {
    const only = input.facilities[0];
    if (only) {
      return { kind: "auto", facilityId: only.id };
    }
  }

  if (input.workFacilityRequired && input.facilities.length > 1) {
    return { kind: "choose", facilities: input.facilities };
  }

  return { kind: "unset" };
}

export function isWorkFacilityRequiredHint(workFacilityRequired: boolean): boolean {
  return workFacilityRequired;
}
