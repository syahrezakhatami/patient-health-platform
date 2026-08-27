import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  adminPermissions,
  clinicianPermissions,
  contextResponse,
  facilitiesResponse,
  org,
  ORG_A,
  ORG_B,
  organizationsResponse,
} from "../test/fixtures";
import { authenticateStaff, renderApp } from "../test/render";
import { ORG_STORAGE_KEY } from "../tenant/tabStorage";

describe("membership and facility revocation", () => {
  it("drops a revoked organization and revalidates remaining memberships", async () => {
    authenticateStaff();
    sessionStorage.setItem(ORG_STORAGE_KEY, ORG_A);
    let revoked = false;
    globalThis.fetch = async (input, init) => {
      const url = String(input);
      const headers = new Headers(init?.headers);
      const orgId = headers.get("X-Organization-Id");
      if (url.includes("/iam/me/organizations")) {
        const organizations = revoked
          ? [org(ORG_B, "Hospital B", ["ORG_ADMIN"])]
          : [org(ORG_A, "Hospital A", ["CLINICIAN"]), org(ORG_B, "Hospital B", ["ORG_ADMIN"])];
        return new Response(JSON.stringify(organizationsResponse(organizations)), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("/iam/me/context")) {
        if (revoked && orgId === ORG_A) {
          return new Response(JSON.stringify({ error: { code: "permission_denied" } }), {
            status: 403,
            headers: { "Content-Type": "application/json" },
          });
        }
        if (orgId === ORG_B || revoked) {
          return new Response(
            JSON.stringify(
              contextResponse(ORG_B, "Hospital B", adminPermissions, { role_codes: ["ORG_ADMIN"] }),
            ),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        return new Response(JSON.stringify(contextResponse(ORG_A, "Hospital A", clinicianPermissions)), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("/facilities/accessible")) {
        return new Response(JSON.stringify(facilitiesResponse(orgId === ORG_B ? ORG_B : ORG_A)), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response("{}", { status: 404 });
    };

    renderApp("/app");
    expect(await screen.findByTestId("active-organization")).toHaveTextContent("Hospital A");
    revoked = true;
    window.dispatchEvent(new Event("focus"));
    await waitFor(() => {
      expect(screen.getByTestId("active-organization")).toHaveTextContent("Hospital B");
    });
    expect(screen.queryByRole("link", { name: /clinical|klinis/i })).not.toBeInTheDocument();
  });
});
