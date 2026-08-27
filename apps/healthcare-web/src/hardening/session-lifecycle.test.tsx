import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { getAccessToken } from "../auth/tokenStore";
import { getSelectedPatientId, setSelectedPatientId } from "../tenant/clinicalBoundary";
import { FACILITY_STORAGE_KEY, ORG_STORAGE_KEY } from "../tenant/tabStorage";
import {
  clinicianPermissions,
  contextResponse,
  FAC_1,
  facilitiesResponse,
  org,
  ORG_A,
  ORG_B,
  organizationsResponse,
} from "../test/fixtures";
import { authenticateStaff, mockJsonFetch, renderApp } from "../test/render";

describe("session lifecycle hardening", () => {
  it("clears protected state after logout so back cannot restore a session", async () => {
    authenticateStaff();
    setSelectedPatientId("should-clear");
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
    await userEvent.click(screen.getByRole("button", { name: /sign out|keluar/i }));
    expect(getAccessToken()).toBeNull();
    expect(getSelectedPatientId()).toBeNull();
    expect(sessionStorage.getItem(ORG_STORAGE_KEY)).toBeNull();
    expect(await screen.findByRole("heading", { name: /staff sign-in|masuk staf/i })).toBeInTheDocument();
    expect(screen.queryByTestId("active-organization")).not.toBeInTheDocument();
  });

  it("handles parallel 401s without leaving protected content", async () => {
    authenticateStaff();
    mockJsonFetch(() => ({ status: 401, body: { error: { code: "unauthorized" } } }));
    renderApp("/app");
    expect(await screen.findByRole("heading", { name: /session expired|sesi berakhir/i })).toBeInTheDocument();
    expect(getAccessToken()).toBeNull();
  });

  it("revalidates stored org and ignores malformed or foreign ids", async () => {
    authenticateStaff();
    sessionStorage.setItem(ORG_STORAGE_KEY, "not-a-uuid");
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
  });

  it("drops a stored facility that is no longer accessible", async () => {
    authenticateStaff();
    sessionStorage.setItem(ORG_STORAGE_KEY, ORG_A);
    sessionStorage.setItem(FACILITY_STORAGE_KEY, FAC_1);
    mockJsonFetch((url) => {
      if (url.includes("/iam/me/organizations")) {
        return { body: organizationsResponse([org(ORG_A, "Hospital A", ["CLINICIAN"])]) };
      }
      if (url.includes("/iam/me/context")) {
        return {
          body: contextResponse(ORG_A, "Hospital A", clinicianPermissions, {
            facility_scope: "EXPLICIT",
            work_facility_required: true,
          }),
        };
      }
      if (url.includes("/facilities/accessible")) {
        return {
          body: facilitiesResponse(ORG_A, { facility_scope: "EXPLICIT", facilities: [] }),
        };
      }
      return null;
    });
    renderApp("/app");
    await waitFor(() => {
      expect(screen.getByTestId("active-work-facility")).not.toHaveTextContent("Site 1");
    });
    expect(sessionStorage.getItem(FACILITY_STORAGE_KEY)).toBeNull();
  });
});
