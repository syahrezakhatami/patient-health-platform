import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { FORBIDDEN_AUDIENCES, STAFF_AUDIENCE, readPublicConfig } from "../config";
import { ApiError } from "../api/errors";
import { apiRequest } from "../api/client";
import { assertStaffAccessToken, readTokenAudiences } from "../auth/audience";
import { peekOidcStatePersistence } from "../auth/oidc";
import { safeReturnTo } from "../auth/returnTo";
import { getAccessToken, setAccessTokenForTests } from "../auth/tokenStore";
import { ORG_STORAGE_KEY } from "../tenant/tabStorage";
import {
  clinicianPermissions,
  contextResponse,
  facilitiesResponse,
  org,
  ORG_A,
  organizationsResponse,
} from "../test/fixtures";
import { authenticateStaff, mockJsonFetch, renderApp } from "../test/render";

function staffJwt(audience: string): string {
  const payload = btoa(JSON.stringify({ aud: audience })).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `aaa.${payload}.bbb`;
}

describe("auth and session", () => {
  it("sends unauthenticated users to login", async () => {
    renderApp("/app");
    expect(await screen.findByRole("heading", { name: /staff sign-in|masuk staf/i })).toBeInTheDocument();
  });

  it("bootstraps an authenticated staff session", async () => {
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
    expect(screen.queryByText(/platform admin/i)).not.toBeInTheDocument();
  });

  it("expires the session on API 401 and clears tenant storage", async () => {
    authenticateStaff();
    sessionStorage.setItem(ORG_STORAGE_KEY, ORG_A);
    mockJsonFetch(() => ({ status: 401, body: { error: { code: "unauthorized", message: "no" } } }));
    renderApp("/app");
    expect(await screen.findByRole("heading", { name: /session expired|sesi berakhir/i })).toBeInTheDocument();
    expect(getAccessToken()).toBeNull();
    expect(sessionStorage.getItem(ORG_STORAGE_KEY)).toBeNull();
  });

  it("clears in-memory token and query cache on logout", async () => {
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
    await userEvent.click(screen.getByRole("button", { name: /sign out|keluar/i }));
    await waitFor(() => {
      expect(getAccessToken()).toBeNull();
      expect(sessionStorage.getItem(ORG_STORAGE_KEY)).toBeNull();
    });
    expect(await screen.findByRole("heading", { name: /staff sign-in|masuk staf/i })).toBeInTheDocument();
  });

  it("does not write the access token to localStorage or sessionStorage", () => {
    setAccessTokenForTests("header.payload.signature");
    expect(localStorage.getItem("access_token")).toBeNull();
    expect(sessionStorage.getItem("access_token")).toBeNull();
    expect(JSON.stringify(localStorage)).not.toContain("header.payload.signature");
    expect(JSON.stringify(sessionStorage)).not.toContain("header.payload.signature");
    expect(getAccessToken()).toBe("header.payload.signature");
  });

  it("uses php-api and rejects patient/platform audiences", () => {
    expect(readPublicConfig().oidcAudience).toBe(STAFF_AUDIENCE);
    expect(FORBIDDEN_AUDIENCES).toEqual(["php-platform", "php-patient"]);
    expect(() => assertStaffAccessToken(staffJwt("php-patient"))).toThrow(/patient/i);
    expect(() => assertStaffAccessToken(staffJwt("php-platform"))).toThrow(/platform/i);
    expect(() => assertStaffAccessToken(staffJwt("php-api"))).not.toThrow();
    expect(readTokenAudiences(staffJwt("php-api"))).toEqual(["php-api"]);
  });

  it("keeps OIDC user store in memory", () => {
    expect(peekOidcStatePersistence()).toEqual({
      userStore: "memory",
      stateStore: "sessionStorage",
    });
  });

  it("rejects open redirects", () => {
    expect(safeReturnTo("https://evil.example/phish")).toBe("/app");
    expect(safeReturnTo("//evil.example")).toBe("/app");
    expect(safeReturnTo("/app/clinical")).toBe("/app/clinical");
    expect(safeReturnTo("/login")).toBe("/app");
  });

  it("maps 401 without exposing bearer tokens", async () => {
    setAccessTokenForTests("header.payload.signature");
    globalThis.fetch = vi.fn(async () => new Response("{}", { status: 401 }));
    await expect(apiRequest({ path: "/api/v1/iam/me/organizations" })).rejects.toBeInstanceOf(ApiError);
    try {
      await apiRequest({ path: "/api/v1/iam/me/organizations" });
    } catch (error) {
      expect(String(error)).not.toContain("header.payload.signature");
      expect(String(error)).not.toContain("Bearer");
    }
  });
});
