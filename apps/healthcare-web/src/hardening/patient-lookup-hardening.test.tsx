import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { shouldRetryRequest, ApiError } from "../api/errors";
import type { PatientLookupResponse, PatientLookupResult } from "../api/generated/iam-shell";
import { PATIENT_LOOKUP_MUTATION_KEY } from "../api/queryClient";
import { getRegisteredQueryClient } from "../auth/sessionLifecycle";
import { lookupPurposeForWorkspace, LOOKUP_WORKSPACES } from "../patient/purpose";
import { getSelectedPatient, type SelectedPatientSummary } from "../patient/selectionStore";
import { APP_PATHS } from "../routing/paths";
import {
  adminPermissions,
  clinicianPermissions,
  contextResponse,
  facilitiesResponse,
  org,
  ORG_A,
  ORG_B,
  organizationsResponse,
  registrarPermissions,
} from "../test/fixtures";
import { authenticateStaff, deferred, renderApp } from "../test/render";

const LOOKUP_PATH = "/api/v1/mpi/patients/lookup";
const PATIENT_UUID = "33333333-3333-4333-8333-333333333333";
const PATIENT_NAME = "Ada Lovelace";
const MRN = "MRN-HARDEN-0001";
const NIK = "1234567890123456";

interface LookupCall {
  url: string;
  method: string;
  purpose: string | null;
  organizationId: string | null;
  body: Record<string, unknown> | null;
  signal: AbortSignal | null;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function hit(overrides?: Partial<PatientLookupResult>): PatientLookupResult {
  return {
    patient_identity_id: PATIENT_UUID,
    requested_patient_identity_id: null,
    lifecycle_status: "ACTIVE",
    identity_kind: "STANDARD",
    display_name: PATIENT_NAME,
    display_label: "ID-TEST",
    birth_date: "1815-12-10",
    administrative_sex: "FEMALE",
    organization_mrn: MRN,
    masked_identifier: null,
    identifier_verification: "VERIFIED",
    resolved_from_merged: false,
    review_required: false,
    selectable: true,
    ...overrides,
  };
}

function lookupResponse(overrides?: Partial<PatientLookupResponse>): PatientLookupResponse {
  return {
    outcome: "one",
    truncated: false,
    results: [hit()],
    ...overrides,
  };
}

function parseBody(init?: RequestInit): Record<string, unknown> | null {
  if (!init?.body || typeof init.body !== "string") {
    return null;
  }
  return JSON.parse(init.body) as Record<string, unknown>;
}

function mutationCacheBlob(): string {
  const client = getRegisteredQueryClient();
  if (!client) {
    return "";
  }
  return JSON.stringify(
    client.getMutationCache().getAll().map((mutation) => ({
      key: mutation.options.mutationKey,
      state: mutation.state,
    })),
  );
}

function storageContains(value: string): boolean {
  for (const storage of [sessionStorage, localStorage]) {
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index);
      if (!key) {
        continue;
      }
      if (key.includes(value) || (storage.getItem(key) ?? "").includes(value)) {
        return true;
      }
    }
  }
  return false;
}

function installStaffFetch(options: {
  permissions?: string[];
  organizations?: ReturnType<typeof org>[];
  onLookup?: (call: LookupCall) => Promise<Response> | Response;
  onContext?: (orgId: string) => Promise<Response> | Response | null;
}): { calls: LookupCall[] } {
  const calls: LookupCall[] = [];
  const organizations = options.organizations ?? [org(ORG_A, "Hospital A", ["REGISTRAR"])];
  const permissions = options.permissions ?? registrarPermissions;
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    const headers = new Headers(init?.headers);
    const method = init?.method ?? "GET";
    if (url.includes("/iam/me/organizations")) {
      return jsonResponse(organizationsResponse(organizations));
    }
    if (url.includes("/iam/me/context")) {
      const orgId = headers.get("X-Organization-Id") ?? ORG_A;
      if (options.onContext) {
        const override = await options.onContext(orgId);
        if (override) {
          return override;
        }
      }
      const listed = organizations.find((item) => item.organization_id === orgId) ?? organizations[0];
      const name = listed?.name ?? "Hospital";
      const orgPermissions = orgId === ORG_B ? adminPermissions : permissions;
      return jsonResponse(
        contextResponse(orgId, name, orgPermissions, { role_codes: listed?.role_codes }),
      );
    }
    if (url.includes("/facilities/accessible")) {
      return jsonResponse(facilitiesResponse(headers.get("X-Organization-Id") ?? ORG_A));
    }
    if (url.includes("/clinical/")) {
      return jsonResponse({ error: { code: "not_found" } }, 404);
    }
    if (url.includes(LOOKUP_PATH)) {
      const call: LookupCall = {
        url,
        method,
        purpose: headers.get("X-Purpose"),
        organizationId: headers.get("X-Organization-Id"),
        body: parseBody(init),
        signal: init?.signal ?? null,
      };
      calls.push(call);
      if (options.onLookup) {
        return options.onLookup(call);
      }
      return jsonResponse(lookupResponse());
    }
    return jsonResponse({ error: { code: "not_found" } }, 404);
  };
  return { calls };
}

