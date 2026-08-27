import type { RequestPurpose } from "../api/client";
import type { WorkspaceId } from "../tenant/permissions";

export const LOOKUP_WORKSPACES: readonly WorkspaceId[] = [
  "registration",
  "clinical",
  "identity",
  "audit",
];

export function lookupPurposeForWorkspace(workspace: WorkspaceId): RequestPurpose | null {
  switch (workspace) {
    case "registration":
      return "REGISTRATION";
    case "clinical":
      return "TREATMENT";
    case "identity":
      return "IDENTITY_RESOLUTION";
    case "audit":
      return "AUDIT";
    default:
      return null;
  }
}

export function isLookupPurpose(value: string): value is RequestPurpose {
  return (
    value === "TREATMENT" ||
    value === "REGISTRATION" ||
    value === "IDENTITY_RESOLUTION" ||
    value === "AUDIT"
  );
}
