import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

import { apiRequest } from "../api/client";
import { ApiError, parseApiError, shouldRetryRequest, userFacingMessage } from "../api/errors";
import { queryKeys, removeTenantScopedQueries } from "../api/queryClient";
import {
  clearSensitiveClientState,
  isSessionExpiryInFlight,
  registerQueryClient,
  registerSessionHandler,
  resetSessionExpiryLock,
  triggerSessionExpired,
} from "../auth/sessionLifecycle";
import { getAccessToken, setAccessTokenForTests } from "../auth/tokenStore";
import { getChartFacilityFilterId, getSelectedPatientId, setSelectedPatientId } from "../tenant/clinicalBoundary";
import { ORG_A, ORG_B } from "../test/fixtures";

describe("session, cache, and header hardening", () => {
  it("treats concurrent 401 handling as idempotent", () => {
    resetSessionExpiryLock();
    let calls = 0;
    registerSessionHandler(() => {
      calls += 1;
    });
    triggerSessionExpired("unauthorized");
    triggerSessionExpired("unauthorized");
    triggerSessionExpired("expired");
    expect(calls).toBe(1);
    expect(isSessionExpiryInFlight()).toBe(true);
  });

  it("clears token, patient placeholder, and query cache on sensitive-state wipe", () => {
    const client = new QueryClient();
    registerQueryClient(client);
    client.setQueryData(queryKeys.context(ORG_A), { leaked: true });
    setAccessTokenForTests("tok");
    setSelectedPatientId("patient-placeholder");
    clearSensitiveClientState();
    expect(getAccessToken()).toBeNull();
    expect(getSelectedPatientId()).toBeNull();
    expect(client.getQueryData(queryKeys.context(ORG_A))).toBeUndefined();
  });

  it("isolates tenant query keys and removes previous org data on switch", () => {
    const client = new QueryClient();
    client.setQueryData(queryKeys.context(ORG_A), { org: "A" });
    client.setQueryData(queryKeys.accessibleFacilities(ORG_A), { org: "A" });
    client.setQueryData(queryKeys.context(ORG_B), { org: "B" });
    expect(queryKeys.context(ORG_A)).toEqual(["iam-context", ORG_A]);
    removeTenantScopedQueries(client, ORG_A);
    expect(client.getQueryData(queryKeys.context(ORG_A))).toBeUndefined();
    expect(client.getQueryData(queryKeys.context(ORG_B))).toEqual({ org: "B" });
  });

  it("does not retry 401/403/404/422", () => {
    expect(shouldRetryRequest(0, new ApiError(401, "session_expired", "x", null))).toBe(false);
    expect(shouldRetryRequest(0, new ApiError(403, "permission_denied", "x", null))).toBe(false);
    expect(shouldRetryRequest(0, new ApiError(404, "not_found", "x", null))).toBe(false);
    expect(shouldRetryRequest(0, new ApiError(422, "validation", "x", null))).toBe(false);
  });

  it("maps errors without exposing tokens or stacks", () => {
    const mapped = parseApiError(500, { stack: "Traceback", error: { message: "Bearer abc.def.ghi" } });
    expect(mapped.message).toBe(userFacingMessage("server_error"));
    expect(mapped.message).not.toMatch(/Bearer|Traceback|abc\.def/);
  });

  it("does not inject X-Purpose or chart facility_id on shell IAM calls", async () => {
    setAccessTokenForTests("tok");
    let capturedUrl = "";
    const captured: Record<string, string | null> = {};
    globalThis.fetch = async (input, init) => {
      capturedUrl = String(input);
      const headers = new Headers(init?.headers);
      captured.purpose = headers.get("X-Purpose");
      captured.facility = headers.get("X-Facility-Id");
      captured.org = headers.get("X-Organization-Id");
      return new Response(JSON.stringify({ provisioned: true, organizations: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    };
    await apiRequest({ path: "/api/v1/iam/me/organizations", organizationId: ORG_A });
    expect(captured.purpose).toBeNull();
    expect(captured.facility).toBeNull();
    expect(captured.org).toBe(ORG_A);
    expect(capturedUrl).not.toContain("facility_id=");
    expect(getChartFacilityFilterId()).toBeNull();
  });

  it("maps remaining status classes without stacks or raw payloads", () => {
    expect(userFacingMessage(parseApiError(409, { stack: "Traceback" }).code)).not.toMatch(/Traceback/);
    expect(parseApiError(422, { error: { message: "field x" } }).message).toBe(
      userFacingMessage("validation"),
    );
    expect(parseApiError(0, null).code).toBe("network");
    expect(parseApiError(503, { error: { message: "upstream" } }).message).toBe(
      userFacingMessage("server_error"),
    );
  });
});
