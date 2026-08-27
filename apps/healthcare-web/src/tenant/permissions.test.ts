import { describe, expect, it } from "vitest";

import {
  hasAdminAccess,
  hasAuditAccess,
  hasClinicalWorkspaceAccess,
  hasIdentityAccess,
  hasRegistrationAccess,
  visibleWorkspaces,
} from "./permissions";
import { adminPermissions, clinicianPermissions, identityPermissions, registrarPermissions } from "../test/fixtures";

describe("permission-derived navigation", () => {
  it("shows registration but not clinical for registrar-only permissions", () => {
    expect(hasRegistrationAccess(registrarPermissions)).toBe(true);
    expect(hasClinicalWorkspaceAccess(registrarPermissions)).toBe(false);
    expect(visibleWorkspaces(registrarPermissions)).toEqual(["registration"]);
  });

  it("shows clinical and audit for selected-org clinician permissions", () => {
    expect(hasClinicalWorkspaceAccess(clinicianPermissions)).toBe(true);
    expect(hasAuditAccess(clinicianPermissions)).toBe(true);
    expect(visibleWorkspaces(clinicianPermissions)).toContain("clinical");
    expect(visibleWorkspaces(clinicianPermissions)).not.toContain("admin");
  });

  it("shows identity without clinical chart for identity officer permissions", () => {
    expect(hasIdentityAccess(identityPermissions)).toBe(true);
    expect(hasClinicalWorkspaceAccess(identityPermissions)).toBe(false);
    expect(visibleWorkspaces(identityPermissions)).toEqual(["registration", "identity"]);
  });

  it("does not union permissions across organizations", () => {
    const hospitalA = clinicianPermissions;
    const hospitalB = adminPermissions;
    expect(hasAdminAccess(hospitalA)).toBe(false);
    expect(hasClinicalWorkspaceAccess(hospitalB)).toBe(false);
    expect(visibleWorkspaces(hospitalA)).not.toEqual(visibleWorkspaces(hospitalB));
  });
});
