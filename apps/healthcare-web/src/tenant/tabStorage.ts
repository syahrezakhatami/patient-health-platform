/**
 * Per-tab tenant/work-context persistence.
 *
 * Organization and work-facility UUIDs are stored in sessionStorage so Tab A
 * and Tab B can use different hospitals. localStorage is forbidden for this
 * state (it would synchronize clinical context across shared-workstation tabs).
 *
 * Values are never authorization. They are revalidated against IAM APIs.
 */
export const ORG_STORAGE_KEY = "php.healthcare-web.organization-id";
export const FACILITY_STORAGE_KEY = "php.healthcare-web.work-facility-id";
export const LOCALE_STORAGE_KEY = "php.healthcare-web.locale";

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function readStoredOrganizationId(): string | null {
  return readUuid(sessionStorage.getItem(ORG_STORAGE_KEY));
}

export function writeStoredOrganizationId(organizationId: string | null): void {
  if (!organizationId) {
    sessionStorage.removeItem(ORG_STORAGE_KEY);
    return;
  }
  sessionStorage.setItem(ORG_STORAGE_KEY, organizationId);
}

export function readStoredWorkFacilityId(): string | null {
  return readUuid(sessionStorage.getItem(FACILITY_STORAGE_KEY));
}

export function writeStoredWorkFacilityId(facilityId: string | null): void {
  if (!facilityId) {
    sessionStorage.removeItem(FACILITY_STORAGE_KEY);
    return;
  }
  sessionStorage.setItem(FACILITY_STORAGE_KEY, facilityId);
}

export function clearTabTenantStorage(): void {
  sessionStorage.removeItem(ORG_STORAGE_KEY);
  sessionStorage.removeItem(FACILITY_STORAGE_KEY);
}

export function usesSessionStorageForTenantContext(): boolean {
  return true;
}

function readUuid(value: string | null): string | null {
  if (!value || !UUID_RE.test(value)) {
    return null;
  }
  return value;
}