async function switchOrganization(organizationId: string): Promise<void> {
  const switcher = await screen.findByLabelText(/switch organization|ganti organisasi/i);
  fireEvent.change(switcher, { target: { value: organizationId } });
}

async function searchMrn(value = MRN): Promise<void> {
  const field = await screen.findByLabelText(/identifier value|nilai identifikasi/i);
  await userEvent.clear(field);
  await userEvent.type(field, value);
  await userEvent.click(screen.getByRole("button", { name: /^search$|^cari$/i }));
}

describe("patient lookup hardening", () => {
  it("requires an explicit workflow on the generic route and maps it to catalog purpose", async () => {
    authenticateStaff();
    const { calls } = installStaffFetch({ permissions: clinicianPermissions });
    renderApp(APP_PATHS.patientSelect);
    expect(await screen.findByText(/choose the workspace workflow|pilih alur kerja/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/identifier value|nilai identifikasi/i)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: /clinical|klinis/i }));
    await searchMrn();
    await screen.findByTestId("patient-confirmation-card");
    expect(calls[0]?.purpose).toBe("TREATMENT");
    expect(LOOKUP_WORKSPACES).toEqual(["registration", "clinical", "identity", "audit"]);
    expect(lookupPurposeForWorkspace("registration")).toBe("REGISTRATION");
    expect(lookupPurposeForWorkspace("clinical")).toBe("TREATMENT");
    expect(lookupPurposeForWorkspace("identity")).toBe("IDENTITY_RESOLUTION");
    expect(lookupPurposeForWorkspace("audit")).toBe("AUDIT");
    expect(lookupPurposeForWorkspace("admin")).toBeNull();
  });

  it("reuses the same panel in workspaces and never auto-selects review_required or ambiguous hits", async () => {
    authenticateStaff();
    let mode: "review" | "ambiguous" | "one" = "review";
    installStaffFetch({
      permissions: registrarPermissions,
      onLookup: () => {
        if (mode === "review") {
          return jsonResponse(
            lookupResponse({
              outcome: "review_required",
              results: [hit({ selectable: false, review_required: true, masked_identifier: "************3456" })],
            }),
          );
        }
        if (mode === "ambiguous") {
          return jsonResponse(
            lookupResponse({
              outcome: "ambiguous",
              results: [
                hit({ patient_identity_id: PATIENT_UUID, display_name: "First" }),
                hit({ patient_identity_id: "44444444-4444-4444-8444-444444444444", display_name: "Second" }),
              ],
            }),
          );
        }
        return jsonResponse(lookupResponse());
      },
    });
    renderApp(APP_PATHS.registration);
    await searchMrn();
    expect(await screen.findByText(/needs identity review|memerlukan tinjauan identitas/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /select this patient|pilih pasien ini/i })).not.toBeInTheDocument();
    expect(getSelectedPatient()).toBeNull();

    mode = "ambiguous";
    await searchMrn();
    expect(await screen.findByText(/more than one patient|lebih dari satu pasien/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /select this patient|pilih pasien ini/i })).not.toBeInTheDocument();
    expect(getSelectedPatient()).toBeNull();

    mode = "one";
    await searchMrn();
    expect(await screen.findByRole("button", { name: /select this patient|pilih pasien ini/i })).toBeInTheDocument();
    expect(screen.getByTestId("lookup-active-organization")).toHaveTextContent("Hospital A");
    expect(getSelectedPatient()).toBeNull();
    expect(window.location.pathname.includes(PATIENT_UUID)).toBe(false);
    expect(APP_PATHS.patientSelect.includes(PATIENT_UUID)).toBe(false);
  });

  it("keeps selected patient memory minimal and out of storage", async () => {
    authenticateStaff();
    installStaffFetch({ permissions: registrarPermissions });
    renderApp(APP_PATHS.registration);
    await searchMrn();
    await userEvent.click(await screen.findByRole("button", { name: /select this patient|pilih pasien ini/i }));
    const selected = getSelectedPatient() as SelectedPatientSummary;
    expect(Object.keys(selected).sort()).toEqual(
      [
        "administrativeSex",
        "birthDate",
        "displayLabel",
        "displayName",
        "identityKind",
        "lifecycleStatus",
        "organizationId",
        "organizationMrn",
        "patientIdentityId",
        "selectedAt",
      ].sort(),
    );
    expect(JSON.stringify(selected)).not.toContain(NIK);
    expect(JSON.stringify(selected)).not.toContain("lookup_value");
    expect(storageContains(PATIENT_NAME)).toBe(false);
    expect(storageContains(MRN)).toBe(false);
    expect(storageContains(PATIENT_UUID)).toBe(false);
    expect(mutationCacheBlob()).not.toContain(MRN);
    expect(mutationCacheBlob()).not.toContain(NIK);
  });

  it("clears mutation PHI and selected patient when org B context fails", async () => {
    authenticateStaff();
    installStaffFetch({
      permissions: registrarPermissions,
      organizations: [org(ORG_A, "Hospital A", ["REGISTRAR"]), org(ORG_B, "Hospital B", ["ORG_ADMIN"])],
      onContext: (orgId) => {
        if (orgId === ORG_B) {
          return jsonResponse({ error: { code: "internal_error", message: "failed" } }, 500);
        }
        return null;
      },
    });
    sessionStorage.setItem("php.healthcare-web.organization-id", ORG_A);
    renderApp(APP_PATHS.registration);
    await searchMrn();
    await userEvent.click(await screen.findByRole("button", { name: /select this patient|pilih pasien ini/i }));
    expect(getSelectedPatient()?.displayName).toBe(PATIENT_NAME);
    await switchOrganization(ORG_B);
    await waitFor(() => expect(getSelectedPatient()).toBeNull());
    expect(screen.queryByText(PATIENT_NAME)).not.toBeInTheDocument();
    expect(mutationCacheBlob()).not.toContain(MRN);
    expect(mutationCacheBlob()).not.toContain(PATIENT_UUID);
  });

  it("does not restore first-A lookup after A -> B -> A", async () => {
    authenticateStaff();
    const lateFirstA = deferred<Response>();
    let lookups = 0;
    installStaffFetch({
      permissions: registrarPermissions,
      organizations: [org(ORG_A, "Hospital A", ["REGISTRAR"]), org(ORG_B, "Hospital B", ["REGISTRAR"])],
      onContext: (orgId) =>
        jsonResponse(
          contextResponse(orgId, orgId === ORG_B ? "Hospital B" : "Hospital A", registrarPermissions, {
            role_codes: ["REGISTRAR"],
          }),
        ),
      onLookup: () => {
        lookups += 1;
        if (lookups === 1) {
          return lateFirstA.promise;
        }
        return jsonResponse(lookupResponse({ results: [hit({ display_name: "Second A" })] }));
      },
    });
    sessionStorage.setItem("php.healthcare-web.organization-id", ORG_A);
    renderApp(APP_PATHS.registration);
    await searchMrn("FIRST");
    await switchOrganization(ORG_B);
    await waitFor(() => expect(screen.getByTestId("active-organization")).toHaveTextContent("Hospital B"));
    await switchOrganization(ORG_A);
    await waitFor(() => expect(screen.getByTestId("active-organization")).toHaveTextContent("Hospital A"));
    await searchMrn("SECOND");
    expect(await screen.findByText("Second A")).toBeInTheDocument();
    lateFirstA.resolve(jsonResponse(lookupResponse({ results: [hit({ display_name: "First A" })] })));
    await waitFor(() => expect(screen.getByText("Second A")).toBeInTheDocument());
    expect(screen.queryByText("First A")).not.toBeInTheDocument();
    expect(getSelectedPatient()).toBeNull();
  });

  it("propagates AbortSignal to fetch and drops stale A after org switch", async () => {
    authenticateStaff();
    const lateA = deferred<Response>();
    const { calls } = installStaffFetch({
      permissions: registrarPermissions,
      organizations: [org(ORG_A, "Hospital A", ["REGISTRAR"]), org(ORG_B, "Hospital B", ["REGISTRAR"])],
      onContext: (orgId) =>
        jsonResponse(
          contextResponse(orgId, orgId === ORG_B ? "Hospital B" : "Hospital A", registrarPermissions, {
            role_codes: ["REGISTRAR"],
          }),
        ),
      onLookup: (call) => {
        if (call.organizationId === ORG_A) {
          return lateA.promise;
        }
        return jsonResponse(lookupResponse({ outcome: "none", results: [] }));
      },
    });
    sessionStorage.setItem("php.healthcare-web.organization-id", ORG_A);
    renderApp(APP_PATHS.registration);
    await searchMrn();
    await waitFor(() => expect(calls[0]?.signal).toBeTruthy());
    await switchOrganization(ORG_B);
    await waitFor(() => expect(screen.getByTestId("active-organization")).toHaveTextContent("Hospital B"));
    await waitFor(() => expect(calls[0]?.signal?.aborted).toBe(true));
    lateA.resolve(jsonResponse(lookupResponse({ results: [hit({ display_name: "Stale A" })] })));
    await waitFor(() => expect(screen.queryByText("Stale A")).not.toBeInTheDocument());
    expect(getSelectedPatient()).toBeNull();
    expect(mutationCacheBlob()).not.toContain("Stale A");
  });

  it("hides lookup and selected patient when the new org lacks mpi.identity.read", async () => {
    authenticateStaff();
    installStaffFetch({
      permissions: registrarPermissions,
      organizations: [org(ORG_A, "Hospital A", ["REGISTRAR"]), org(ORG_B, "Hospital B", ["ORG_ADMIN"])],
    });
    sessionStorage.setItem("php.healthcare-web.organization-id", ORG_A);
    renderApp(APP_PATHS.registration);
    await searchMrn();
    await userEvent.click(await screen.findByRole("button", { name: /select this patient|pilih pasien ini/i }));
    expect(getSelectedPatient()?.displayName).toBe(PATIENT_NAME);
    await switchOrganization(ORG_B);
    await waitFor(() => expect(screen.getByTestId("active-organization")).toHaveTextContent("Hospital B"));
    expect(getSelectedPatient()).toBeNull();
    expect(screen.queryByText(PATIENT_NAME)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/identifier value|nilai identifikasi/i)).not.toBeInTheDocument();
  });

  it("renders XSS and unicode names as text and uses generic errors", async () => {
    authenticateStaff();
    const xss = `<script>alert(1)</script>`;
    const quoted = `O'Brien "quoted"`;
    const rtl = "مريم";
    let name = xss;
    installStaffFetch({
      permissions: registrarPermissions,
      onLookup: () => jsonResponse(lookupResponse({ results: [hit({ display_name: name })] })),
    });
    renderApp(APP_PATHS.registration);
    await searchMrn();
    let card = await screen.findByTestId("patient-confirmation-card");
    expect(card).toHaveTextContent(xss);
    expect(card.querySelector("script")).toBeNull();
    name = quoted;
    await searchMrn();
    card = await screen.findByTestId("patient-confirmation-card");
    expect(card).toHaveTextContent(quoted);
    name = rtl;
    await searchMrn();
    card = await screen.findByTestId("patient-confirmation-card");
    expect(card).toHaveTextContent(rtl);
  });

  it("does not log PHI and does not put the patient UUID in the route", async () => {
    const srcRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
    const walk = (dir: string): string[] =>
      readdirSync(dir).flatMap((entry) => {
        const path = join(dir, entry);
        return statSync(path).isDirectory() ? walk(path) : path.endsWith(".ts") || path.endsWith(".tsx") ? [path] : [];
      });
    const patientFiles = walk(join(srcRoot, "patient")).filter(
      (path) => !path.includes(".test."),
    );
    const blob = patientFiles.map((file) => readFileSync(file, "utf8")).join("\n");
    expect(blob).not.toMatch(/console\.(log|debug|info|warn|error)/);
    expect(blob).not.toMatch(/dangerouslySetInnerHTML/);
    expect(blob).not.toMatch(/localStorage|sessionStorage|indexedDB|BroadcastChannel/);
    expect(PATIENT_LOOKUP_MUTATION_KEY).toEqual(["patient-lookup"]);
    expect(APP_PATHS.patientSelect).toBe("/app/patients/select");
    expect(APP_PATHS.patientSelect).not.toContain(":");
    for (const status of [401, 403, 409, 422, 429]) {
      expect(shouldRetryRequest(0, new ApiError(status, "unknown", "x", null))).toBe(false);
    }
  });
});
