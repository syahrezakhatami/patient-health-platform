import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { getRegisteredQueryClient, triggerSessionExpired } from "../../auth/sessionLifecycle";
import { APP_PATHS } from "../../routing/paths";
import { clinicianCatalog } from "../../test/catalogPermissions";
import {
  contextResponse,
  facilitiesResponse,
  org,
  ORG_A,
  organizationsResponse,
} from "../../test/fixtures";
import { authenticateStaff, deferred, renderApp } from "../../test/render";
import { selectPatientAndWipeChart } from "../wipe";

const PATIENT_A = "33333333-3333-4333-8333-333333333333";
const PATIENT_B = "44444444-4444-4444-8444-444444444444";
const NAME_A = "Ada Lovelace";
const NAME_B = "Grace Hopper";
const ENCOUNTER_A = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee1";
const ENCOUNTER_B = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee2";
const NOTE_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbb1";
const XSS = "<img src=x onerror=alert(1)>";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function selectPatient(id: string, name: string, organizationId = ORG_A) {
  selectPatientAndWipeChart({
    patientIdentityId: id,
    organizationId,
    displayName: name,
    displayLabel: name,
    birthDate: "1815-12-10",
    administrativeSex: "FEMALE",
    organizationMrn: "MRN-A-0001",
    identityKind: "STANDARD",
    lifecycleStatus: "ACTIVE",
    selectedAt: new Date().toISOString(),
  });
}

function encounterItem(id = ENCOUNTER_A, label = "ENC-TEST") {
  return {
    id,
    encounter_class: "AMB",
    status: "IN_PROGRESS",
    display_label: label,
    started_at: "2020-01-01T00:00:00Z",
    ended_at: null,
    facility_id: null,
  };
}

function patientFromChartUrl(url: string): string | null {
  const match = url.match(/\/patients\/([0-9a-f-]+)\/chart/);
  return match?.[1] ?? null;
}

function installNoteFetch(options?: {
  onRequest?: (url: string, init?: RequestInit) => Promise<Response> | Response | null;
}): { posts: Array<{ url: string; body: unknown; idempotency: string | null }>; calls: Array<{ method: string; url: string }> } {
  const posts: Array<{ url: string; body: unknown; idempotency: string | null }> = [];
  const calls: Array<{ method: string; url: string }> = [];
  const organizations = [org(ORG_A, "Hospital A", ["CLINICIAN"])];
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    const headers = new Headers(init?.headers);
    calls.push({ method: String(init?.method ?? "GET"), url });
    if (options?.onRequest) {
      const override = await options.onRequest(url, init);
      if (override) {
        return override;
      }
    }
    if (url.includes("/iam/me/organizations")) {
      return jsonResponse(organizationsResponse(organizations));
    }
    if (url.includes("/iam/me/context")) {
      return jsonResponse(contextResponse(ORG_A, "Hospital A", clinicianCatalog));
    }
    if (url.includes("/facilities/accessible")) {
      return jsonResponse(facilitiesResponse(headers.get("X-Organization-Id") ?? ORG_A));
    }
    const chartPatient = patientFromChartUrl(url) ?? PATIENT_A;
    const chartName = chartPatient === PATIENT_B ? NAME_B : NAME_A;
    if (url.includes("/chart/summary")) {
      return jsonResponse({
        requested_patient_identity_id: chartPatient,
        canonical_patient_identity_id: chartPatient,
      });
    }
    if (url.includes("/chart/timeline")) {
      return jsonResponse({
        requested_patient_identity_id: chartPatient,
        canonical_patient_identity_id: chartPatient,
        items: [],
        has_more: false,
      });
    }
    if (url.includes("/sections/encounters")) {
      const items =
        chartPatient === PATIENT_B
          ? [encounterItem(ENCOUNTER_B, "ENC-B")]
          : chartPatient === PATIENT_A
            ? [encounterItem(ENCOUNTER_A)]
            : [];
      return jsonResponse({
        requested_patient_identity_id: chartPatient,
        canonical_patient_identity_id: chartPatient,
        section: "encounters",
        items,
        has_more: false,
      });
    }
    if (url.includes("/sections/notes")) {
      return jsonResponse({
        requested_patient_identity_id: chartPatient,
        canonical_patient_identity_id: chartPatient,
        section: "notes",
        items: [],
        has_more: false,
      });
    }
    if (url.includes("/chart") && url.includes("/clinical/patients")) {
      return jsonResponse({
        requested_patient_identity_id: chartPatient,
        canonical_patient_identity_id: chartPatient,
        authorized_sections: ["encounters", "notes"],
        header: {
          requested_patient_identity_id: chartPatient,
          canonical_patient_identity_id: chartPatient,
          lifecycle_status: "ACTIVE",
          identity_kind: "STANDARD",
          display_label: chartName,
          given_name: chartPatient === PATIENT_B ? "Grace" : "Ada",
          family_name: chartPatient === PATIENT_B ? "Hopper" : "Lovelace",
          birth_date: "1815-12-10",
          age_years: 30,
          administrative_sex: "FEMALE",
          mrn: chartPatient === PATIENT_B ? ["MRN-B-0001"] : ["MRN-A-0001"],
          documented_allergy_exists: false,
        },
      });
    }
    if (init?.method === "POST" && url.includes("/api/v1/clinical/notes")) {
      const raw = init.body ? String(init.body) : "{}";
      posts.push({
        url,
        body: JSON.parse(raw) as unknown,
        idempotency: headers.get("Idempotency-Key"),
      });
      return jsonResponse({
        id: NOTE_ID,
        patient_identity_id: PATIENT_A,
        encounter_id: ENCOUNTER_A,
        organization_id: ORG_A,
        facility_id: null,
        note_type: "PROGRESS",
        body_text: (JSON.parse(raw) as { body_text?: string }).body_text ?? "saved",
        record_status: url.includes("/finalize") ? "FINAL" : "DRAFT",
        version: url.includes("/finalize") ? 1 : raw.includes("expected_version") ? 2 : 1,
        authored_at: "2020-01-01T00:00:00Z",
        finalized_at: url.includes("/finalize") ? "2020-01-01T01:00:00Z" : null,
      });
    }
    return jsonResponse({ error: { code: "not_found" } }, 404);
  };
  return { posts, calls };
}

