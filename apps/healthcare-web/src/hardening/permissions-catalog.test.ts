import { describe, expect, it } from "vitest";

import { WORKSPACE_PERMISSION_RULES, visibleWorkspaces } from "../tenant/permissions";
import {
  auditorCatalog,
  clinicianCatalog,
  identityOfficerCatalog,
  orgAdminCatalog,
  registrarCatalog,
} from "../test/catalogPermissions";

describe("permission navigation vs frozen catalog", () => {
  it("documents the approved workspace mapping", () => {
    expect(WORKSPACE_PERMISSION_RULES.audit).toBe("clinical.condition.read");
    expect(WORKSPACE_PERMISSION_RULES.clinical).toContain("encounter-only");
  });

  it("shows registration only for registrar catalog permissions", () => {
    expect(visibleWorkspaces(registrarCatalog)).toEqual(["registration"]);
  });

  it("shows identity without clinical/audit for identity officer catalog permissions", () => {
    expect(visibleWorkspaces(identityOfficerCatalog)).toEqual(["registration", "identity"]);
  });

  it("shows read workspaces for auditor without admin or identity merge tools", () => {
    const workspaces = visibleWorkspaces(auditorCatalog);
    expect(workspaces).toContain("audit");
    expect(workspaces).toContain("clinical");
    expect(workspaces).toContain("registration");
    expect(workspaces).not.toContain("admin");
    expect(workspaces).not.toContain("identity");
  });

  it("does not grant Audit from encounter.read alone", () => {
    expect(visibleWorkspaces(["clinical.encounter.read", "mpi.identity.read"])).toEqual([
      "registration",
    ]);
  });

  it("shows clinician catalog clinical+audit from clinical.condition.read, not admin", () => {
    const workspaces = visibleWorkspaces(clinicianCatalog);
    expect(workspaces).toContain("clinical");
    expect(workspaces).toContain("audit");
    expect(workspaces).toContain("registration");
    expect(workspaces).not.toContain("admin");
    expect(workspaces).not.toContain("identity");
  });

  it("shows org admin catalog admin capability", () => {
    expect(visibleWorkspaces(orgAdminCatalog)).toContain("admin");
  });
});
