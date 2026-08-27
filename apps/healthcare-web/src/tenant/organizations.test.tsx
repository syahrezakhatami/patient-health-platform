import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { QueryClient } from "@tanstack/react-query";

import { queryKeys, removeTenantScopedQueries } from "../api/queryClient";
import { ORG_STORAGE_KEY } from "../tenant/tabStorage";
import { resolveOrganizationChoice } from "../tenant/bootstrap";
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
import { authenticateStaff, mockJsonFetch, renderApp } from "../test/render";

describe("organization bootstrap", () => {
  it("shows unassigned state when provisioned with zero organizations", async () => {
    authenticateStaff();
    mockJsonFetch((url) => {
      if (url.includes("/iam/me/organizations")) {
        return { body: organizationsResponse([], true) };
      }
      return null;
    });
    renderApp("/app");
    expect(await screen.findByRole("heading", { name: /no healthcare organization access|tidak ada akses organisasi/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /platform admin/i })).not.toBeInTheDocument();
  });

  it("auto-selects a single active organization", async () => {
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
    renderApp("/app");
    expect(await screen.findByTestId("active-organization")).toHaveTextContent("Hospital A");
  });

  it("shows the picker when multiple organizations exist", async () => {
    authenticateStaff();
    mockJsonFetch((url) => {
      if (url.includes("/iam/me/organizations")) {
        return {
          body: organizationsResponse([
            org(ORG_A, "Hospital A", ["CLINICIAN"]),
            org(ORG_B, "Hospital B", ["ORG_ADMIN"]),
          ]),
        };
      }
      return null;
    });
    renderApp("/app");
    expect(await screen.findByRole("heading", { name: /select organization|pilih organisasi/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /hospital a/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /hospital b/i })).toBeInTheDocument();
  });

  it("restores a stored organization only after revalidation", async () => {
    authenticateStaff();
    sessionStorage.setItem(ORG_STORAGE_KEY, ORG_B);
    mockJsonFetch((url) => {
      if (url.includes("/iam/me/organizations")) {
        return {
          body: organizationsResponse([
            org(ORG_A, "Hospital A", ["CLINICIAN"]),
            org(ORG_B, "Hospital B", ["ORG_ADMIN"]),
          ]),
        };
      }
      if (url.includes("/iam/me/context")) {
        return { body: contextResponse(ORG_B, "Hospital B", adminPermissions, { role_codes: ["ORG_ADMIN"] }) };
      }
      if (url.includes("/facilities/accessible")) {
        return { body: facilitiesResponse(ORG_B) };
      }
      return null;
    });
    renderApp("/app");
    expect(await screen.findByTestId("active-organization")).toHaveTextContent("Hospital B");
  });

  it("ignores a stale stored organization", () => {
    expect(
      resolveOrganizationChoice({
        organizations: [org(ORG_A, "Hospital A", ["CLINICIAN"])],
        storedOrganizationId: ORG_B,
      }),
    ).toEqual({ kind: "use", organizationId: ORG_A });
  });

  it("switches organization without merging permissions and clears tenant queries", async () => {
    authenticateStaff();
    mockJsonFetch((url) => {
      if (url.includes("/iam/me/organizations")) {
        return {
          body: organizationsResponse([
            org(ORG_A, "Hospital A", ["CLINICIAN"]),
            org(ORG_B, "Hospital B", ["ORG_ADMIN"]),
          ]),
        };
      }
      if (url.includes(`/organizations/${ORG_A}/facilities`) || (url.includes("/iam/me/context") && url.includes("unused"))) {
        return { body: facilitiesResponse(ORG_A) };
      }
      if (url.includes("/iam/me/context")) {
        return { body: contextResponse(ORG_A, "Hospital A", clinicianPermissions) };
      }
      if (url.includes("/facilities/accessible")) {
        const orgId = url.includes(ORG_B) ? ORG_B : ORG_A;
        return { body: facilitiesResponse(orgId) };
      }
      return null;
    });

    const fetchImpl = globalThis.fetch;
    globalThis.fetch = async (input, init) => {
      const url = String(input);
      const headers = init?.headers instanceof Headers ? init.headers : new Headers(init?.headers);
      const orgHeader = headers.get("X-Organization-Id");
      if (url.includes("/iam/me/organizations")) {
        return new Response(
          JSON.stringify(
            organizationsResponse([
              org(ORG_A, "Hospital A", ["CLINICIAN"]),
              org(ORG_B, "Hospital B", ["ORG_ADMIN"]),
            ]),
          ),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.includes("/iam/me/context")) {
        if (orgHeader === ORG_B) {
          return new Response(
            JSON.stringify(contextResponse(ORG_B, "Hospital B", adminPermissions, { role_codes: ["ORG_ADMIN"] })),
            { status: 200, headers: { "Content-Type": "application/json" } },
          );
        }
        return new Response(JSON.stringify(contextResponse(ORG_A, "Hospital A", clinicianPermissions)), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("/facilities/accessible")) {
        return new Response(JSON.stringify(facilitiesResponse(orgHeader === ORG_B ? ORG_B : ORG_A)), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      return fetchImpl(input, init);
    };

    renderApp("/app");
    expect(await screen.findByRole("heading", { name: /select organization|pilih organisasi/i })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /hospital a/i }));
    expect(await screen.findByTestId("active-organization")).toHaveTextContent("Hospital A");
    expect(screen.getByRole("link", { name: /clinical|klinis/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /organization administration|administrasi organisasi/i })).not.toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText(/switch organization|ganti organisasi/i), ORG_B);
    await waitFor(() => {
      expect(screen.getByTestId("active-organization")).toHaveTextContent("Hospital B");
    });
    expect(screen.getByRole("link", { name: /organization administration|administrasi organisasi/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /clinical|klinis/i })).not.toBeInTheDocument();
  });

  it("removeTenantScopedQueries drops the previous organization cache", () => {
    const client = new QueryClient();
    client.setQueryData(queryKeys.context(ORG_A), { org: "A" });
    client.setQueryData(queryKeys.context(ORG_B), { org: "B" });
    removeTenantScopedQueries(client, ORG_A);
    expect(client.getQueryData(queryKeys.context(ORG_A))).toBeUndefined();
    expect(client.getQueryData(queryKeys.context(ORG_B))).toEqual({ org: "B" });
  });
});
