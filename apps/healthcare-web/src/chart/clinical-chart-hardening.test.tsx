import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CLINICAL_CHART_PURPOSE } from "../api/clinical";
import { parseApiError } from "../api/errors";
import { clinicalKeys, isClinicalQueryKey } from "../api/queryClient";
import { getRegisteredQueryClient } from "../auth/sessionLifecycle";
import { clinicalChartCoordinator } from "../chart/clinicalChartCoordinator";
import { clinicalQueryPolicy } from "../chart/queryPolicy";
import { selectPatientAndWipeChart, closePatientAndWipeChart } from "../chart/wipe";
import type { ChartSection, ChartShellResponse, ClinicalSummaryResponse } from "../api/generated/iam-shell";
import { getSelectedPatient } from "../patient/selectionStore";
import { APP_PATHS } from "../routing/paths";
import { clinicianCatalog } from "../test/catalogPermissions";
import {
  contextResponse,
  facilitiesResponse,
  org,
  ORG_A,
  ORG_B,
  organizationsResponse,
} from "../test/fixtures";
import { authenticateStaff, deferred, renderApp } from "../test/render";

const PATIENT_A = "33333333-3333-4333-8333-333333333333";
const PATIENT_B = "44444444-4444-4444-8444-444444444444";
const PATIENT_Y = "55555555-5555-4555-8555-555555555555";
const NAME_A = "Ada Lovelace";
const NAME_B = "Grace Hopper";
const MRN_A = "MRN-A-0001";
const XSS = "<script>alert(1)</script>";
const OPAQUE_CURSOR = 'opaque/cursor+with spaces&quotes={"x":1}';

interface ChartCall {
  url: string;
  purpose: string | null;
  organizationId: string | null;
  facilityQuery: boolean;
  signal: AbortSignal | null;
}

function isShellUrl(url: string): boolean {
  return url.includes("/chart") && !url.includes("/summary") && !url.includes("/timeline") && !url.includes("/sections/");
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function header(overrides?: Record<string, unknown>) {
  return {
    requested_patient_identity_id: PATIENT_A,
    canonical_patient_identity_id: PATIENT_A,
    lifecycle_status: "ACTIVE",
    identity_kind: "PERSON",
    display_label: "ID-A",
    given_name: "Ada",
    family_name: "Lovelace",
    birth_date: "1815-12-10",
    age_years: 30,
    administrative_sex: "FEMALE",
    mrn: [MRN_A],
    documented_allergy_exists: false,
    ...overrides,
  };
}

function shell(overrides?: Partial<ChartShellResponse> & { header?: Record<string, unknown> }): ChartShellResponse {
  const { header: headerOverrides, ...rest } = overrides ?? {};
  const requested = rest.requested_patient_identity_id ?? PATIENT_A;
  const canonical = rest.canonical_patient_identity_id ?? PATIENT_A;
  return {
    requested_patient_identity_id: requested,
    canonical_patient_identity_id: canonical,
    authorized_sections: ["encounters", "conditions", "allergies", "medications", "notes", "laboratory", "observations"],
    header: header({
      requested_patient_identity_id: requested,
      canonical_patient_identity_id: canonical,
      ...headerOverrides,
    }) as ChartShellResponse["header"],
    ...rest,
  };
}

function summary(overrides?: Partial<ClinicalSummaryResponse>): ClinicalSummaryResponse {
  return {
    requested_patient_identity_id: PATIENT_A,
    canonical_patient_identity_id: PATIENT_A,
    active_conditions: [],
    ...overrides,
  };
}

function selectPatient(id: string, name: string, organizationId = ORG_A) {
  selectPatientAndWipeChart({
    patientIdentityId: id,
    organizationId,
    displayName: name,
    displayLabel: name,
    birthDate: "1815-12-10",
    administrativeSex: "FEMALE",
    organizationMrn: MRN_A,
    identityKind: "STANDARD",
    lifecycleStatus: "ACTIVE",
    selectedAt: new Date().toISOString(),
  });
}

function listenAbort<T>(signal: AbortSignal | null | undefined, pending: Promise<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const onAbort = () => reject(new DOMException("Aborted", "AbortError"));
    signal?.addEventListener("abort", onAbort);
    pending.then(
      (value) => {
        signal?.removeEventListener("abort", onAbort);
        if (signal?.aborted) {
          reject(new DOMException("Aborted", "AbortError"));
          return;
        }
        resolve(value);
      },
      (error) => {
        signal?.removeEventListener("abort", onAbort);
        reject(error);
      },
    );
  });
}

function clinicalCache() {
  return (getRegisteredQueryClient()?.getQueryCache().getAll() ?? []).filter((query) =>
    isClinicalQueryKey(query.queryKey),
  );
}

