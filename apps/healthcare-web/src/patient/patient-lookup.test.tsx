import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { getSelectedPatient } from "../patient/selectionStore";
import { APP_PATHS } from "../routing/paths";
import {
  adminPermissions,
  clinicianPermissions,
  contextResponse,
  facilitiesResponse,
  identityPermissions,
  org,
  ORG_A,
  ORG_B,
  organizationsResponse,
  registrarPermissions,
} from "../test/fixtures";
import { authenticateStaff, deferred, renderApp } from "../test/render";
import type { PatientLookupResponse, PatientLookupResult } from "../api/generated/iam-shell";

const LOOKUP_PATH = "/api/v1/mpi/patients/lookup";
const PATIENT_UUID = "33333333-3333-4333-8333-333333333333";
const PATIENT_NAME = "Ada Lovelace";
const XSS_NAME = "<img src=x onerror=alert(1)>";
const MRN = "MRN-TEST-0001";
const NIK = "1234567890123456";
const BPJS = "0001234567890";

interface LookupCall {
  url: string;
  method: string;
  purpose: string | null;
  organizationId: string | null;
  body: Record<string, unknown> | null;
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

function installStaffFetch(options: {
  permissions?: string[];
  organizations?: ReturnType<typeof org>[];
  onLookup?: (call: LookupCall) => Promise<Response> | Response;
}): { calls: LookupCall[] } {
  const calls: LookupCall[] = [];
  const organizations = options.organizations ?? [org(ORG_A, "Hospital A", ["CLINICIAN"])];
  const permissions = options.permissions ?? clinicianPermissions;
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    const headers = new Headers(init?.headers);
    const method = init?.method ?? "GET";
    if (url.includes("/iam/me/organizations")) {
      return jsonResponse(organizationsResponse(organizations));
    }
    if (url.includes("/iam/me/context")) {
      const orgId = headers.get("X-Organization-Id") ?? ORG_A;
      const listed = organizations.find((item) => item.organization_id === orgId) ?? organizations[0];
      const name = listed?.name ?? "Hospital";
      const orgPermissions = orgId === ORG_B ? [...adminPermissions, "mpi.identity.read"] : permissions;
      return jsonResponse(
        contextResponse(orgId, name, orgPermissions, { role_codes: listed?.role_codes }),
      );
    }
    if (url.includes("/facilities/accessible")) {
      return jsonResponse(facilitiesResponse(headers.get("X-Organization-Id") ?? ORG_A));
    }
    if (url.includes("/clinical/")) {
      calls.push({
        url,
        method,
        purpose: headers.get("X-Purpose"),
        organizationId: headers.get("X-Organization-Id"),
        body: parseBody(init),
      });
      return jsonResponse({ error: { code: "not_found" } }, 404);
    }
    if (url.includes(LOOKUP_PATH)) {
      const call: LookupCall = {
        url,
        method,
        purpose: headers.get("X-Purpose"),
        organizationId: headers.get("X-Organization-Id"),
        body: parseBody(init),
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

describe("patient lookup and selection", () => {
  it("hides lookup navigation without mpi.identity.read and forbids the select route", async () => {
    authenticateStaff();
    installStaffFetch({ permissions: adminPermissions, organizations: [org(ORG_A, "Hospital A", ["ORG_ADMIN"])] });
    renderApp(APP_PATHS.patientSelect);
    expect(await screen.findByRole("heading", { name: /permission denied|izin ditolak/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /select patient|pilih pasien/i })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/identifier type|jenis identifikasi/i)).not.toBeInTheDocument();
  });

  it("submits exact MRN, NIK, BPJS, and UUID lookups with purpose and no organization in the body", async () => {
    authenticateStaff();
    const { calls } = installStaffFetch({ permissions: registrarPermissions });
    renderApp(APP_PATHS.registration);
    expect(await screen.findByLabelText(/identifier type|jenis identifikasi/i)).toBeInTheDocument();
    const type = screen.getByLabelText(/identifier type|jenis identifikasi/i);
    const value = screen.getByLabelText(/identifier value|nilai identifikasi/i);

    await userEvent.selectOptions(type, "MRN");
    await userEvent.type(value, MRN);
    await userEvent.click(screen.getByRole("button", { name: /^search$|^cari$/i }));
    await screen.findByTestId("patient-confirmation-card");
    expect(calls[0]?.purpose).toBe("REGISTRATION");
    expect(calls[0]?.body).toEqual({ lookup_type: "MRN", lookup_value: MRN });
    expect(calls[0]?.body).not.toHaveProperty("organization_id");
    expect(calls[0]?.url).not.toContain(MRN);
    expect(APP_PATHS.registration.includes(MRN)).toBe(false);
    expect(APP_PATHS.patientSelect.includes(PATIENT_UUID)).toBe(false);

    await userEvent.clear(value);
    await userEvent.selectOptions(type, "NIK");
    await userEvent.type(value, NIK);
    await userEvent.click(screen.getByRole("button", { name: /^search$|^cari$/i }));
    await waitFor(() => expect(calls.at(-1)?.body).toEqual({ lookup_type: "NIK", lookup_value: NIK }));
    expect(calls.at(-1)?.purpose).toBe("REGISTRATION");
    expect(calls.at(-1)?.url).not.toContain(NIK);

    await userEvent.clear(value);
    await userEvent.selectOptions(type, "BPJS");
    await userEvent.type(value, BPJS);
    await userEvent.click(screen.getByRole("button", { name: /^search$|^cari$/i }));
    await waitFor(() => expect(calls.at(-1)?.body).toEqual({ lookup_type: "BPJS", lookup_value: BPJS }));

    await userEvent.clear(value);
    await userEvent.selectOptions(type, "PATIENT_IDENTITY_ID");
    await userEvent.type(value, PATIENT_UUID);
    await userEvent.click(screen.getByRole("button", { name: /^search$|^cari$/i }));
    await waitFor(() =>
      expect(calls.at(-1)?.body).toEqual({
        lookup_type: "PATIENT_IDENTITY_ID",
        lookup_value: PATIENT_UUID,
      }),
    );
    expect(calls.every((call) => !call.url.includes("/clinical/"))).toBe(true);
    expect(screen.queryByLabelText(/patient name|nama pasien/i)).not.toBeInTheDocument();
  });

  it("sends TREATMENT, IDENTITY_RESOLUTION, and AUDIT purposes from their workspaces", async () => {
    authenticateStaff();
    const { calls } = installStaffFetch({ permissions: [...clinicianPermissions, ...identityPermissions] });
    const clinical = renderApp(APP_PATHS.clinical);
    const value = await screen.findByLabelText(/identifier value|nilai identifikasi/i);
    await userEvent.type(value, MRN);
    await userEvent.click(screen.getByRole("button", { name: /^search$|^cari$/i }));
    await waitFor(() => expect(calls.at(-1)?.purpose).toBe("TREATMENT"));
    clinical.unmount();

    const identity = renderApp(APP_PATHS.identity);
    const identityValue = await screen.findByLabelText(/identifier value|nilai identifikasi/i);
    await userEvent.type(identityValue, MRN);
    await userEvent.click(screen.getByRole("button", { name: /^search$|^cari$/i }));
    await waitFor(() => expect(calls.at(-1)?.purpose).toBe("IDENTITY_RESOLUTION"));
    identity.unmount();

    renderApp(APP_PATHS.audit);
    const auditValue = await screen.findByLabelText(/identifier value|nilai identifikasi/i);
    await userEvent.type(auditValue, MRN);
    await userEvent.click(screen.getByRole("button", { name: /^search$|^cari$/i }));
    await waitFor(() => expect(calls.at(-1)?.purpose).toBe("AUDIT"));
  });

  it("shows confirmation without auto-select, then stores memory-only selection", async () => {
    authenticateStaff();
    installStaffFetch({ permissions: registrarPermissions });
    renderApp(APP_PATHS.patientSelect);
    await userEvent.type(await screen.findByLabelText(/identifier value|nilai identifikasi/i), MRN);
    await userEvent.click(screen.getByRole("button", { name: /^search$|^cari$/i }));
    expect(await screen.findByText(PATIENT_NAME)).toBeInTheDocument();
    expect(screen.queryByTestId("selected-patient-banner")).not.toBeInTheDocument();
    expect(getSelectedPatient()).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /select this patient|pilih pasien ini/i }));
    expect(await screen.findByTestId("selected-patient-banner")).toHaveTextContent(PATIENT_NAME);
    expect(getSelectedPatient()?.patientIdentityId).toBe(PATIENT_UUID);
    expect(getSelectedPatient()?.organizationId).toBe(ORG_A);
    expect(storageContains(PATIENT_NAME)).toBe(false);
    expect(storageContains(MRN)).toBe(false);
    expect(storageContains(PATIENT_UUID)).toBe(false);
  });

  it("renders zero, ambiguous, anonymous, retired, 429, and XSS-safe results", async () => {
    authenticateStaff();
    let mode = "none";
    installStaffFetch({
      permissions: registrarPermissions,
      onLookup: () => {
        if (mode === "none") {
          return jsonResponse(lookupResponse({ outcome: "none", results: [] }));
        }
        if (mode === "ambiguous") {
          return jsonResponse(
            lookupResponse({
              outcome: "ambiguous",
              results: [hit({ patient_identity_id: PATIENT_UUID }), hit({ patient_identity_id: "44444444-4444-4444-8444-444444444444", display_name: "Second Person" })],
            }),
          );
        }
        if (mode === "anonymous") {
          return jsonResponse(
            lookupResponse({
              results: [
                hit({
                  identity_kind: "ANONYMOUS",
                  lifecycle_status: "ANONYMOUS",
                  display_name: "UNKNOWN-ANON",
                  organization_mrn: null,
                }),
              ],
            }),
          );
        }
        if (mode === "retired") {
          return jsonResponse({ error: { code: "identity_not_usable", message: "cannot" } }, 409);
        }
        if (mode === "throttled") {
          return jsonResponse({ error: { code: "rate_limited", message: "Too many requests" } }, 429);
        }
        return jsonResponse(lookupResponse({ results: [hit({ display_name: XSS_NAME })] }));
      },
    });
    renderApp(APP_PATHS.patientSelect);
    const value = await screen.findByLabelText(/identifier value|nilai identifikasi/i);
    const search = () => userEvent.click(screen.getByRole("button", { name: /^search$|^cari$/i }));

    await userEvent.type(value, "missing");
    await search();
    expect(await screen.findByText(/no matching patient|tidak ada pasien yang cocok/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /select this patient|pilih pasien ini/i })).not.toBeInTheDocument();

    mode = "ambiguous";
    await userEvent.clear(value);
    await userEvent.type(value, MRN);
    await search();
    expect(await screen.findByText(/more than one patient|lebih dari satu pasien/i)).toBeInTheDocument();
    expect(screen.getByText("Second Person")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /select this patient|pilih pasien ini/i })).not.toBeInTheDocument();

