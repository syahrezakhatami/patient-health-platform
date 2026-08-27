import type { AccessibleOrganizationDTO } from "../api/generated/iam-shell";

export type OrganizationResolution =
  | { kind: "unassigned" }
  | { kind: "select"; organizations: AccessibleOrganizationDTO[] }
  | { kind: "use"; organizationId: string };

export function activeOrganizations(
  organizations: AccessibleOrganizationDTO[] | undefined,
): AccessibleOrganizationDTO[] {
  return (organizations ?? []).filter((organization) => organization.status === "ACTIVE");
}

/**
 * provisioned=true is not tenant authority. Empty ACTIVE orgs → unassigned.
 * Stored org is used only when it is still in the live list.
 */
export function resolveOrganizationChoice(input: {
  organizations: AccessibleOrganizationDTO[] | undefined;
  storedOrganizationId: string | null;
}): OrganizationResolution {
  const active = activeOrganizations(input.organizations);
  if (active.length === 0) {
    return { kind: "unassigned" };
  }
  if (input.storedOrganizationId) {
    const stored = active.find((org) => org.organization_id === input.storedOrganizationId);
    if (stored) {
      return { kind: "use", organizationId: stored.organization_id };
    }
  }
  if (active.length === 1) {
    const only = active[0];
    if (only) {
      return { kind: "use", organizationId: only.organization_id };
    }
  }
  return { kind: "select", organizations: active };
}