function installChartFetch(options?: {
  permissions?: string[];
  organizations?: ReturnType<typeof org>[];
  onChart?: (call: ChartCall, init?: RequestInit) => Promise<Response> | Response;
}): { calls: ChartCall[] } {
  const calls: ChartCall[] = [];
  const organizations = options?.organizations ?? [org(ORG_A, "Hospital A", ["CLINICIAN"])];
  const permissions = options?.permissions ?? clinicianCatalog;
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    const headers = new Headers(init?.headers);
    const call: ChartCall = {
      url,
      purpose: headers.get("X-Purpose"),
      organizationId: headers.get("X-Organization-Id"),
      facilityQuery: /[?&]facility_id=/.test(url),
      signal: init?.signal ?? null,
    };
    if (url.includes("/iam/me/organizations")) {
      return jsonResponse(organizationsResponse(organizations));
    }
    if (url.includes("/iam/me/context")) {
      const orgId = headers.get("X-Organization-Id") ?? ORG_A;
      const listed = organizations.find((item) => item.organization_id === orgId) ?? organizations[0];
      return jsonResponse(contextResponse(orgId, listed?.name ?? "Hospital", permissions, { role_codes: listed?.role_codes }));
    }
    if (url.includes("/facilities/accessible")) {
      return jsonResponse(facilitiesResponse(headers.get("X-Organization-Id") ?? ORG_A));
    }
    if (url.includes("/api/v1/clinical/patients")) {
      calls.push(call);
      if (options?.onChart) {
        return options.onChart(call, init);
      }
      if (url.includes("/summary")) {
        return jsonResponse(summary());
      }
      if (url.includes("/timeline")) {
        return jsonResponse({
          requested_patient_identity_id: PATIENT_A,
          canonical_patient_identity_id: PATIENT_A,
          items: [],
          has_more: false,
        });
      }
      if (url.includes("/sections/")) {
        return jsonResponse({
          requested_patient_identity_id: PATIENT_A,
          canonical_patient_identity_id: PATIENT_A,
          section: url.split("/sections/")[1]?.split("?")[0] as ChartSection,
          items: [],
          has_more: false,
        });
      }
      return jsonResponse(shell());
    }
    return jsonResponse({ error: { code: "not_found" } }, 404);
  };
  return { calls };
}