async function openNoteForm() {
  authenticateStaff();
  selectPatient(PATIENT_A, NAME_A);
  renderApp(APP_PATHS.clinicalChart);
  await screen.findByTestId("clinical-chart");
  await userEvent.click(await screen.findByRole("button", { name: /notes|catatan/i }));
  return screen.findByTestId("clinical-note-form");
}

describe("clinical note write form", () => {
  it("does not render the form without a selected patient", async () => {
    authenticateStaff();
    installNoteFetch();
    renderApp(APP_PATHS.clinicalChart);
    expect(await screen.findByTestId("chart-patient-gate")).toBeInTheDocument();
    expect(screen.queryByTestId("clinical-note-form")).not.toBeInTheDocument();
  });

  it("loads encounters from Clinical Read and saves a draft with a stable idempotency key", async () => {
    const { posts, calls } = installNoteFetch();
    await openNoteForm();
    expect(screen.getByTestId("patient-safety-banner")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText(/encounter|kunjungan/i), ENCOUNTER_A);
    await userEvent.selectOptions(screen.getByLabelText(/note type|jenis catatan/i), "ED");
    await userEvent.type(screen.getByLabelText(/note text|teks catatan/i), "Nyeri dada. 胸痛。");
    expect(screen.getByRole("button", { name: /save draft|simpan draf/i })).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: /save draft|simpan draf/i }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0]?.url).toMatch(/\/api\/v1\/clinical\/notes$/);
    expect(posts[0]?.idempotency).toMatch(/^[A-Za-z0-9._-]{8,128}$/);
    expect(posts[0]?.body).toMatchObject({
      expected_patient_identity_id: PATIENT_A,
      encounter_id: ENCOUNTER_A,
      note_type: "ED",
      body_text: "Nyeri dada. 胸痛。",
    });
    expect(screen.getByTestId("clinical-note-status")).toHaveTextContent(/draft|draf/i);
    await userEvent.type(screen.getByLabelText(/note text|teks catatan/i), " updated");
    await userEvent.click(screen.getByRole("button", { name: /save draft|simpan draf/i }));
    await waitFor(() => expect(posts).toHaveLength(2));
    expect(posts[1]?.url).toContain(`/api/v1/clinical/notes/${NOTE_ID}`);
    expect(posts[1]?.body).toMatchObject({ expected_version: 1 });
    expect(posts[1]?.idempotency).toBeNull();
    expect(posts.some((post) => post.url.includes("/entered-in-error"))).toBe(false);
    expect(
      calls.some(
        (call) =>
          call.method === "GET" && /\/api\/v1\/clinical\/notes\/[0-9a-f-]+$/i.test(call.url),
      ),
    ).toBe(false);
    expect(calls.some((call) => call.url.includes("/clinical/encounters") && !call.url.includes("/chart/sections/encounters"))).toBe(false);
  });

  it("requires explicit encounter selection and rejects empty body", async () => {
    installNoteFetch();
    await openNoteForm();
    expect(screen.getByRole("button", { name: /save draft|simpan draf/i })).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/note text|teks catatan/i), "   ");
    expect(screen.getByRole("button", { name: /save draft|simpan draf/i })).toBeDisabled();
  });

  it("does not autosave while typing", async () => {
    const { posts } = installNoteFetch();
    await openNoteForm();
    await userEvent.selectOptions(screen.getByLabelText(/encounter|kunjungan/i), ENCOUNTER_A);
    await userEvent.type(screen.getByLabelText(/note text|teks catatan/i), "typed without save");
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(posts).toHaveLength(0);
  });

  it("shows finalize confirmation and then a read-only final state", async () => {
    const { posts } = installNoteFetch();
    await openNoteForm();
    await userEvent.selectOptions(screen.getByLabelText(/encounter|kunjungan/i), ENCOUNTER_A);
    await userEvent.type(screen.getByLabelText(/note text|teks catatan/i), "Ready to sign");
    await userEvent.click(screen.getByRole("button", { name: /save draft|simpan draf/i }));
    await waitFor(() => expect(screen.getByRole("button", { name: /finalize|finalisasi/i })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: /finalize|finalisasi/i }));
    expect(await screen.findByRole("alertdialog")).toHaveTextContent(/cannot be edited|tidak dapat diedit/i);
    await userEvent.click(screen.getByRole("button", { name: /finalize note|finalisasi catatan/i }));
    await waitFor(() => expect(posts.some((post) => post.url.includes("/finalize"))).toBe(true));
    const finalize = posts.find((post) => post.url.includes("/finalize"));
    expect(finalize?.idempotency).toMatch(/^[A-Za-z0-9._-]{8,128}$/);
    expect(screen.getByTestId("clinical-note-status")).toHaveTextContent(/final/i);
    expect(screen.queryByRole("button", { name: /save draft|simpan draf/i })).not.toBeInTheDocument();
  });

  it("guards dirty change-patient, org switch, facility switch, and logout", async () => {
    installNoteFetch();
    await openNoteForm();
    await userEvent.selectOptions(screen.getByLabelText(/encounter|kunjungan/i), ENCOUNTER_A);
    await userEvent.type(screen.getByLabelText(/note text|teks catatan/i), "unsaved phi");
    await userEvent.click(screen.getByRole("button", { name: /change patient|ganti pasien/i }));
    expect(await screen.findByRole("alertdialog")).toHaveTextContent(/unsaved|belum disimpan/i);
    await userEvent.click(screen.getByRole("button", { name: /^stay$|^tetap$/i }));
    expect(screen.getByTestId("clinical-note-form")).toHaveTextContent("unsaved phi");
    await userEvent.click(screen.getByRole("button", { name: /change patient|ganti pasien/i }));
    await userEvent.click(await screen.findByRole("button", { name: /discard and continue|buang dan lanjutkan/i }));
    await waitFor(() => expect(screen.queryByTestId("clinical-note-form")).not.toBeInTheDocument());
  });

  it("wipes immediately on 401 without a confirmation dialog", async () => {
    installNoteFetch();
    await openNoteForm();
    await userEvent.selectOptions(screen.getByLabelText(/encounter|kunjungan/i), ENCOUNTER_A);
    await userEvent.type(screen.getByLabelText(/note text|teks catatan/i), "session phi");
    triggerSessionExpired("unauthorized");
    await waitFor(() => expect(screen.queryByTestId("clinical-note-form")).not.toBeInTheDocument());
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  });

  it("discards a late Patient A response after switching to Patient B", async () => {
    const pending = deferred<Response>();
    installNoteFetch({
      onRequest: (url, init) => {
        if (init?.method === "POST" && url.endsWith("/api/v1/clinical/notes")) {
          return pending.promise;
        }
        return null;
      },
    });
    await openNoteForm();
    await userEvent.selectOptions(screen.getByLabelText(/encounter|kunjungan/i), ENCOUNTER_A);
    await userEvent.type(screen.getByLabelText(/note text|teks catatan/i), "patient A body");
    await userEvent.click(screen.getByRole("button", { name: /save draft|simpan draf/i }));
    selectPatient(PATIENT_B, NAME_B);
    pending.resolve(
      jsonResponse({
        id: NOTE_ID,
        patient_identity_id: PATIENT_A,
        encounter_id: ENCOUNTER_A,
        organization_id: ORG_A,
        facility_id: null,
        note_type: "PROGRESS",
        body_text: "patient A body",
        record_status: "DRAFT",
        version: 1,
        authored_at: "2020-01-01T00:00:00Z",
        finalized_at: null,
      }),
    );
    await waitFor(() => expect(screen.queryByDisplayValue("patient A body")).not.toBeInTheDocument());
  });

  it("does not put note body in storage, query keys, or console", async () => {
    const log = vi.spyOn(console, "log").mockImplementation(() => undefined);
    const { posts } = installNoteFetch();
    await openNoteForm();
    await userEvent.selectOptions(screen.getByLabelText(/encounter|kunjungan/i), ENCOUNTER_A);
    const hostile = `${XSS} Nyeri`;
    await userEvent.type(screen.getByLabelText(/note text|teks catatan/i), hostile);
    await userEvent.click(screen.getByRole("button", { name: /save draft|simpan draf/i }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(window.localStorage.getItem("body_text")).toBeNull();
    expect(sessionStorage.getItem("body_text")).toBeNull();
    expect(window.location.href).not.toContain("Nyeri");
    const client = getRegisteredQueryClient();
    const keys = client?.getQueryCache().getAll().map((query) => JSON.stringify(query.queryKey)) ?? [];
    expect(keys.some((key) => key.includes("Nyeri") || key.includes("body_text"))).toBe(false);
    expect(log.mock.calls.flat().join(" ")).not.toContain("Nyeri");
    expect(screen.getByLabelText(/note text|teks catatan/i)).toHaveValue(hostile);
    expect(document.querySelector("img")).toBeNull();
    log.mockRestore();
  });

  it("shows a version conflict without merging text", async () => {
    installNoteFetch({
      onRequest: (url, init) => {
        if (init?.method === "POST" && url.includes(NOTE_ID) && !url.includes("finalize")) {
          return jsonResponse({ error: { code: "note_version_conflict", message: "conflict" } }, 409);
        }
        return null;
      },
    });
    await openNoteForm();
    await userEvent.selectOptions(screen.getByLabelText(/encounter|kunjungan/i), ENCOUNTER_A);
    await userEvent.type(screen.getByLabelText(/note text|teks catatan/i), "first save");
    await userEvent.click(screen.getByRole("button", { name: /save draft|simpan draf/i }));
    await waitFor(() => expect(screen.getByTestId("clinical-note-status")).toHaveTextContent(/draft|draf/i));
    await userEvent.type(screen.getByLabelText(/note text|teks catatan/i), " more");
    await userEvent.click(screen.getByRole("button", { name: /save draft|simpan draf/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/will not merge|tidak akan menggabungkan/i);
    expect(screen.getByLabelText(/note text|teks catatan/i)).toHaveValue("first save more");
  });

  it("disables save while a create is pending", async () => {
    const pending = deferred<Response>();
    installNoteFetch({
      onRequest: (url, init) => {
        if (init?.method === "POST" && url.endsWith("/api/v1/clinical/notes")) {
          return pending.promise;
        }
        return null;
      },
    });
    await openNoteForm();
    await userEvent.selectOptions(screen.getByLabelText(/encounter|kunjungan/i), ENCOUNTER_A);
    await userEvent.type(screen.getByLabelText(/note text|teks catatan/i), "pending body");
    await userEvent.click(screen.getByRole("button", { name: /save draft|simpan draf/i }));
    expect(screen.getByRole("button", { name: /saving|menyimpan/i })).toBeDisabled();
    pending.resolve(
      jsonResponse({
        id: NOTE_ID,
        patient_identity_id: PATIENT_A,
        encounter_id: ENCOUNTER_A,
        organization_id: ORG_A,
        facility_id: null,
        note_type: "PROGRESS",
        body_text: "pending body",
        record_status: "DRAFT",
        version: 1,
        authored_at: "2020-01-01T00:00:00Z",
        finalized_at: null,
      }),
    );
    await waitFor(() => expect(screen.getByRole("button", { name: /save draft|simpan draf/i })).toBeEnabled());
  });

  it("reuses the same create idempotency key after an ambiguous failure", async () => {
    const keys: string[] = [];
    let attempts = 0;
    installNoteFetch({
      onRequest: (url, init) => {
        if (init?.method === "POST" && String(url).endsWith("/api/v1/clinical/notes")) {
          keys.push(new Headers(init.headers).get("Idempotency-Key") ?? "");
          attempts += 1;
          if (attempts === 1) {
            return jsonResponse({ error: { code: "server_error", message: "upstream" } }, 500);
          }
        }
        return null;
      },
    });
    await openNoteForm();
    await userEvent.selectOptions(screen.getByLabelText(/encounter|kunjungan/i), ENCOUNTER_A);
    await userEvent.type(screen.getByLabelText(/note text|teks catatan/i), "retry body");
    await userEvent.click(screen.getByRole("button", { name: /save draft|simpan draf/i }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /save draft|simpan draf/i }));
    await waitFor(() => expect(keys).toHaveLength(2));
    expect(keys[0]).toBe(keys[1]);
    expect(keys[0]).toMatch(/^[A-Za-z0-9._-]{8,128}$/);
  });

  it("does not populate Patient B encounter picker with late Patient A encounters", async () => {
    const pending = deferred<Response>();
    installNoteFetch({
      onRequest: (url) => {
        if (url.includes(`/patients/${PATIENT_A}/chart/sections/encounters`)) {
          return pending.promise;
        }
        return null;
      },
    });
    await openNoteForm();
    selectPatient(PATIENT_B, NAME_B);
    await screen.findByTestId("clinical-chart");
    await userEvent.click(await screen.findByRole("button", { name: /notes|catatan/i }));
    await screen.findByTestId("clinical-note-form");
    pending.resolve(
      jsonResponse({
        requested_patient_identity_id: PATIENT_A,
        canonical_patient_identity_id: PATIENT_A,
        section: "encounters",
        items: [encounterItem(ENCOUNTER_A, "ENC-LATE-A")],
        has_more: false,
      }),
    );
    await waitFor(() => expect(screen.getByLabelText(/encounter|kunjungan/i)).toHaveTextContent("ENC-B"));
    expect(screen.getByLabelText(/encounter|kunjungan/i)).not.toHaveTextContent("ENC-LATE-A");
    expect(screen.getByLabelText(/encounter|kunjungan/i)).not.toHaveTextContent(ENCOUNTER_A);
  });

  it("keeps encounter unavailable distinct from an empty encounter list", async () => {
    installNoteFetch({
      onRequest: (url) => {
        if (url.includes("/sections/encounters")) {
          return jsonResponse({ error: { code: "permission_denied" } }, 403);
        }
        return null;
      },
    });
    await openNoteForm();
    expect(await screen.findByRole("alert")).toHaveTextContent(/could not be loaded|tidak dapat dimuat/i);
    expect(screen.queryByText(/no encounters are available|tidak ada kunjungan/i)).not.toBeInTheDocument();
  });

  it("guards browser Back while the note is dirty", async () => {
    installNoteFetch();
    await openNoteForm();
    await userEvent.selectOptions(screen.getByLabelText(/encounter|kunjungan/i), ENCOUNTER_A);
    await userEvent.type(screen.getByLabelText(/note text|teks catatan/i), "back guard body");
    window.dispatchEvent(new PopStateEvent("popstate"));
    expect(await screen.findByRole("alertdialog")).toHaveTextContent(/unsaved|belum disimpan/i);
    await userEvent.click(screen.getByRole("button", { name: /^stay$|^tetap$/i }));
    expect(screen.getByLabelText(/note text|teks catatan/i)).toHaveValue("back guard body");
  });

  it("shows a safe error on 403 and does not keep a note body in the mutation cache", async () => {
    const { calls } = installNoteFetch({
      onRequest: (url, init) => {
        if (init?.method === "POST" && String(url).endsWith("/api/v1/clinical/notes")) {
          return jsonResponse({ error: { code: "permission_denied", message: "Not authorized" } }, 403);
        }
        return null;
      },
    });
    await openNoteForm();
    await userEvent.selectOptions(screen.getByLabelText(/encounter|kunjungan/i), ENCOUNTER_A);
    await userEvent.type(screen.getByLabelText(/note text|teks catatan/i), "revoked facility body");
    await userEvent.click(screen.getByRole("button", { name: /save draft|simpan draf/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/no longer have access|tidak lagi memiliki akses/i);
    expect(screen.queryByTestId("clinical-note-status")).toHaveTextContent(/not saved|belum disimpan/i);
    const client = getRegisteredQueryClient();
    const mutationBlob = JSON.stringify(client?.getMutationCache().getAll() ?? []);
    expect(mutationBlob).not.toContain("revoked facility body");
    expect(
      calls.some((call) => call.method === "GET" && /\/api\/v1\/clinical\/notes\/[0-9a-f-]+$/i.test(call.url)),
    ).toBe(false);
  });

  it("invalidates captured Patient A reads without applying a late result to Patient B", async () => {
    const pending = deferred<Response>();
    const notesUrls: string[] = [];
    installNoteFetch({
      onRequest: (url, init) => {
        if (url.includes("/sections/notes")) {
          notesUrls.push(url);
        }
        if (init?.method === "POST" && String(url).endsWith("/api/v1/clinical/notes")) {
          return pending.promise;
        }
        return null;
      },
    });
    await openNoteForm();
    await userEvent.selectOptions(screen.getByLabelText(/encounter|kunjungan/i), ENCOUNTER_A);
    await userEvent.type(screen.getByLabelText(/note text|teks catatan/i), "patient A body");
    await userEvent.click(screen.getByRole("button", { name: /save draft|simpan draf/i }));
    selectPatient(PATIENT_B, NAME_B);
    await waitFor(() => expect(screen.queryByDisplayValue("patient A body")).not.toBeInTheDocument());
    await userEvent.click(await screen.findByRole("button", { name: /notes|catatan/i }));
    await screen.findByTestId("clinical-note-form");
    await waitFor(() => expect(notesUrls.some((url) => url.includes(PATIENT_B))).toBe(true));
    const notesBeforeB = notesUrls.filter((url) => url.includes(PATIENT_B)).length;
    pending.resolve(
      jsonResponse({
        id: NOTE_ID,
        patient_identity_id: PATIENT_A,
        encounter_id: ENCOUNTER_A,
        organization_id: ORG_A,
        facility_id: null,
        note_type: "PROGRESS",
        body_text: "patient A body",
        record_status: "DRAFT",
        version: 1,
        authored_at: "2020-01-01T00:00:00Z",
        finalized_at: null,
      }),
    );
    await waitFor(() => expect(screen.queryByDisplayValue("patient A body")).not.toBeInTheDocument());
    expect(screen.getByTestId("clinical-note-status")).not.toHaveTextContent(/draft|draf/i);
    const client = getRegisteredQueryClient();
    const mutationBlob = JSON.stringify(client?.getMutationCache().getAll() ?? []);
    expect(mutationBlob).not.toContain("patient A body");
    expect(notesUrls.filter((url) => url.includes(PATIENT_B)).length).toBe(notesBeforeB);
  });
});
