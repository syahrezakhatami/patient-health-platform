import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { CLINICAL_CHART_PURPOSE } from "../api/clinical";
import { CLINICAL_GC_TIME_MS, isClinicalQueryKey } from "../api/queryClient";
import { getRegisteredQueryClient } from "../auth/sessionLifecycle";
import { CHART_SECTION_ORDER, visibleAuthorizedSections } from "../chart/catalog";
import { clinicalQueryPolicy } from "../chart/queryPolicy";
import { selectPatientAndWipeChart } from "../chart/wipe";
import type { ChartSection, ChartShellResponse, ClinicalSummaryResponse, TimelinePageResponse } from "../api/generated/iam-shell";
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
const XSS_NAME = "<img src=x onerror=alert(1)>";
const MRN_A = "MRN-A-0001";
const NIK = "1234567890123456";

interface ChartCall {
  url: string;
  purpose: string | null;
  organizationId: string | null;
  facilityQuery: boolean;
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
    identity_kind: "STANDARD",
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
    authorized_sections: ["encounters", "conditions", "allergies", "medications", "notes"],
    header: header({
      requested_patient_identity_id: requested,
      canonical_patient_identity_id: canonical,
      ...headerOverrides,
    }) as ChartShellResponse["header"],
    ...rest,
  };
}

function summary(): ClinicalSummaryResponse {
  return {
    requested_patient_identity_id: PATIENT_A,
    canonical_patient_identity_id: PATIENT_A,
    active_conditions: [],
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
        } satisfies TimelinePageResponse);
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