    mode = "anonymous";
    await search();
    expect(await screen.findByText(/temporary \/ anonymous|sementara \/ anonim/i)).toBeInTheDocument();

    mode = "retired";
    await search();
    expect(await screen.findByText(/cannot be selected|tidak dapat dipilih/i)).toBeInTheDocument();

    mode = "throttled";
    await search();
    expect(await screen.findByText(/too many attempts|terlalu banyak percobaan/i)).toBeInTheDocument();

    mode = "xss";
    await search();
    const card = await screen.findByTestId("patient-confirmation-card");
    expect(card).toHaveTextContent(XSS_NAME);
    expect(card.querySelector("img")).toBeNull();
  });

  it("does not refetch lookup on window focus", async () => {
    authenticateStaff();
    const { calls } = installStaffFetch({ permissions: registrarPermissions });
    renderApp(APP_PATHS.patientSelect);
    await userEvent.type(await screen.findByLabelText(/identifier value|nilai identifikasi/i), MRN);
    await userEvent.click(screen.getByRole("button", { name: /^search$|^cari$/i }));
    await screen.findByTestId("patient-confirmation-card");
    const lookupCount = () => calls.filter((call) => call.url.includes(LOOKUP_PATH)).length;
    expect(lookupCount()).toBe(1);
    window.dispatchEvent(new Event("focus"));
    await new Promise((resolve) => {
      window.setTimeout(resolve, 50);
    });
    expect(lookupCount()).toBe(1);
  });

  it("keeps lookup B when stale A returns last", async () => {
    authenticateStaff();
    const lateA = deferred<Response>();
    let lookups = 0;
    installStaffFetch({
      permissions: registrarPermissions,
      onLookup: () => {
        lookups += 1;
        if (lookups === 1) {
          return lateA.promise;
        }
        return jsonResponse(lookupResponse({ results: [hit({ display_name: "Patient B", organization_mrn: "MRN-B" })] }));
      },
    });
    renderApp(APP_PATHS.patientSelect);
    const value = await screen.findByLabelText(/identifier value|nilai identifikasi/i);
    await userEvent.type(value, "AAA");
    await userEvent.click(screen.getByRole("button", { name: /search|cari/i }));
    await userEvent.clear(value);
    await userEvent.type(value, "BBB");
    await userEvent.click(screen.getByRole("button", { name: /search|cari/i }));
    expect(await screen.findByText("Patient B")).toBeInTheDocument();
    lateA.resolve(jsonResponse(lookupResponse({ results: [hit({ display_name: "Patient A" })] })));
    await waitFor(() => {
      expect(screen.getByText("Patient B")).toBeInTheDocument();
    });
    expect(screen.queryByText("Patient A")).not.toBeInTheDocument();
  });

    it("does not render Hospital A PHI after switching to Hospital B", async () => {
    authenticateStaff();
    const lateA = deferred<Response>();
    installStaffFetch({
      permissions: clinicianPermissions,
      organizations: [org(ORG_A, "Hospital A", ["CLINICIAN"]), org(ORG_B, "Hospital B", ["ORG_ADMIN"])],
      onLookup: (call) => {
        if (call.organizationId === ORG_A) {
          return lateA.promise;
        }
        return jsonResponse(lookupResponse({ outcome: "none", results: [] }));
      },
    });
    sessionStorage.setItem("php.healthcare-web.organization-id", ORG_A);
    renderApp(APP_PATHS.patientSelect);
    await userEvent.click(await screen.findByRole("radio", { name: /clinical|klinis/i }));
    const value = await screen.findByLabelText(/identifier value|nilai identifikasi/i);
    await userEvent.type(value, MRN);
    await userEvent.click(screen.getByRole("button", { name: /^search$|^cari$/i }));
    await userEvent.selectOptions(screen.getByLabelText(/switch organization|ganti organisasi/i), ORG_B);
    expect(await screen.findByTestId("active-organization")).toHaveTextContent("Hospital B");
    lateA.resolve(jsonResponse(lookupResponse({ results: [hit({ display_name: "Alice From A" })] })));
    await waitFor(() => {
      expect(screen.getByTestId("active-organization")).toHaveTextContent("Hospital B");
    });
    expect(screen.queryByText("Alice From A")).not.toBeInTheDocument();
    expect(getSelectedPatient()).toBeNull();
  });

  it("clears selected patient on logout and 401", async () => {
    authenticateStaff();
    let lookupStatus = 200;
    installStaffFetch({
      permissions: registrarPermissions,
      onLookup: () => jsonResponse(lookupStatus === 200 ? lookupResponse() : { error: { code: "unauthorized" } }, lookupStatus),
    });
    renderApp(APP_PATHS.patientSelect);
    await userEvent.type(await screen.findByLabelText(/identifier value|nilai identifikasi/i), MRN);
    await userEvent.click(screen.getByRole("button", { name: /^search$|^cari$/i }));
    await userEvent.click(await screen.findByRole("button", { name: /select this patient|pilih pasien ini/i }));
    expect(getSelectedPatient()?.displayName).toBe(PATIENT_NAME);
    await userEvent.click(screen.getByRole("button", { name: /sign out|keluar/i }));
    expect(getSelectedPatient()).toBeNull();
    expect(screen.queryByText(PATIENT_NAME)).not.toBeInTheDocument();

    authenticateStaff();
    lookupStatus = 401;
    renderApp(APP_PATHS.patientSelect);
    await userEvent.type(await screen.findByLabelText(/identifier value|nilai identifikasi/i), MRN);
    await userEvent.click(screen.getByRole("button", { name: /^search$|^cari$/i }));
    expect(await screen.findByRole("heading", { name: /session expired|sesi berakhir/i })).toBeInTheDocument();
    expect(getSelectedPatient()).toBeNull();
  });
});
