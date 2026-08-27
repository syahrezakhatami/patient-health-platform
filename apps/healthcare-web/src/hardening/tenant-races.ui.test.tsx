import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
import { authenticateStaff, deferred, renderApp } from "../test/render";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("organization switch UI races", () => {
  it("keeps organization B when a late A context arrives last", async () => {
    authenticateStaff();
    const lateA = deferred<Response>();
    globalThis.fetch = async (input, init) => {
      const url = String(input);
      const headers = new Headers(init?.headers);
      const orgId = headers.get("X-Organization-Id");
      if (url.includes("/iam/me/organizations")) {
        return jsonResponse(
          organizationsResponse([
            org(ORG_A, "Hospital A", ["CLINICIAN"]),
            org(ORG_B, "Hospital B", ["ORG_ADMIN"]),
          ]),
        );
      }
      if (url.includes("/iam/me/context")) {
        if (orgId === ORG_A) {
          return lateA.promise;
        }
        return jsonResponse(
          contextResponse(ORG_B, "Hospital B", adminPermissions, { role_codes: ["ORG_ADMIN"] }),
        );
      }
      if (url.includes("/facilities/accessible")) {
        return jsonResponse(facilitiesResponse(orgId === ORG_B ? ORG_B : ORG_A));
      }
      return jsonResponse({ error: { code: "not_found" } }, 404);
    };

    renderApp("/app");
    expect(await screen.findByRole("heading", { name: /select organization|pilih organisasi/i })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /hospital a/i }));
    await userEvent.click(screen.getByRole("button", { name: /hospital b/i }));
    expect(await screen.findByTestId("active-organization")).toHaveTextContent("Hospital B");
    expect(screen.getByRole("link", { name: /organization administration|administrasi organisasi/i })).toBeInTheDocument();
    lateA.resolve(jsonResponse(contextResponse(ORG_A, "Hospital A", clinicianPermissions)));
    await waitFor(() => {
      expect(screen.getByTestId("active-organization")).toHaveTextContent("Hospital B");
    });
    expect(screen.queryByRole("link", { name: /clinical|klinis/i })).not.toBeInTheDocument();
  });
});