describe("clinical chart ui", () => {
  it("does not call Clinical Read without a selected patient", async () => {
    authenticateStaff();
    const { calls } = installChartFetch();
    renderApp(APP_PATHS.clinicalChart);
    expect(await screen.findByTestId("chart-patient-gate")).toBeInTheDocument();
    expect(calls.filter((call) => call.url.includes("/clinical/patients"))).toHaveLength(0);
    expect(APP_PATHS.clinicalChart).toBe("/app/clinical/chart");
    expect(APP_PATHS.clinicalChart).not.toContain(PATIENT_A);
  });

  it("loads shell then summary with TREATMENT and no work-facility query filter", async () => {
    authenticateStaff();
    const { calls } = installChartFetch();
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    expect(await screen.findByTestId("clinical-chart")).toBeInTheDocument();
    await waitFor(() => {
      expect(calls.some((call) => isShellUrl(call.url))).toBe(true);
      expect(calls.some((call) => call.url.includes("/chart/summary"))).toBe(true);
    });
    const clinical = calls.filter((call) => call.url.includes("/clinical/patients"));
    expect(clinical.every((call) => call.purpose === CLINICAL_CHART_PURPOSE)).toBe(true);
    expect(clinical.every((call) => !call.facilityQuery)).toBe(true);
    expect(clinical.some((call) => call.url.includes("/sections/"))).toBe(false);
    expect(clinical.some((call) => call.url.includes("/timeline"))).toBe(false);
    expect(screen.getByRole("heading", { name: /summary|ringkasan/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^add$|^edit$|^order$/i })).not.toBeInTheDocument();
  });

  it("renders the safety banner without NIK/BPJS and keeps organization visible", async () => {
    authenticateStaff();
    installChartFetch();
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    const banner = await screen.findByTestId("patient-safety-banner");
    expect(banner).toHaveTextContent("Ada");
    expect(banner).toHaveTextContent(MRN_A);
    expect(banner).toHaveTextContent("1815-12-10");
    expect(banner).toHaveTextContent("30");
    expect(banner.textContent).not.toContain(NIK);
    expect(banner.textContent).not.toContain("BPJS");
    expect(screen.getByTestId("active-organization")).toHaveTextContent("Hospital A");
    expect(within(banner).getByText(/work facility|fasilitas kerja/i)).toBeInTheDocument();
  });

  it("uses authorized_sections for navigation and treats omitted allergies as unavailable", async () => {
    authenticateStaff();
    installChartFetch({
      onChart: (call) => {
        if (call.url.includes("/summary")) {
          return jsonResponse(summary());
        }
        if (call.url.endsWith("/chart")) {
          return jsonResponse(
            shell({
              authorized_sections: ["conditions"],
              header: { documented_allergy_exists: undefined },
            }),
          );
        }
        return jsonResponse({ error: { code: "not_found" } }, 404);
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    expect(await screen.findByRole("button", { name: /conditions|kondisi/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /allergies|alergi/i })).not.toBeInTheDocument();
    const allergy = await screen.findByTestId("allergy-safety");
    expect(allergy).toHaveTextContent(/not available|tidak tersedia/i);
    expect(allergy.textContent).not.toMatch(/no known allergies|tidak ada alergi/i);
  });

  it("distinguishes authorized empty allergies from unavailable", async () => {
    authenticateStaff();
    installChartFetch({
      onChart: (call) => {
        if (call.url.includes("/summary")) {
          return jsonResponse(summary());
        }
        if (call.url.endsWith("/chart")) {
          return jsonResponse(shell({ header: { documented_allergy_exists: false } }));
        }
        if (call.url.includes("/sections/allergies")) {
          return jsonResponse({
            requested_patient_identity_id: PATIENT_A,
            canonical_patient_identity_id: PATIENT_A,
            section: "allergies",
            items: [],
            has_more: false,
          });
        }
        return jsonResponse({ error: { code: "not_found" } }, 404);
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    const allergy = await screen.findByTestId("allergy-safety");
    expect(allergy).toHaveTextContent(/no documented allergy|tidak ada catatan alergi/i);
    await userEvent.click(await screen.findByRole("button", { name: /allergies|alergi/i }));
    expect(await screen.findByText(/no documented records|tidak ada catatan terdokumentasi/i)).toBeInTheDocument();
  });

  it("shows documented allergy when header is true", async () => {
    authenticateStaff();
    installChartFetch({
      onChart: (call) => {
        if (call.url.includes("/summary")) {
          return jsonResponse({
            ...summary(),
            active_allergies: [
              {
                source_type: "allergy",
                source_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
                status: "ACTIVE",
                occurred_at: "2020-01-01T00:00:00Z",
                code_display: "Peanut",
              },
            ],
          });
        }
        return jsonResponse(shell({ header: { documented_allergy_exists: true } }));
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    const allergy = await screen.findByTestId("allergy-safety");
    expect(allergy).toHaveTextContent(/documented allergy|catatan alergi yang terdokumentasi/i);
  });

  it("lazy-loads a section only after it is opened and keeps notes metadata-only", async () => {
    authenticateStaff();
    const { calls } = installChartFetch({
      onChart: (call) => {
        if (call.url.includes("/summary")) {
          return jsonResponse(summary());
        }
        if (call.url.includes("/sections/notes")) {
          return jsonResponse({
            requested_patient_identity_id: PATIENT_A,
            canonical_patient_identity_id: PATIENT_A,
            section: "notes",
            items: [{ id: "n1", note_type: "PROGRESS", authored_at: "2020-01-01T00:00:00Z", body_text: "SECRET" }],
            has_more: false,
          });
        }
        if (call.url.endsWith("/chart")) {
          return jsonResponse(shell());
        }
        return jsonResponse({ error: { code: "not_found" } }, 404);
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    await userEvent.click(await screen.findByRole("button", { name: /notes|catatan/i }));
    expect(await screen.findByText(/metadata only|hanya judul/i)).toBeInTheDocument();
    expect(screen.queryByText("SECRET")).not.toBeInTheDocument();
    expect(calls.some((call) => call.url.includes("/clinical/notes/"))).toBe(false);
    const sectionCalls = calls.filter((call) => call.url.includes("/sections/"));
    expect(sectionCalls).toHaveLength(1);
    expect(sectionCalls[0]?.url).toContain("/sections/notes");
  });

  it("loads timeline only when opened and uses Load More with an opaque cursor", async () => {
    authenticateStaff();
    const { calls } = installChartFetch({
      onChart: (call) => {
        if (call.url.includes("/summary")) {
          return jsonResponse(summary());
        }
        if (call.url.includes("/timeline")) {
          const second = call.url.includes("cursor=");
          return jsonResponse({
            requested_patient_identity_id: PATIENT_A,
            canonical_patient_identity_id: PATIENT_A,
            items: second
              ? [
                  {
                    source_type: "condition",
                    source_id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb2",
                    occurred_at: "2019-01-01T00:00:00Z",
                    organization_id: ORG_A,
                    facility_id: null,
                    canonical_patient_identity_id: PATIENT_A,
                    source_patient_identity_id: PATIENT_A,
                    status: "ACTIVE",
                  },
                ]
              : [
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
            has_more: !second,
            next_cursor: second ? null : "opaque-cursor-token",
          });
        }
        return jsonResponse(shell());
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    await userEvent.click(await screen.findByRole("button", { name: /timeline|linimasa/i }));
    expect(await screen.findByRole("button", { name: /load more|muat lebih/i })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /load more|muat lebih/i }));
    await waitFor(() => {
      expect(calls.filter((call) => call.url.includes("/timeline"))).toHaveLength(2);
    });
    expect(calls.some((call) => call.url.includes("cursor=opaque-cursor-token"))).toBe(true);
  });

  it("shows a safe 409 retired state", async () => {
    authenticateStaff();
    installChartFetch({
      onChart: () => jsonResponse({ error: { code: "identity_not_usable" } }, 409),
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    expect(await screen.findByTestId("chart-shell-error")).toHaveTextContent(/no longer available|tidak lagi tersedia/i);
  });

  it("shows a generic 404 unavailable state", async () => {
    authenticateStaff();
    installChartFetch({
      onChart: () => jsonResponse({ error: { code: "not_found" } }, 404),
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    expect(await screen.findByTestId("chart-shell-error")).toHaveTextContent(/not available|tidak tersedia/i);
  });

  it("updates selected patient to the canonical identity from a merged shell", async () => {
    authenticateStaff();
    installChartFetch({
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
    expect(await screen.findByText(/canonical patient identity|identitas pasien kanonik/i, {}, { timeout: 3000 })).toBeInTheDocument();
    await waitFor(() => {
      expect(getSelectedPatient()?.patientIdentityId).toBe(PATIENT_Y);
    });
  });

  it("closes the patient and returns to selection without leftover chart PHI", async () => {
    authenticateStaff();
    installChartFetch();
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    await userEvent.click(screen.getByRole("button", { name: /change patient|ganti pasien/i }));
    expect(await screen.findByRole("heading", { name: /select patient|pilih pasien/i })).toBeInTheDocument();
    expect(getSelectedPatient()).toBeNull();
    await waitFor(() => {
      const cache = getRegisteredQueryClient()?.getQueryCache().getAll() ?? [];
      expect(cache.some((query) => isClinicalQueryKey(query.queryKey))).toBe(false);
    });
  });

  it("escapes synthetic HTML in clinical text", async () => {
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
                code_display: XSS_NAME,
              },
            ],
          });
        }
        return jsonResponse(shell({ header: { given_name: XSS_NAME, family_name: "X" } }));
      },
    });
    selectPatient(PATIENT_A, XSS_NAME);
    renderApp(APP_PATHS.clinicalChart);
    expect(await screen.findByTestId("patient-safety-banner")).toHaveTextContent(XSS_NAME);
    expect(document.querySelector("img[src='x']")).toBeNull();
  });

  it("does not persist chart PHI in Web Storage or log it", async () => {
    authenticateStaff();
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const debug = vi.spyOn(console, "debug").mockImplementation(() => undefined);
    installChartFetch();
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    expect(JSON.stringify(sessionStorage)).not.toContain(NAME_A);
    expect(JSON.stringify(localStorage)).not.toContain(NAME_A);
    expect(JSON.stringify(sessionStorage)).not.toContain(PATIENT_A);
    expect(log.mock.calls.flat().join(" ")).not.toContain(NAME_A);
    expect(debug.mock.calls.flat().join(" ")).not.toContain(MRN_A);
    log.mockRestore();
    debug.mockRestore();
  });

  it("does not request summary or sections after a shell failure", async () => {
    authenticateStaff();
    const { calls } = installChartFetch({
      onChart: () => jsonResponse({ error: { code: "permission_denied" } }, 403),
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    expect(await screen.findByTestId("chart-shell-error")).toBeInTheDocument();
    expect(calls.some((call) => call.url.includes("/summary"))).toBe(false);
    expect(calls.some((call) => call.url.includes("/sections/"))).toBe(false);
    expect(calls.some((call) => call.url.includes("/timeline"))).toBe(false);
  });

  it("treats a later section 403 as unavailable, not empty", async () => {
    authenticateStaff();
    installChartFetch({
      onChart: (call) => {
        if (call.url.includes("/summary")) {
          return jsonResponse(summary());
        }
        if (call.url.includes("/sections/conditions")) {
          return jsonResponse({ error: { code: "permission_denied" } }, 403);
        }
        return jsonResponse(shell());
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    await userEvent.click(await screen.findByRole("button", { name: /conditions|kondisi/i }));
    expect(await screen.findByText(/not available|tidak tersedia/i)).toBeInTheDocument();
    expect(screen.queryByText(/no documented records|tidak ada catatan terdokumentasi/i)).not.toBeInTheDocument();
  });

  it("treats an allergy section load failure as error, not empty", async () => {
    authenticateStaff();
    installChartFetch({
      onChart: (call) => {
        if (call.url.includes("/summary")) {
          return jsonResponse(summary());
        }
        if (call.url.includes("/sections/allergies")) {
          return jsonResponse({ error: { code: "validation" } }, 422);
        }
        return jsonResponse(shell({ header: { documented_allergy_exists: true } }));
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    await userEvent.click(await screen.findByRole("button", { name: /allergies|alergi/i }));
    expect(await screen.findByText(/could not be loaded|tidak dapat dimuat/i)).toBeInTheDocument();
    expect(screen.queryByText(/no known allergies|tidak ada alergi/i)).not.toBeInTheDocument();
  });

  it("ignores unknown authorized_sections without crashing", async () => {
    authenticateStaff();
    installChartFetch({
      onChart: (call) => {
        if (call.url.includes("/summary")) {
          return jsonResponse(summary());
        }
        return jsonResponse(
          shell({
            authorized_sections: ["conditions", "not-a-real-section", "allergies"] as ChartShellResponse["authorized_sections"],
          }),
        );
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    expect(await screen.findByRole("button", { name: /conditions|kondisi/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /allergies|alergi/i })).toBeInTheDocument();
    expect(screen.queryByText("not-a-real-section")).not.toBeInTheDocument();
  });

  it("wipes chart PHI on logout", async () => {
    authenticateStaff();
    installChartFetch();
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    await userEvent.click(screen.getByRole("button", { name: /sign out|keluar/i }));
    expect(getSelectedPatient()).toBeNull();
    expect(screen.queryByText("Ada Lovelace")).not.toBeInTheDocument();
    await waitFor(() => {
      const cache = getRegisteredQueryClient()?.getQueryCache().getAll() ?? [];
      expect(cache.some((query) => isClinicalQueryKey(query.queryKey))).toBe(false);
    });
  });

  it("wipes selected patient and chart PHI on 401", async () => {
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
  });

  it("does not treat omitted summary lists as clinical absence", async () => {
    authenticateStaff();
    installChartFetch({
      onChart: (call) => {
        if (call.url.includes("/summary")) {
          return jsonResponse({
            requested_patient_identity_id: PATIENT_A,
            canonical_patient_identity_id: PATIENT_A,
          });
        }
        return jsonResponse(shell());
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    expect(await screen.findAllByText(/does not include this list|tidak menyertakan daftar/i)).not.toHaveLength(0);
    expect(screen.queryByText(/no documented records|tidak ada catatan terdokumentasi/i)).not.toBeInTheDocument();
  });
});

describe("clinical chart races", () => {
  it("keeps Patient B when Patient A shell returns last", async () => {
    authenticateStaff();
    const aShell = deferred<Response>();
    const { calls } = installChartFetch({
      onChart: (call, init) => {
        const signal = init?.signal;
        if (isShellUrl(call.url) && call.url.includes(PATIENT_A)) {
          return listenAbort(signal, aShell.promise);
        }
        if (call.url.includes("/summary")) {
          return jsonResponse({
            requested_patient_identity_id: PATIENT_B,
            canonical_patient_identity_id: PATIENT_B,
          });
        }
        if (isShellUrl(call.url) && call.url.includes(PATIENT_B)) {
          return jsonResponse(
            shell({
              requested_patient_identity_id: PATIENT_B,
              canonical_patient_identity_id: PATIENT_B,
              header: { given_name: "Grace", family_name: "Hopper", display_label: NAME_B },
            }),
          );
        }
        return jsonResponse(shell());
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await waitFor(() => {
      expect(calls.some((call) => call.url.includes(PATIENT_A))).toBe(true);
    });
    selectPatient(PATIENT_B, NAME_B);
    expect(await screen.findByText(/Grace Hopper/)).toBeInTheDocument();
    aShell.resolve(
      jsonResponse(
        shell({
          header: { given_name: "LATE-A", family_name: "Leak" },
        }),
      ),
    );
    await waitFor(() => {
      expect(screen.queryByText("LATE-A")).not.toBeInTheDocument();
    });
    expect(getSelectedPatient()?.patientIdentityId).toBe(PATIENT_B);
  });

  it("does not let a stale first-A response overwrite a newer second-A selection", async () => {
    authenticateStaff();
    let shellCount = 0;
    const firstA = deferred<Response>();
    installChartFetch({
      onChart: (call, init) => {
        const signal = init?.signal;
        if (call.url.includes("/summary")) {
          return jsonResponse(summary());
        }
        if (isShellUrl(call.url)) {
          shellCount += 1;
          if (shellCount === 1) {
            return listenAbort(signal, firstA.promise);
          }
          return jsonResponse(shell({ header: { given_name: "Second", family_name: "Ada" } }));
        }
        return jsonResponse(shell());
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await waitFor(() => expect(shellCount).toBeGreaterThan(0));
    selectPatient(PATIENT_A, "Ada Again");
    expect(await screen.findByText(/Second Ada/)).toBeInTheDocument();
    firstA.resolve(jsonResponse(shell({ header: { given_name: "FIRST-A" } })));
    await waitFor(() => {
      expect(screen.queryByText("FIRST-A")).not.toBeInTheDocument();
    });
  });

  it("discards a late Patient A section under Patient B", async () => {
    authenticateStaff();
    const aSection = deferred<Response>();
    installChartFetch({
      onChart: (call, init) => {
        const signal = init?.signal;
        if (call.url.includes("/summary")) {
          return jsonResponse(summary());
        }
        if (call.url.includes("/sections/conditions") && call.url.includes(PATIENT_A)) {
          return listenAbort(signal, aSection.promise);
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
    await userEvent.click(await screen.findByRole("button", { name: /conditions|kondisi/i }));
    selectPatient(PATIENT_B, NAME_B);
    await screen.findByText(/Grace Hopper/);
    await userEvent.click(await screen.findByRole("button", { name: /conditions|kondisi/i }));
    expect(await screen.findAllByText("Condition-B")).not.toHaveLength(0);
    aSection.resolve(
      jsonResponse({
        requested_patient_identity_id: PATIENT_A,
        canonical_patient_identity_id: PATIENT_A,
        section: "conditions",
        items: [{ id: "a1", code_display: "Condition-A-LEAK" }],
        has_more: false,
      }),
    );
    await waitFor(() => {
      expect(screen.queryByText("Condition-A-LEAK")).not.toBeInTheDocument();
    });
  });

  it("clears chart PHI on organization switch and does not restore it if B fails", async () => {
    authenticateStaff();
    sessionStorage.setItem("php.healthcare-web.organization-id", ORG_A);
    installChartFetch({
      organizations: [
        org(ORG_A, "Hospital A", ["CLINICIAN"]),
        org(ORG_B, "Hospital B", ["CLINICIAN"]),
      ],
      onChart: (call) => {
        if (call.url.includes("/summary")) {
          return jsonResponse(summary());
        }
        return jsonResponse(shell());
      },
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
    await userEvent.selectOptions(screen.getByLabelText(/switch organization|ganti organisasi/i), ORG_B);
    await waitFor(() => {
      expect(getSelectedPatient()).toBeNull();
      expect(screen.queryByText("Ada")).not.toBeInTheDocument();
    });
  });

  it("shows a safe timeline cursor error and does not retry it", async () => {
    authenticateStaff();
    let timelineCalls = 0;
    installChartFetch({
      onChart: (call) => {
        if (call.url.includes("/summary")) {
          return jsonResponse(summary());
        }
        if (call.url.includes("/timeline")) {
          timelineCalls += 1;
          return jsonResponse({ error: { code: "validation" } }, 422);
        }
        return jsonResponse(shell());
      },
    });
    selectPatient(PATIENT_A, NAME_A);
    renderApp(APP_PATHS.clinicalChart);
    await screen.findByTestId("clinical-chart");
    await userEvent.click(await screen.findByRole("button", { name: /timeline|linimasa/i }));
    expect(await screen.findByText(/paging could not continue|halaman linimasa tidak dapat/i)).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(timelineCalls).toBe(1);
  });
});

describe("clinical chart catalog and query policy", () => {
  it("covers every frozen section and ignores unknown slugs", () => {
    expect(CHART_SECTION_ORDER).toEqual([
      "encounters",
      "notes",
      "conditions",
      "observations",
      "laboratory",
      "medications",
      "allergies",
      "consents",
      "immunizations",
      "procedures",
      "medical-devices",
      "adverse-events",
      "family-histories",
    ]);
    expect(visibleAuthorizedSections([...CHART_SECTION_ORDER, "invented-section"])).toEqual([
      ...CHART_SECTION_ORDER,
    ]);
    expect(visibleAuthorizedSections(["allergies", "conditions"])).toEqual(["conditions", "allergies"]);
  });

  it("keeps clinical PHI queries memory-bounded without focus refetch", () => {
    expect(clinicalQueryPolicy.gcTime).toBeLessThanOrEqual(CLINICAL_GC_TIME_MS);
    expect(clinicalQueryPolicy.gcTime).toBeLessThanOrEqual(5 * 60_000);
    expect(clinicalQueryPolicy.refetchOnWindowFocus).toBe(false);
    expect(clinicalQueryPolicy.refetchOnReconnect).toBe(false);
  });
});