describe("clinical chart selected-patient gate", () => {
  it("makes zero Clinical Read calls without a selected patient", async () => {
    authenticateStaff();
    const { calls } = installChartFetch();
    renderApp(APP_PATHS.clinicalChart);
    expect(await screen.findByTestId("chart-patient-gate")).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it("clears a foreign-org selection before any Clinical Read request", async () => {
    authenticateStaff();
    const { calls } = installChartFetch();
    selectPatient(PATIENT_A, NAME_A, ORG_B);
    renderApp(APP_PATHS.clinicalChart);
    expect(await screen.findByTestId("chart-patient-gate")).toBeInTheDocument();
    await waitFor(() => {
      expect(getSelectedPatient()).toBeNull();
    });
    expect(calls).toHaveLength(0);
  });

  it("stops Clinical Read when the selected patient is cleared during shell load", async () => {
    authenticateStaff();
    const pending = deferred<Response>();
    const { calls } = installChartFetch({
      onChart: (_call, init) => listenAbort(init?.signal, pending.promise),
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await waitFor(() => expect(calls.some((call) => isShellUrl(call.url))).toBe(true));
    closePatientAndWipeChart();
    expect(await screen.findByTestId("chart-patient-gate")).toBeInTheDocument();
    pending.resolve(jsonResponse(shell({ header: { given_name: "STALE-CLEARED" } })));
    await waitFor(() => {
      expect(screen.queryByText("STALE-CLEARED")).not.toBeInTheDocument();
      expect(clinicalCache()).toHaveLength(0);
    });
  });
});

describe("clinical chart request contract", () => {
  it("opens with exactly one shell then one summary, TREATMENT, and no facility_id query", async () => {
    authenticateStaff();
    const { calls } = installChartFetch();
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    await waitFor(() => {
      const clinical = calls.filter((call) => call.url.includes("/clinical/patients"));
      expect(clinical.filter((call) => isShellUrl(call.url))).toHaveLength(1);
      expect(clinical.filter((call) => call.url.includes("/summary"))).toHaveLength(1);
    });
    await new Promise((resolve) => setTimeout(resolve, 40));
    const clinical = calls.filter((call) => call.url.includes("/clinical/patients"));
    expect(clinical).toHaveLength(2);
    expect(clinical.every((call) => call.purpose === CLINICAL_CHART_PURPOSE)).toBe(true);
    expect(clinical.every((call) => call.purpose !== "REGISTRATION")).toBe(true);
    expect(clinical.every((call) => call.purpose !== "IDENTITY_RESOLUTION")).toBe(true);
    expect(clinical.every((call) => call.purpose !== "AUDIT")).toBe(true);
    expect(clinical.every((call) => !call.facilityQuery)).toBe(true);
    expect(clinical.some((call) => call.url.includes("/sections/"))).toBe(false);
    expect(clinical.some((call) => call.url.includes("/timeline"))).toBe(false);
  });

  it("fans out only the opened section or timeline", async () => {
    authenticateStaff();
    const { calls } = installChartFetch();
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    await userEvent.click(await screen.findByRole("button", { name: /conditions|kondisi/i }));
    await waitFor(() => {
      expect(calls.filter((call) => call.url.includes("/sections/conditions"))).toHaveLength(1);
    });
    await userEvent.click(await screen.findByRole("button", { name: /allergies|alergi/i }));
    await waitFor(() => {
      expect(calls.filter((call) => call.url.includes("/sections/allergies"))).toHaveLength(1);
    });
    await userEvent.click(await screen.findByRole("button", { name: /timeline|linimasa/i }));
    await waitFor(() => {
      expect(calls.filter((call) => call.url.includes("/timeline"))).toHaveLength(1);
    });
    expect(calls.some((call) => call.url.includes("/sections/medications"))).toBe(false);
    expect(calls.some((call) => call.url.includes("/sections/encounters"))).toBe(false);
  });

  it("does not refetch PHI on window focus", async () => {
    authenticateStaff();
    const { calls } = installChartFetch();
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    await waitFor(() => expect(calls).toHaveLength(2));
    window.dispatchEvent(new Event("focus"));
    window.dispatchEvent(new Event("visibilitychange"));
    await new Promise((resolve) => setTimeout(resolve, 40));
    expect(calls).toHaveLength(2);
    expect(clinicalQueryPolicy.refetchOnWindowFocus).toBe(false);
    expect(clinicalQueryPolicy.refetchOnReconnect).toBe(false);
    expect(clinicalQueryPolicy.placeholderData).toBeUndefined();
  });
});

describe("clinical chart authorization and empty states", () => {
  it("does not reconstruct section access from a broad frontend permission set", async () => {
    authenticateStaff();
    installChartFetch({
      permissions: clinicianCatalog,
      onChart: (call) => {
        if (call.url.includes("/summary")) {
          return jsonResponse(summary());
        }
        return jsonResponse(shell({ authorized_sections: ["encounters"] }));
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    expect(await screen.findByRole("button", { name: /encounters|kunjungan/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /conditions|kondisi/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /medications|pengobatan/i })).not.toBeInTheDocument();
    expect(await screen.findByTestId("allergy-safety")).toHaveTextContent(/not available|tidak tersedia/i);
  });

  it("ignores unknown future sections without requesting them", async () => {
    authenticateStaff();
    const { calls } = installChartFetch({
      onChart: (call) => {
        if (call.url.includes("/summary")) {
          return jsonResponse(summary());
        }
        return jsonResponse(
          shell({
            authorized_sections: ["conditions", "future-clinical-domain"] as ChartShellResponse["authorized_sections"],
          }),
        );
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    expect(screen.queryByText("future-clinical-domain")).not.toBeInTheDocument();
    expect(calls.some((call) => call.url.includes("future-clinical-domain"))).toBe(false);
  });

  it("renders unauthorized allergies/conditions/medications/laboratory as unavailable, not empty", async () => {
    authenticateStaff();
    installChartFetch({
      onChart: (call) => {
        if (call.url.includes("/summary")) {
          return jsonResponse({
            requested_patient_identity_id: PATIENT_A,
            canonical_patient_identity_id: PATIENT_A,
          });
        }
        return jsonResponse(shell({ authorized_sections: ["encounters"] }));
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    expect(await screen.findByTestId("allergy-safety")).toHaveTextContent(/not available|tidak tersedia/i);
    expect(screen.queryByText(/no documented records|tidak ada catatan terdokumentasi/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/no known allergies|tidak ada alergi/i)).not.toBeInTheDocument();
    expect(screen.getAllByText(/not available|tidak tersedia/i).length).toBeGreaterThan(3);
  });

  it("renders authorized empty distinctly from unauthorized", async () => {
    authenticateStaff();
    installChartFetch({
      onChart: (call) => {
        if (call.url.includes("/summary")) {
          return jsonResponse(
            summary({
              active_conditions: [],
              active_medications: [],
            }),
          );
        }
        if (call.url.includes("/sections/conditions")) {
          return jsonResponse({
            requested_patient_identity_id: PATIENT_A,
            canonical_patient_identity_id: PATIENT_A,
            section: "conditions",
            items: [],
            has_more: false,
          });
        }
        return jsonResponse(shell({ authorized_sections: ["conditions", "medications"] }));
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    expect(
      await screen.findAllByText(/no items in this summary|tidak ada item pada ringkasan/i),
    ).not.toHaveLength(0);
    await userEvent.click(await screen.findByRole("button", { name: /conditions|kondisi/i }));
    expect(await screen.findByText(/no documented records|tidak ada catatan terdokumentasi/i)).toBeInTheDocument();
  });

  it("keeps allergy true / false / omitted / unauthorized / summary error / section error distinct", async () => {
    authenticateStaff();
    installChartFetch({
      onChart: (call) => {
        if (call.url.includes("/summary")) {
          return jsonResponse({ error: { code: "validation" } }, 422);
        }
        return jsonResponse(shell({ header: { documented_allergy_exists: true } }));
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    expect(await screen.findByTestId("clinical-chart")).toBeInTheDocument();
    expect(await screen.findByText(/could not be loaded|tidak dapat dimuat/i)).toBeInTheDocument();
    expect(screen.queryByText(/no documented allergy|tidak ada catatan alergi/i)).not.toBeInTheDocument();
  });

  it("does not destroy a valid shell when summary returns 403", async () => {
    authenticateStaff();
    installChartFetch({
      onChart: (call) => {
        if (call.url.includes("/summary")) {
          return jsonResponse({ error: { code: "permission_denied" } }, 403);
        }
        return jsonResponse(shell());
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    expect(await screen.findByTestId("patient-safety-banner")).toHaveTextContent("Ada");
    expect(await screen.findByText(/not available|tidak tersedia/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /conditions|kondisi/i })).toBeInTheDocument();
  });

  it("stops fan-out on shell 422", async () => {
    authenticateStaff();
    const { calls } = installChartFetch({
      onChart: () => jsonResponse({ error: { code: "validation" } }, 422),
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    expect(await screen.findByTestId("chart-shell-error")).toBeInTheDocument();
    expect(calls.some((call) => call.url.includes("/summary"))).toBe(false);
    expect(screen.queryByText(JSON.stringify({ patientIdentityId: PATIENT_A }))).not.toBeInTheDocument();
  });

  it("fails closed on a drifted header instead of rendering a misleading banner", async () => {
    authenticateStaff();
    const { calls } = installChartFetch({
      onChart: (call) => {
        if (isShellUrl(call.url)) {
          return jsonResponse({
            requested_patient_identity_id: PATIENT_A,
            canonical_patient_identity_id: PATIENT_A,
            authorized_sections: ["conditions"],
            header: { given_name: "Misbound", family_name: "Identity" },
          });
        }
        return jsonResponse(summary());
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    expect(await screen.findByTestId("chart-shell-error")).toBeInTheDocument();
    expect(screen.queryByText("Misbound")).not.toBeInTheDocument();
    expect(calls.some((call) => call.url.includes("/summary"))).toBe(false);
  });
});

describe("clinical chart canonical and races", () => {
  it("applies a canonical merge once without a request storm", async () => {
    authenticateStaff();
    const { calls } = installChartFetch({
      onChart: (call) => {
        if (call.url.includes("/summary")) {
          return jsonResponse({
            requested_patient_identity_id: PATIENT_A,
            canonical_patient_identity_id: PATIENT_Y,
          });
        }
        return jsonResponse(
          shell({
            requested_patient_identity_id: PATIENT_A,
            canonical_patient_identity_id: PATIENT_Y,
            header: {
              requested_patient_identity_id: PATIENT_A,
              canonical_patient_identity_id: PATIENT_Y,
              family_name: "Canonical",
            },
          }),
        );
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    expect(await screen.findByText(/canonical patient identity|identitas pasien kanonik/i)).toBeInTheDocument();
    await waitFor(() => expect(getSelectedPatient()?.patientIdentityId).toBe(PATIENT_Y));
    await new Promise((resolve) => setTimeout(resolve, 80));
    expect(calls.filter((call) => isShellUrl(call.url))).toHaveLength(1);
    expect(calls.filter((call) => call.url.includes("/summary"))).toHaveLength(1);
  });

  it("ignores a stale canonical response after the user selected another patient", async () => {
    authenticateStaff();
    const lateA = deferred<Response>();
    installChartFetch({
      onChart: (call, init) => {
        if (isShellUrl(call.url) && call.url.includes(PATIENT_A)) {
          return listenAbort(init?.signal, lateA.promise);
        }
        if (call.url.includes("/summary")) {
          return jsonResponse({
            requested_patient_identity_id: PATIENT_B,
            canonical_patient_identity_id: PATIENT_B,
          });
        }
        return jsonResponse(
          shell({
            requested_patient_identity_id: PATIENT_B,
            canonical_patient_identity_id: PATIENT_B,
            header: { given_name: "Grace", family_name: "Hopper", display_label: NAME_B },
          }),
        );
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    selectPatient(PATIENT_B, NAME_B);
    expect(await screen.findByText(/Grace Hopper/)).toBeInTheDocument();
    lateA.resolve(
      jsonResponse(
        shell({
          requested_patient_identity_id: PATIENT_A,
          canonical_patient_identity_id: PATIENT_Y,
          header: {
            requested_patient_identity_id: PATIENT_A,
            canonical_patient_identity_id: PATIENT_Y,
            given_name: "STALE-CANONICAL",
            family_name: "Leak",
          },
        }),
      ),
    );
    await waitFor(() => {
      expect(getSelectedPatient()?.patientIdentityId).toBe(PATIENT_B);
      expect(screen.queryByText("STALE-CANONICAL")).not.toBeInTheDocument();
      expect(screen.queryByText(/canonical patient identity|identitas pasien kanonik/i)).not.toBeInTheDocument();
    });
  });

  it("discards Patient A shell, summary, and section after switching to B", async () => {
    authenticateStaff();
    const aShell = deferred<Response>();
    const aSummary = deferred<Response>();
    const aSection = deferred<Response>();
    installChartFetch({
      onChart: (call, init) => {
        const signal = init?.signal;
        if (isShellUrl(call.url) && call.url.includes(PATIENT_A)) {
          return listenAbort(signal, aShell.promise);
        }
        if (call.url.includes("/summary") && call.url.includes(PATIENT_A)) {
          return listenAbort(signal, aSummary.promise);
        }
        if (call.url.includes("/sections/conditions") && call.url.includes(PATIENT_A)) {
          return listenAbort(signal, aSection.promise);
        }
        if (call.url.includes("/summary")) {
          return jsonResponse({
            requested_patient_identity_id: PATIENT_B,
            canonical_patient_identity_id: PATIENT_B,
          });
        }
        if (call.url.includes("/sections/conditions")) {
          return jsonResponse({
            requested_patient_identity_id: PATIENT_B,
            canonical_patient_identity_id: PATIENT_B,
            section: "conditions",
            items: [{ id: "b1", code_display: "Condition-B" }],
            has_more: false,
          });
        }
        return jsonResponse(
          shell({
            requested_patient_identity_id: PATIENT_B,
            canonical_patient_identity_id: PATIENT_B,
            header: { given_name: "Grace", family_name: "Hopper" },
          }),
        );
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    selectPatient(PATIENT_B, NAME_B);
    expect(await screen.findByText(/Grace Hopper/)).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: /conditions|kondisi/i }));
    expect(await screen.findAllByText("Condition-B")).not.toHaveLength(0);
    aShell.resolve(jsonResponse(shell({ header: { given_name: "LATE-A-SHELL" } })));
    aSummary.resolve(
      jsonResponse(
        summary({
          active_conditions: [
            {
              source_type: "condition",
              source_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
              status: "ACTIVE",
              occurred_at: "2020-01-01T00:00:00Z",
              code_display: "LATE-A-SUMMARY",
            },
          ],
        }),
      ),
    );
    aSection.resolve(
      jsonResponse({
        requested_patient_identity_id: PATIENT_A,
        canonical_patient_identity_id: PATIENT_A,
        section: "conditions",
        items: [{ id: "a1", code_display: "LATE-A-SECTION" }],
        has_more: false,
      }),
    );
    await waitFor(() => {
      expect(screen.queryByText("LATE-A-SHELL")).not.toBeInTheDocument();
      expect(screen.queryByText("LATE-A-SUMMARY")).not.toBeInTheDocument();
      expect(screen.queryByText("LATE-A-SECTION")).not.toBeInTheDocument();
    });
    expect(getSelectedPatient()?.patientIdentityId).toBe(PATIENT_B);
    expect(clinicalCache().some((query) => String(query.queryKey[2]) === PATIENT_A)).toBe(false);
  });

  it("does not let the first A session populate a later A reselection", async () => {
    authenticateStaff();
    const firstA = deferred<Response>();
    let shells = 0;
    installChartFetch({
      onChart: (call, init) => {
        if (call.url.includes("/summary")) {
          return jsonResponse(summary());
        }
        if (isShellUrl(call.url)) {
          shells += 1;
          if (shells === 1) {
            return listenAbort(init?.signal, firstA.promise);
          }
          return jsonResponse(shell({ header: { given_name: "Second", family_name: "Ada" } }));
        }
        return jsonResponse(shell());
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await waitFor(() => expect(shells).toBe(1));
    closePatientAndWipeChart();
    expect(await screen.findByTestId("chart-patient-gate")).toBeInTheDocument();
    selectPatient(PATIENT_A, "Ada Again");
    expect(await screen.findByText(/Second Ada/)).toBeInTheDocument();
    firstA.resolve(jsonResponse(shell({ header: { given_name: "FIRST-A-SESSION" } })));
    await waitFor(() => expect(screen.queryByText("FIRST-A-SESSION")).not.toBeInTheDocument());
  });

  it("keeps the current generation usable after idle-cache cleanup", async () => {
    authenticateStaff();
    const token = clinicalChartCoordinator.begin();
    getRegisteredQueryClient()?.removeQueries({ queryKey: ["chart-idle", "shell"] });
    expect(clinicalChartCoordinator.isCurrent(token.generation)).toBe(true);
    authenticateStaff();
    const { calls } = installChartFetch();
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    await userEvent.click(await screen.findByRole("button", { name: /conditions|kondisi/i }));
    await waitFor(() => {
      expect(calls.some((call) => call.url.includes("/sections/conditions"))).toBe(true);
    });
    expect(screen.queryByText(/could not be loaded|tidak dapat dimuat/i)).not.toBeInTheDocument();
  });
});

describe("clinical chart timeline hardening", () => {
  it("passes an opaque cursor unchanged and serializes Load More", async () => {
    authenticateStaff();
    const secondPage = deferred<Response>();
    const { calls } = installChartFetch({
      onChart: (call, init) => {
        if (call.url.includes("/summary")) {
          return jsonResponse(summary());
        }
        if (call.url.includes("/timeline")) {
          if (call.url.includes("cursor=")) {
            return listenAbort(init?.signal, secondPage.promise);
          }
          return jsonResponse({
            requested_patient_identity_id: PATIENT_A,
            canonical_patient_identity_id: PATIENT_A,
            items: [
              {
                source_type: "condition",
                source_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
                occurred_at: "2020-01-01T00:00:00Z",
                organization_id: ORG_A,
                facility_id: null,
                canonical_patient_identity_id: PATIENT_A,
                source_patient_identity_id: PATIENT_A,
                status: "ACTIVE",
                code_display: "Page-1",
              },
            ],
            has_more: true,
            next_cursor: OPAQUE_CURSOR,
          });
        }
        return jsonResponse(shell());
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    await userEvent.click(await screen.findByRole("button", { name: /timeline|linimasa/i }));
    const loadMore = await screen.findByRole("button", { name: /load more|muat lebih/i });
    await userEvent.click(loadMore);
    await userEvent.click(loadMore);
    await waitFor(() => {
      expect(calls.filter((call) => call.url.includes("cursor="))).toHaveLength(1);
    });
    const cursorUrl = calls.find((call) => call.url.includes("cursor="))?.url ?? "";
    expect(new URL(cursorUrl, "http://localhost").searchParams.get("cursor")).toBe(OPAQUE_CURSOR);
    secondPage.resolve(
      jsonResponse({
        requested_patient_identity_id: PATIENT_A,
        canonical_patient_identity_id: PATIENT_A,
        items: [
          {
            source_type: "condition",
            source_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
            occurred_at: "2019-01-01T00:00:00Z",
            organization_id: ORG_A,
            facility_id: null,
            canonical_patient_identity_id: PATIENT_A,
            source_patient_identity_id: PATIENT_A,
            status: "ACTIVE",
            code_display: "Duplicate-overlap",
          },
          {
            source_type: "condition",
            source_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2",
            occurred_at: "2019-01-01T00:00:00Z",
            organization_id: ORG_A,
            facility_id: null,
            canonical_patient_identity_id: PATIENT_A,
            source_patient_identity_id: PATIENT_A,
            status: "ACTIVE",
            code_display: "Page-2",
          },
        ],
        has_more: false,
      }),
    );
    expect(await screen.findByText("Page-2")).toBeInTheDocument();
    expect(screen.getAllByText("Page-1")).toHaveLength(1);
    expect(screen.queryByText("Duplicate-overlap")).not.toBeInTheDocument();
  });

  it("keeps loaded timeline rows after a 422 cursor and does not retry", async () => {
    authenticateStaff();
    let timelineCalls = 0;
    installChartFetch({
      onChart: (call) => {
        if (call.url.includes("/summary")) {
          return jsonResponse(summary());
        }
        if (call.url.includes("/timeline")) {
          timelineCalls += 1;
          if (call.url.includes("cursor=")) {
            return jsonResponse({ error: { code: "validation" } }, 422);
          }
          return jsonResponse({
            requested_patient_identity_id: PATIENT_A,
            canonical_patient_identity_id: PATIENT_A,
            items: [
              {
                source_type: "condition",
                source_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
                occurred_at: "2020-01-01T00:00:00Z",
                organization_id: ORG_A,
                facility_id: null,
                canonical_patient_identity_id: PATIENT_A,
                source_patient_identity_id: PATIENT_A,
                status: "ACTIVE",
                code_display: "Kept-row",
              },
            ],
            has_more: true,
            next_cursor: "bad-cursor",
          });
        }
        return jsonResponse(shell());
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    await userEvent.click(await screen.findByRole("button", { name: /timeline|linimasa/i }));
    await userEvent.click(await screen.findByRole("button", { name: /load more|muat lebih/i }));
    expect(await screen.findByText(/paging could not continue|halaman linimasa tidak dapat/i)).toBeInTheDocument();
    expect(screen.getByText("Kept-row")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /conditions|kondisi/i })).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 40));
    expect(timelineCalls).toBe(2);
  });

  it("drops a late Patient A timeline page after switching to B", async () => {
    authenticateStaff();
    const aPage2 = deferred<Response>();
    installChartFetch({
      onChart: (call, init) => {
        if (call.url.includes("/summary")) {
          return jsonResponse({
            requested_patient_identity_id: call.url.includes(PATIENT_B) ? PATIENT_B : PATIENT_A,
            canonical_patient_identity_id: call.url.includes(PATIENT_B) ? PATIENT_B : PATIENT_A,
          });
        }
        if (call.url.includes("/timeline") && call.url.includes(PATIENT_A) && call.url.includes("cursor=")) {
          return listenAbort(init?.signal, aPage2.promise);
        }
        if (call.url.includes("/timeline")) {
          const forB = call.url.includes(PATIENT_B);
          return jsonResponse({
            requested_patient_identity_id: forB ? PATIENT_B : PATIENT_A,
            canonical_patient_identity_id: forB ? PATIENT_B : PATIENT_A,
            items: [
              {
                source_type: "condition",
                source_id: forB ? "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2" : "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
                occurred_at: "2020-01-01T00:00:00Z",
                organization_id: ORG_A,
                facility_id: null,
                canonical_patient_identity_id: forB ? PATIENT_B : PATIENT_A,
                source_patient_identity_id: forB ? PATIENT_B : PATIENT_A,
                status: "ACTIVE",
                code_display: forB ? "Timeline-B" : "Timeline-A",
              },
            ],
            has_more: !forB,
            next_cursor: forB ? null : "a-page-2",
          });
        }
        if (call.url.includes(PATIENT_B)) {
          return jsonResponse(
            shell({
              requested_patient_identity_id: PATIENT_B,
              canonical_patient_identity_id: PATIENT_B,
              header: { given_name: "Grace", family_name: "Hopper" },
            }),
          );
        }
        return jsonResponse(shell());
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    await userEvent.click(await screen.findByRole("button", { name: /timeline|linimasa/i }));
    await userEvent.click(await screen.findByRole("button", { name: /load more|muat lebih/i }));
    selectPatient(PATIENT_B, NAME_B);
    expect(await screen.findByText(/Grace Hopper/)).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: /timeline|linimasa/i }));
    expect(await screen.findByText("Timeline-B")).toBeInTheDocument();
    aPage2.resolve(
      jsonResponse({
        requested_patient_identity_id: PATIENT_A,
        canonical_patient_identity_id: PATIENT_A,
        items: [
          {
            source_type: "condition",
            source_id: "cccccccccccccccc-cccc-4ccc-8ccc-ccccccccccc3",
            occurred_at: "2019-01-01T00:00:00Z",
            organization_id: ORG_A,
            facility_id: null,
            canonical_patient_identity_id: PATIENT_A,
            source_patient_identity_id: PATIENT_A,
            status: "ACTIVE",
            code_display: "LATE-A-PAGE-2",
          },
        ],
        has_more: false,
      }),
    );
    await waitFor(() => expect(screen.queryByText("LATE-A-PAGE-2")).not.toBeInTheDocument());
  });
});

describe("clinical chart PHI wipe and cache keys", () => {
  it("removes every clinical QueryCache entry on Close Patient", async () => {
    authenticateStaff();
    installChartFetch({
      onChart: (call) => {
        if (call.url.includes("/summary")) {
          return jsonResponse(summary());
        }
        if (call.url.includes("/timeline")) {
          return jsonResponse({
            requested_patient_identity_id: PATIENT_A,
            canonical_patient_identity_id: PATIENT_A,
            items: [
              {
                source_type: "condition",
                source_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
                occurred_at: "2020-01-01T00:00:00Z",
                organization_id: ORG_A,
                facility_id: null,
                canonical_patient_identity_id: PATIENT_A,
                source_patient_identity_id: PATIENT_A,
                status: "ACTIVE",
              },
            ],
            has_more: true,
            next_cursor: "page-2",
          });
        }
        if (call.url.includes("/sections/")) {
          return jsonResponse({
            requested_patient_identity_id: PATIENT_A,
            canonical_patient_identity_id: PATIENT_A,
            section: call.url.split("/sections/")[1]?.split("?")[0],
            items: [{ id: "c1", code_display: "Cached-condition" }],
            has_more: false,
          });
        }
        return jsonResponse(shell());
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    await userEvent.click(await screen.findByRole("button", { name: /conditions|kondisi/i }));
    await screen.findAllByText("Cached-condition");
    await userEvent.click(await screen.findByRole("button", { name: /allergies|alergi/i }));
    await userEvent.click(await screen.findByRole("button", { name: /timeline|linimasa/i }));
    await screen.findByRole("button", { name: /load more|muat lebih/i });
    expect(clinicalCache().length).toBeGreaterThan(2);
    await userEvent.click(screen.getByRole("button", { name: /change patient|ganti pasien/i }));
    await waitFor(() => {
      expect(getSelectedPatient()).toBeNull();
      expect(clinicalCache()).toHaveLength(0);
    });
  });

  it("wipes previous-org clinical PHI on organization switch even if B context fails", async () => {
    authenticateStaff();
    sessionStorage.setItem("php.healthcare-web.organization-id", ORG_A);
    installChartFetch({
      organizations: [org(ORG_A, "Hospital A", ["CLINICIAN"]), org(ORG_B, "Hospital B", ["CLINICIAN"])],
    });
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (input, init) => {
      const url = String(input);
      const headers = new Headers(init?.headers);
      if (url.includes("/iam/me/context") && headers.get("X-Organization-Id") === ORG_B) {
        return jsonResponse({ error: { code: "server_error" } }, 500);
      }
      return originalFetch(input, init);
    };
    selectPatient(PATIENT_A, NAME_A, ORG_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    expect(clinicalCache().length).toBeGreaterThan(0);
    await userEvent.selectOptions(screen.getByLabelText(/switch organization|ganti organisasi/i), ORG_B);
    await waitFor(() => {
      expect(getSelectedPatient()).toBeNull();
      expect(clinicalCache()).toHaveLength(0);
      expect(screen.queryByText("Ada")).not.toBeInTheDocument();
    });
  });

  it("wipes selected patient and clinical cache on 401", async () => {
    authenticateStaff();
    installChartFetch();
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (input, init) => {
      const url = String(input);
      if (url.includes("/api/v1/clinical/")) {
        return jsonResponse({ error: { code: "unauthorized" } }, 401);
      }
      return originalFetch(input, init);
    };
    await userEvent.click(await screen.findByRole("button", { name: /conditions|kondisi/i }));
    expect(await screen.findByRole("heading", { name: /session expired|sesi berakhir/i })).toBeInTheDocument();
    expect(getSelectedPatient()).toBeNull();
    await waitFor(() => expect(clinicalCache()).toHaveLength(0));
    expect(screen.queryByTestId("clinical-chart")).not.toBeInTheDocument();
  });

  it("does not put MRN, name, or DOB in clinical query keys", async () => {
    authenticateStaff();
    installChartFetch();
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    const blob = JSON.stringify(clinicalCache().map((query) => query.queryKey));
    expect(blob).toContain(ORG_A);
    expect(blob).toContain(PATIENT_A);
    expect(blob).not.toContain(MRN_A);
    expect(blob).not.toContain(NAME_A);
    expect(blob).not.toContain("1815-12-10");
    expect(blob).not.toContain("NIK");
    expect(clinicalKeys.chart(ORG_A, PATIENT_A)).toEqual(["clinical-chart", ORG_A, PATIENT_A]);
  });
});

describe("clinical chart revocation, notes, labs, xss, a11y", () => {
  it("hides Conditions and drops cached PHI when a later shell omits the section", async () => {
    authenticateStaff();
    let includeConditions = true;
    installChartFetch({
      onChart: (call) => {
        if (call.url.includes("/summary")) {
          return jsonResponse(summary());
        }
        if (call.url.includes("/sections/conditions")) {
          return jsonResponse({
            requested_patient_identity_id: PATIENT_A,
            canonical_patient_identity_id: PATIENT_A,
            section: "conditions",
            items: [{ id: "c1", code_display: "Stale-condition" }],
            has_more: false,
          });
        }
        return jsonResponse(
          shell({
            authorized_sections: includeConditions
              ? ["conditions", "allergies", "medications"]
              : ["allergies", "medications"],
          }),
        );
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    await userEvent.click(await screen.findByRole("button", { name: /conditions|kondisi/i }));
    expect(await screen.findAllByText("Stale-condition")).not.toHaveLength(0);
    includeConditions = false;
    await getRegisteredQueryClient()?.refetchQueries({ queryKey: clinicalKeys.chart(ORG_A, PATIENT_A) });
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /conditions|kondisi/i })).not.toBeInTheDocument();
      expect(screen.queryByText("Stale-condition")).not.toBeInTheDocument();
      expect(screen.getByRole("heading", { name: /summary|ringkasan/i })).toBeInTheDocument();
    });
  });

  it("renders laboratory and notes without inventing nested data or loading note bodies", async () => {
    authenticateStaff();
    const { calls } = installChartFetch({
      onChart: (call) => {
        if (call.url.includes("/summary")) {
          return jsonResponse(summary());
        }
        if (call.url.includes("/sections/laboratory")) {
          return jsonResponse({
            requested_patient_identity_id: PATIENT_A,
            canonical_patient_identity_id: PATIENT_A,
            section: "laboratory",
            items: [{ id: "lab-1", code_display: "CBC" }],
            has_more: false,
          });
        }
        if (call.url.includes("/sections/notes")) {
          return jsonResponse({
            requested_patient_identity_id: PATIENT_A,
            canonical_patient_identity_id: PATIENT_A,
            section: "notes",
            items: [{ id: "n1", note_type: "PROGRESS", authored_at: "2020-01-01T00:00:00Z", body_text: "SECRET-BODY" }],
            has_more: false,
          });
        }
        if (call.url.includes("/sections/observations")) {
          return jsonResponse({
            requested_patient_identity_id: PATIENT_A,
            canonical_patient_identity_id: PATIENT_A,
            section: "observations",
            items: [
              { id: "v1", category: "VITAL_SIGNS", code_display: "Heart rate" },
              { id: "o1", category: "LABORATORY", code_display: "Sodium" },
            ],
            has_more: false,
          });
        }
        return jsonResponse(shell());
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    await userEvent.click(await screen.findByRole("button", { name: /laboratory|laboratorium/i }));
    expect(await screen.findAllByText("CBC")).not.toHaveLength(0);
    expect(screen.queryByText(/no documented records|tidak ada catatan terdokumentasi/i)).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: /notes|catatan/i }));
    expect(await screen.findByText(/metadata only|hanya judul/i)).toBeInTheDocument();
    expect(screen.queryByText("SECRET-BODY")).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: /observations|observasi/i }));
    expect(await screen.findAllByText("Heart rate")).not.toHaveLength(0);
    expect(screen.getAllByText("Sodium").length).toBeGreaterThan(0);
    expect(calls.some((call) => /\/api\/v1\/clinical\/notes\//.test(call.url))).toBe(false);
  });

  it("renders hostile clinical strings as text and keeps keyboard focus in the content region", async () => {
    authenticateStaff();
    installChartFetch({
      onChart: (call) => {
        if (call.url.includes("/summary")) {
          return jsonResponse({
            ...summary(),
            active_conditions: [
              {
                source_type: "condition",
                source_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
                status: "ACTIVE",
                occurred_at: "2020-01-01T00:00:00Z",
                code_display: XSS,
              },
            ],
            active_medications: [
              {
                source_type: "medication",
                source_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2",
                status: "ACTIVE",
                occurred_at: "2020-01-01T00:00:00Z",
                code_display: "<img src=x onerror=alert(1)>",
              },
            ],
          });
        }
        return jsonResponse(shell({ header: { given_name: XSS, family_name: "X" } }));
      },
    });
    selectPatient(PATIENT_A, XSS);
    renderApp(APP_PATHS.clinicalChart);
    const banner = await screen.findByTestId("patient-safety-banner");
    expect(banner).toHaveTextContent(XSS);
    expect(document.querySelector("script")).toBeNull();
    expect(document.querySelector("img[src='x']")).toBeNull();
    await userEvent.click(await screen.findByRole("button", { name: /conditions|kondisi/i }));
    await waitFor(() => {
      expect(document.activeElement).toHaveClass("chart-content");
    });
  });

  it("does not auto-page a large section payload", async () => {
    authenticateStaff();
    const { calls } = installChartFetch({
      onChart: (call) => {
        if (call.url.includes("/summary")) {
          return jsonResponse(summary());
        }
        if (call.url.includes("/sections/conditions")) {
          return jsonResponse({
            requested_patient_identity_id: PATIENT_A,
            canonical_patient_identity_id: PATIENT_A,
            section: "conditions",
            items: Array.from({ length: 50 }, (_, index) => ({
              id: `c-${index}`,
              code_display: `Condition-${index}`,
            })),
            has_more: true,
          });
        }
        return jsonResponse(shell());
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    await userEvent.click(await screen.findByRole("button", { name: /conditions|kondisi/i }));
    expect(await screen.findAllByText("Condition-0")).not.toHaveLength(0);
    await new Promise((resolve) => setTimeout(resolve, 40));
    expect(calls.filter((call) => call.url.includes("/sections/conditions"))).toHaveLength(1);
  });
});

describe("clinical chart privacy scans", () => {
  it("does not persist chart PHI, log it, or fabricate chart audits", async () => {
    authenticateStaff();
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const info = vi.spyOn(console, "info").mockImplementation(() => undefined);
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const error = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { calls } = installChartFetch();
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    expect(JSON.stringify(sessionStorage)).not.toContain(PATIENT_A);
    expect(JSON.stringify(localStorage)).not.toContain(NAME_A);
    expect(JSON.stringify(sessionStorage)).not.toContain(MRN_A);
    const logged = [...log.mock.calls, ...info.mock.calls, ...warn.mock.calls, ...error.mock.calls]
      .flat()
      .map(String)
      .join(" ");
    expect(logged).not.toContain(NAME_A);
    expect(logged).not.toContain(MRN_A);
    expect(calls.some((call) => call.url.includes("/audit"))).toBe(false);
    expect(parseApiError(500, { error: { message: NAME_A } }).message).not.toContain(NAME_A);
    log.mockRestore();
    info.mockRestore();
    warn.mockRestore();
    error.mockRestore();
  });

  it("keeps the chart route free of patient identifiers and forbids speculative clinical prefetch", () => {
    expect(APP_PATHS.clinicalChart).toBe("/app/clinical/chart");
    expect(APP_PATHS.clinicalChart).not.toContain(PATIENT_A);
    const root = join(dirname(fileURLToPath(import.meta.url)), "..");
    function walk(dir: string): string[] {
      return readdirSync(dir).flatMap((entry) => {
        const path = join(dir, entry);
        return statSync(path).isDirectory() ? walk(path) : path.endsWith(".ts") || path.endsWith(".tsx") ? [path] : [];
      });
    }
    const chartBlob = walk(join(root, "chart"))
      .filter((path) => !path.includes(".test."))
      .map((file) => readFileSync(file, "utf8"))
      .join("\n");
    expect(chartBlob).not.toMatch(/prefetchQuery|ensureQueryData/);
    expect(chartBlob).not.toMatch(/CLINICAL_CHART_ACCESSED/);
    expect(chartBlob).not.toMatch(/JSON\.parse\(.*cursor|atob\(/);
    expect(chartBlob).not.toMatch(/keepPreviousData/);
    expect(readFileSync(join(root, "../vite.config.ts"), "utf8")).toMatch(/sourcemap:\s*false/);
  });
});
