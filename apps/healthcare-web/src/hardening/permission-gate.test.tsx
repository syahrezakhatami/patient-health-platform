import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { adminPermissions, clinicianPermissions, contextResponse, facilitiesResponse, org, ORG_A, organizationsResponse } from "../test/fixtures";
import { authenticateStaff, mockJsonFetch, renderApp } from "../test/render";
import { APP_PATHS } from "../routing/paths";

describe("permission gate and revocation hardening", () => {
  it("shows forbidden for a workspace the selected org cannot open", async () => {
    authenticateStaff();
    mockJsonFetch((url) => {
      if (url.includes("/iam/me/organizations")) {
        return { body: organizationsResponse([org(ORG_A, "Hospital A", ["CLINICIAN"])]) };
      }
      if (url.includes("/iam/me/context")) {
        return { body: contextResponse(ORG_A, "Hospital A", clinicianPermissions) };
      }
      if (url.includes("/facilities/accessible")) {
        return { body: facilitiesResponse(ORG_A) };
      }
      return null;
    });
    renderApp(APP_PATHS.admin);
    expect(await screen.findByRole("heading", { name: /permission denied|izin ditolak/i })).toBeInTheDocument();
  });

  it("updates navigation after context refresh removes a permission", async () => {
    authenticateStaff();
    let privileged = true;
    mockJsonFetch((url) => {
      if (url.includes("/iam/me/organizations")) {
        return { body: organizationsResponse([org(ORG_A, "Hospital A", ["ORG_ADMIN"])]) };
      }
      if (url.includes("/iam/me/context")) {
        return {
          body: contextResponse(
            ORG_A,
            "Hospital A",
            privileged ? [...clinicianPermissions, ...adminPermissions] : clinicianPermissions,
            { role_codes: privileged ? ["ORG_ADMIN"] : ["CLINICIAN"] },
          ),
        };
      }
      if (url.includes("/facilities/accessible")) {
        return { body: facilitiesResponse(ORG_A) };
      }
      return null;
    });
    renderApp("/app");
    expect(await screen.findByRole("link", { name: /organization administration|administrasi organisasi/i })).toBeInTheDocument();
    privileged = false;
    window.dispatchEvent(new Event("focus"));
    await waitFor(() => {
      expect(screen.queryByRole("link", { name: /organization administration|administrasi organisasi/i })).not.toBeInTheDocument();
    });
  });
});
