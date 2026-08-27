/**
 * Selected-org navigation is UX only. Backend authorization remains authoritative.
 *
 * Mapping follows docs/architecture/healthcare-web-shell-iam-context-design.md §14
 * and the frozen permission catalog. There is no audit.* catalog permission;
 * this shell does not invent one.
 *
 * | Workspace | Show when (effective_permissions of selected org) |
 * | Registration | mpi.identity.read OR clinical.encounter.create OR clinical.encounter.read |
 * | Clinical | any clinical.*.read other than encounter-only (registrar stays Registration) |
 * | Identity | mpi.merge.execute OR mpi.match.review |
 * | Audit | clinical.condition.read (approved design). Not encounter.read alone. |
 * | Administration | iam.membership.manage OR org.facility.create OR org.identifier.manage |
 *
 * Clinical workspace in this shell is an empty read-chart placeholder, not write
 * forms. Auditor catalog holds clinical *.read without *.create; they may see
 * Clinical (read) and Audit. Write forms are out of scope.
 */
export type WorkspaceId = "registration" | "clinical" | "identity" | "audit" | "admin";

export const WORKSPACE_PERMISSION_RULES: Record<WorkspaceId, string> = {
  registration: "mpi.identity.read | clinical.encounter.create | clinical.encounter.read",
  clinical: "clinical.*.read except encounter-only",
  identity: "mpi.merge.execute | mpi.match.review",
  audit: "clinical.condition.read",
  admin: "iam.membership.manage | org.facility.create | org.identifier.manage",
};

const ENCOUNTER_READ = "clinical.encounter.read";
const ENCOUNTER_CREATE = "clinical.encounter.create";
const AUDIT_PERMISSION = "clinical.condition.read";

export function hasPermission(permissions: readonly string[], code: string): boolean {
  return permissions.includes(code);
}

export function clinicalReadPermissions(permissions: readonly string[]): string[] {
  return permissions.filter((code) => code.startsWith("clinical.") && code.endsWith(".read"));
}

export function nonEncounterClinicalReads(permissions: readonly string[]): string[] {
  return clinicalReadPermissions(permissions).filter((code) => code !== ENCOUNTER_READ);
}

export function hasRegistrationAccess(permissions: readonly string[]): boolean {
  return (
    hasPermission(permissions, "mpi.identity.read") ||
    hasPermission(permissions, ENCOUNTER_CREATE) ||
    hasPermission(permissions, ENCOUNTER_READ)
  );
}

export function hasClinicalWorkspaceAccess(permissions: readonly string[]): boolean {
  return nonEncounterClinicalReads(permissions).length > 0;
}

export function hasIdentityAccess(permissions: readonly string[]): boolean {
  return hasPermission(permissions, "mpi.merge.execute") || hasPermission(permissions, "mpi.match.review");
}

export function hasAuditAccess(permissions: readonly string[]): boolean {
  return hasPermission(permissions, AUDIT_PERMISSION);
}

export function hasAdminAccess(permissions: readonly string[]): boolean {
  return (
    hasPermission(permissions, "iam.membership.manage") ||
    hasPermission(permissions, "org.facility.create") ||
    hasPermission(permissions, "org.identifier.manage")
  );
}

const CHECKS: Record<WorkspaceId, (permissions: readonly string[]) => boolean> = {
  registration: hasRegistrationAccess,
  clinical: hasClinicalWorkspaceAccess,
  identity: hasIdentityAccess,
  audit: hasAuditAccess,
  admin: hasAdminAccess,
};

export function visibleWorkspaces(permissions: readonly string[]): WorkspaceId[] {
  return (Object.keys(CHECKS) as WorkspaceId[]).filter((workspace) => CHECKS[workspace](permissions));
}

export function canOpenWorkspace(permissions: readonly string[], workspace: WorkspaceId): boolean {
  return CHECKS[workspace](permissions);
}
