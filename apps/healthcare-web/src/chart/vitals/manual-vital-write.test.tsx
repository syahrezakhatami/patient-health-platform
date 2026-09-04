import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { APP_PATHS } from "../../routing/paths";
import { getRegisteredQueryClient } from "../../auth/sessionLifecycle";
import { clinicianCatalog } from "../../test/catalogPermissions";
import {
  contextResponse,
  FAC_1,
  FAC_2,
  facilitiesResponse,
  org,
  ORG_A,
  ORG_B,
  organizationsResponse,
} from "../../test/fixtures";
import { manualVitalKeys } from "../../api/queryClient";
import { authenticateStaff, renderApp } from "../../test/render";
import { selectPatientAndWipeChart } from "../wipe";

const PATIENT_A = "33333333-3333-4333-8333-333333333333";
const NAME_A = "Ada Lovelace";
const ENCOUNTER_A = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeee1";

const CATALOG_UNITS: Record<string, string> = {
  heart_rate: "beats/min",
  respiratory_rate: "breaths/min",
  body_temperature: "Cel",
  body_weight: "kg",
  body_height: "cm",
};

const FULL_CATALOG = [
  {
    measurement_key: "heart_rate",
    display_unit: "beats/min",
    canonical_concept: "Heart rate",
  },
  {
    measurement_key: "respiratory_rate",
    display_unit: "breaths/min",
    canonical_concept: "Respiratory rate",
  },
  {
    measurement_key: "body_temperature",
    display_unit: "Cel",
    canonical_concept: "Body temperature",
  },
  {
    measurement_key: "body_weight",
    display_unit: "kg",
    canonical_concept: "Body weight",
  },
  {
    measurement_key: "body_height",
    display_unit: "cm",
    canonical_concept: "Body height",
  },
];

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function selectPatient() {
  selectPatientAndWipeChart({
    patientIdentityId: PATIENT_A,
    organizationId: ORG_A,
    displayName: NAME_A,
    displayLabel: NAME_A,
    birthDate: "1815-12-10",
    administrativeSex: "FEMALE",
    organizationMrn: "MRN-A-0001",
    identityKind: "STANDARD",
    lifecycleStatus: "ACTIVE",
    selectedAt: new Date().toISOString(),
  });
}

function installFetch(options?: {
  writeContext?: Record<string, unknown> | (() => Record<string, unknown>);
  onPost?: (url: string, init?: RequestInit) => Response | null;
}): { posts: Array<{ url: string; body: unknown; idempotency: string | null }> } {
  const posts: Array<{ url: string; body: unknown; idempotency: string | null }> = [];
  const organizations = [org(ORG_A, "Hospital A", ["CLINICIAN"])];
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    if (url.includes("/iam/me/organizations")) {
      return jsonResponse(organizationsResponse(organizations));
    }
    if (url.includes("/iam/me/context")) {
      return jsonResponse(contextResponse(ORG_A, "Hospital A", clinicianCatalog));
    }
    if (url.includes("/facilities/accessible")) {
      return jsonResponse(facilitiesResponse(ORG_A));
    }
    if (url.includes("/manual-vitals/measurements") && String(init?.method ?? "GET") === "GET") {
      const context =
        typeof options?.writeContext === "function"
          ? options.writeContext()
          : options?.writeContext;
      return jsonResponse(
        context ?? {
          available: false,
          catalog_version: null,
          feature_version: null,
          measurements: [],
        },
      );
    }
    if (url.includes("/manual-vitals/measurements") && init?.method === "POST") {
      const headers = new Headers(init.headers);
      posts.push({
        url,
        body: JSON.parse(String(init.body)),
        idempotency: headers.get("Idempotency-Key"),
      });
      const override = options?.onPost?.(url, init);
      if (override) {
        return override;
      }
      return jsonResponse({ id: "obs-1", category: "VITAL_SIGNS", status: "FINAL" });
    }
    if (url.includes("/sections/encounters")) {
      return jsonResponse({
        requested_patient_identity_id: PATIENT_A,
        canonical_patient_identity_id: PATIENT_A,
        section: "encounters",
        items: [
          {
            id: ENCOUNTER_A,
            encounter_class: "AMB",
            status: "IN_PROGRESS",
            display_label: "ENC-A",
            started_at: "2020-01-01T00:00:00Z",
            ended_at: null,
            facility_id: null,
          },
        ],
        has_more: false,
      });
    }
    if (url.includes("/sections/observations")) {
      return jsonResponse({
        requested_patient_identity_id: PATIENT_A,
        canonical_patient_identity_id: PATIENT_A,
        section: "observations",
        items: [],
        has_more: false,
      });
    }
    if (url.includes("/chart/summary")) {
      return jsonResponse({
        requested_patient_identity_id: PATIENT_A,
        canonical_patient_identity_id: PATIENT_A,
      });
    }
    if (url.includes("/chart/timeline")) {
      return jsonResponse({
        requested_patient_identity_id: PATIENT_A,
        canonical_patient_identity_id: PATIENT_A,
        items: [],
        has_more: false,
      });
    }
    if (url.includes("/chart") && url.includes("/clinical/patients")) {
      return jsonResponse({
        requested_patient_identity_id: PATIENT_A,
        canonical_patient_identity_id: PATIENT_A,
        authorized_sections: ["encounters", "observations"],
        header: {
          requested_patient_identity_id: PATIENT_A,
          canonical_patient_identity_id: PATIENT_A,
          lifecycle_status: "ACTIVE",
          identity_kind: "STANDARD",
          display_label: NAME_A,
          given_name: "Ada",
          family_name: "Lovelace",
          birth_date: "1815-12-10",
          age_years: 30,
          administrative_sex: "FEMALE",
          mrn: ["MRN-A-0001"],
          documented_allergy_exists: false,
        },
      });
    }
    return jsonResponse({});
  };
  return { posts };
}

describe("manual vital write form", () => {
  it("hides the form when manual vitals are unavailable", async () => {
    installFetch();
    authenticateStaff();
    selectPatient();
    const user = userEvent.setup();
    const view = renderApp(APP_PATHS.clinicalChart);
    await user.click(await screen.findByRole("button", { name: /observations|observasi/i }));
    await waitFor(() => {
      expect(screen.queryByText(/record manual vital sign/i)).not.toBeInTheDocument();
    });
    view.unmount();
  });

  it("shows only backend-approved measurements in subset context", async () => {
    installFetch({
      writeContext: {
        available: true,
        catalog_version: "manual-vitals-mvp-v1",
        feature_version: "1.0.0",
        measurements: [
          {
            measurement_key: "heart_rate",
            display_unit: "beats/min",
            canonical_concept: "Heart rate",
          },
          {
            measurement_key: "body_temperature",
            display_unit: "Cel",
            canonical_concept: "Body temperature",
          },
        ],
      },
    });
    authenticateStaff();
    selectPatient();
    const user = userEvent.setup();
    const view = renderApp(APP_PATHS.clinicalChart);
    await user.click(await screen.findByRole("button", { name: /observations|observasi/i }));
    expect(await screen.findByText(/record manual vital sign/i)).toBeInTheDocument();
    const measurementSelect = await screen.findByLabelText(/^measurement$/i);
    const optionValues = Array.from(measurementSelect.querySelectorAll("option")).map(
      (option) => option.getAttribute("value"),
    );
    expect(optionValues).toEqual(expect.arrayContaining(["heart_rate", "body_temperature"]));
    expect(optionValues).toHaveLength(2);
    expect(screen.queryByText("kg")).not.toBeInTheDocument();
    view.unmount();
  });

  it("clears entered value when patient context changes", async () => {
    installFetch({
      writeContext: {
        available: true,
        catalog_version: "manual-vitals-mvp-v1",
        feature_version: "1.0.0",
        measurements: [
          {
            measurement_key: "heart_rate",
            display_unit: "beats/min",
            canonical_concept: "Heart rate",
          },
        ],
      },
    });
    authenticateStaff();
    selectPatient();
    const user = userEvent.setup();
    const view = renderApp(APP_PATHS.clinicalChart);
    await user.click(await screen.findByRole("button", { name: /observations|observasi/i }));
    expect(await screen.findByText(/record manual vital sign/i)).toBeInTheDocument();
    const valueInput = screen.getByLabelText(/^value$/i);
    await user.clear(valueInput);
    await user.type(valueInput, "88");
    selectPatientAndWipeChart({
      patientIdentityId: "44444444-4444-4444-8444-444444444444",
      organizationId: ORG_A,
      displayName: "Grace Hopper",
      displayLabel: "Grace Hopper",
      birthDate: "1906-12-09",
      administrativeSex: "FEMALE",
      organizationMrn: "MRN-A-0002",
      identityKind: "STANDARD",
      lifecycleStatus: "ACTIVE",
      selectedAt: new Date().toISOString(),
    });
    await waitFor(() => {
      expect(screen.queryByDisplayValue("88")).not.toBeInTheDocument();
    });
    view.unmount();
  });

  it("reuses idempotency key only for the same logical submit", async () => {
    const { posts } = installFetch({
      writeContext: {
        available: true,
        catalog_version: "manual-vitals-mvp-v1",
        feature_version: "1.0.0",
        measurements: [
          {
            measurement_key: "heart_rate",
            display_unit: "beats/min",
            canonical_concept: "Heart rate",
          },
        ],
      },
      onPost: () => jsonResponse({ detail: "server error" }, 500),
    });
    authenticateStaff();
    selectPatient();
    const user = userEvent.setup();
    const view = renderApp(APP_PATHS.clinicalChart);
    await user.click(await screen.findByRole("button", { name: /observations|observasi/i }));
    expect(await screen.findByText(/record manual vital sign/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByLabelText(/encounter/i).querySelectorAll("option").length).toBeGreaterThan(1);
    });
    await user.selectOptions(screen.getByLabelText(/encounter/i), ENCOUNTER_A);
    await user.clear(screen.getByLabelText(/^value$/i));
    await user.type(screen.getByLabelText(/^value$/i), "72");
    await user.click(screen.getByRole("button", { name: /save measurement/i }));
    await waitFor(() => {
      expect(posts).toHaveLength(1);
    });
    const firstKey = posts[0]?.idempotency;
    await user.click(screen.getByRole("button", { name: /save measurement/i }));
    await waitFor(() => {
      expect(posts).toHaveLength(2);
    });
    expect(posts[1]?.idempotency).toBe(firstKey);
    view.unmount();
  });

  it("invalidates observation reads after successful submit", async () => {
    installFetch({
      writeContext: {
        available: true,
        catalog_version: "manual-vitals-mvp-v1",
        feature_version: "1.0.0",
        measurements: [
          {
            measurement_key: "heart_rate",
            display_unit: "beats/min",
            canonical_concept: "Heart rate",
          },
        ],
      },
    });
    authenticateStaff();
    selectPatient();
    const user = userEvent.setup();
    const view = renderApp(APP_PATHS.clinicalChart);
    const queryClient = getRegisteredQueryClient();
    expect(queryClient).toBeTruthy();
    const invalidateSpy = vi
      .spyOn(queryClient!, "invalidateQueries")
      .mockResolvedValue(undefined as never);
    await user.click(await screen.findByRole("button", { name: /observations|observasi/i }));
    expect(await screen.findByText(/record manual vital sign/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByLabelText(/encounter/i).querySelectorAll("option").length).toBeGreaterThan(1);
    });
    await user.selectOptions(screen.getByLabelText(/encounter/i), ENCOUNTER_A);
    await user.clear(screen.getByLabelText(/^value$/i));
    await user.type(screen.getByLabelText(/^value$/i), "72");
    await user.click(screen.getByRole("button", { name: /save measurement/i }));
    await waitFor(() => {
      expect(invalidateSpy.mock.calls.length).toBeGreaterThan(0);
    });
    const keys = invalidateSpy.mock.calls.map(([args]) => JSON.stringify(args?.queryKey));
    expect(keys.some((entry) => entry.includes("observations"))).toBe(true);
    expect(keys.some((entry) => entry.includes("timeline"))).toBe(true);
    expect(keys.some((entry) => entry.includes("summary"))).toBe(true);
    invalidateSpy.mockRestore();
    view.unmount();
  });

  it("shows approved measurements and submits one measurement", async () => {
    const { posts } = installFetch({
      writeContext: {
        available: true,
        catalog_version: "manual-vitals-mvp-v1",
        feature_version: "1.0.0",
        measurements: [
          {
            measurement_key: "heart_rate",
            display_unit: "beats/min",
            canonical_concept: "Heart rate",
          },
        ],
      },
    });
    authenticateStaff();
    selectPatient();
    const user = userEvent.setup();
    const view = renderApp(APP_PATHS.clinicalChart);
    await user.click(await screen.findByRole("button", { name: /observations|observasi/i }));
    expect(await screen.findByText(/record manual vital sign/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByLabelText(/^measurement$/i)).toHaveValue("heart_rate");
    });
    expect(screen.getByText("beats/min")).toBeInTheDocument();
    expect(screen.queryByText("Cel")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByLabelText(/encounter/i).querySelectorAll("option").length).toBeGreaterThan(1);
    });
    await user.selectOptions(screen.getByLabelText(/encounter/i), ENCOUNTER_A);
    await user.clear(screen.getByLabelText(/^value$/i));
    await user.type(screen.getByLabelText(/^value$/i), "72");
    await user.click(screen.getByRole("button", { name: /save measurement/i }));
    await waitFor(() => {
      expect(posts).toHaveLength(1);
    });
    expect(posts[0]?.body).toMatchObject({
      expected_patient_identity_id: PATIENT_A,
      encounter_id: ENCOUNTER_A,
      measurement_key: "heart_rate",
      value: "72",
    });
    expect(posts[0]?.idempotency).toBeTruthy();
    view.unmount();
  });

  it("ignores stale write context when patient changes before response arrives", async () => {
    let resolveContext: ((value: Response) => void) | null = null;
    const contextPromise = new Promise<Response>((resolve) => {
      resolveContext = resolve;
    });
    installFetch({
      writeContext: {
        available: true,
        catalog_version: "manual-vitals-mvp-v1",
        feature_version: "1.0.0",
        measurements: [
          {
            measurement_key: "heart_rate",
            display_unit: "beats/min",
            canonical_concept: "Heart rate",
          },
        ],
      },
    });
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (input, init) => {
      const url = String(input);
      if (url.includes("/manual-vitals/measurements") && String(init?.method ?? "GET") === "GET") {
        return contextPromise;
      }
      return originalFetch(input, init);
    };
    authenticateStaff();
    selectPatient();
    const user = userEvent.setup();
    const view = renderApp(APP_PATHS.clinicalChart);
    await user.click(await screen.findByRole("button", { name: /observations|observasi/i }));
    selectPatientAndWipeChart({
      patientIdentityId: "44444444-4444-4444-8444-444444444444",
      organizationId: ORG_A,
      displayName: "Grace Hopper",
      displayLabel: "Grace Hopper",
      birthDate: "1906-12-09",
      administrativeSex: "FEMALE",
      organizationMrn: "MRN-A-0002",
      identityKind: "STANDARD",
      lifecycleStatus: "ACTIVE",
      selectedAt: new Date().toISOString(),
    });
    resolveContext!(
      jsonResponse({
        available: true,
        catalog_version: "manual-vitals-mvp-v1",
        feature_version: "1.0.0",
        measurements: [
          {
            measurement_key: "heart_rate",
            display_unit: "beats/min",
            canonical_concept: "Heart rate",
          },
        ],
      }),
    );
    await waitFor(() => {
      expect(screen.queryByText(/record manual vital sign/i)).not.toBeInTheDocument();
    });
    globalThis.fetch = originalFetch;
    view.unmount();
  });

  it("clears form state when organization context changes", async () => {
    const ORG_B = "55555555-5555-4555-8555-555555555555";
    installFetch({
      writeContext: {
        available: true,
        catalog_version: "manual-vitals-mvp-v1",
        feature_version: "1.0.0",
        measurements: [
          {
            measurement_key: "heart_rate",
            display_unit: "beats/min",
            canonical_concept: "Heart rate",
          },
        ],
      },
    });
    authenticateStaff();
    selectPatient();
    const user = userEvent.setup();
    const view = renderApp(APP_PATHS.clinicalChart);
    await user.click(await screen.findByRole("button", { name: /observations|observasi/i }));
    expect(await screen.findByText(/record manual vital sign/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByLabelText(/encounter/i).querySelectorAll("option").length).toBeGreaterThan(1);
    });
    await user.selectOptions(screen.getByLabelText(/encounter/i), ENCOUNTER_A);
    await user.clear(screen.getByLabelText(/^value$/i));
    await user.type(screen.getByLabelText(/^value$/i), "77");
    selectPatientAndWipeChart({
      patientIdentityId: PATIENT_A,
      organizationId: ORG_B,
      displayName: NAME_A,
      displayLabel: NAME_A,
      birthDate: "1815-12-10",
      administrativeSex: "FEMALE",
      organizationMrn: "MRN-B-0001",
      identityKind: "STANDARD",
      lifecycleStatus: "ACTIVE",
      selectedAt: new Date().toISOString(),
    });
    await waitFor(() => {
      expect(screen.queryByDisplayValue("77")).not.toBeInTheDocument();
    });
    view.unmount();
  });

  it("binds first-paint measurement selection to that entry's unit", async () => {
    installFetch({
      writeContext: {
        available: true,
        catalog_version: "manual-vitals-mvp-v1",
        feature_version: "1.0.0",
        measurements: FULL_CATALOG,
      },
    });
    authenticateStaff();
    selectPatient();
    const user = userEvent.setup();
    const view = renderApp(APP_PATHS.clinicalChart);
    await user.click(await screen.findByRole("button", { name: /observations|observasi/i }));
    expect(await screen.findByText(/record manual vital sign/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByLabelText(/^measurement$/i)).toHaveValue("heart_rate");
    });
    const selectedKey = (screen.getByLabelText(/^measurement$/i) as HTMLSelectElement).value;
    const catalogEntry = FULL_CATALOG.find((item) => item.measurement_key === selectedKey);
    expect(catalogEntry).toEqual(FULL_CATALOG[0]);
    expect(catalogEntry?.display_unit).toBe(CATALOG_UNITS.heart_rate);
    expect(screen.getByText(catalogEntry!.display_unit)).toBeInTheDocument();
    for (const other of FULL_CATALOG) {
      if (other.measurement_key !== selectedKey) {
        expect(screen.queryByText(other.display_unit)).not.toBeInTheDocument();
      }
    }
    view.unmount();
  });

  it("updates the displayed unit from the same catalog entry when selection changes", async () => {
    installFetch({
      writeContext: {
        available: true,
        catalog_version: "manual-vitals-mvp-v1",
        feature_version: "1.0.0",
        measurements: FULL_CATALOG,
      },
    });
    authenticateStaff();
    selectPatient();
    const user = userEvent.setup();
    const view = renderApp(APP_PATHS.clinicalChart);
    await user.click(await screen.findByRole("button", { name: /observations|observasi/i }));
    const measurementSelect = await screen.findByLabelText(/^measurement$/i);
    await waitFor(() => {
      expect(measurementSelect).toHaveValue("heart_rate");
    });
    for (const entry of FULL_CATALOG) {
      await user.selectOptions(measurementSelect, entry.measurement_key);
      expect(measurementSelect).toHaveValue(entry.measurement_key);
      expect(screen.getByText(entry.display_unit)).toBeInTheDocument();
      for (const other of FULL_CATALOG) {
        if (other.measurement_key !== entry.measurement_key) {
          expect(screen.queryByText(other.display_unit)).not.toBeInTheDocument();
        }
      }
    }
    await user.selectOptions(measurementSelect, "heart_rate");
    await user.selectOptions(measurementSelect, "body_temperature");
    expect(measurementSelect).toHaveValue("body_temperature");
    expect(screen.getByText("Cel")).toBeInTheDocument();
    expect(screen.queryByText("beats/min")).not.toBeInTheDocument();
    view.unmount();
  });

  it("drops a previous measurement and unit when the site subset no longer includes it", async () => {
    let writeContext: Record<string, unknown> = {
      available: true,
      catalog_version: "manual-vitals-mvp-v1",
      feature_version: "1.0.0",
      measurements: [
        FULL_CATALOG[0],
        FULL_CATALOG[2],
      ],
    };
    installFetch({
      writeContext: () => writeContext,
    });
    authenticateStaff();
    selectPatient();
    const user = userEvent.setup();
    const view = renderApp(APP_PATHS.clinicalChart);
    await user.click(await screen.findByRole("button", { name: /observations|observasi/i }));
    const measurementSelect = await screen.findByLabelText(/^measurement$/i);
    await waitFor(() => {
      expect(measurementSelect).toHaveValue("heart_rate");
    });
    await user.selectOptions(measurementSelect, "heart_rate");
    expect(screen.getByText("beats/min")).toBeInTheDocument();
    writeContext = {
      available: true,
      catalog_version: "manual-vitals-mvp-v1",
      feature_version: "1.0.0",
      measurements: [FULL_CATALOG[2]],
    };
    const queryClient = getRegisteredQueryClient();
    await queryClient!.invalidateQueries({ queryKey: ["manual-vitals-write-context"] });
    await waitFor(() => {
      const select = screen.getByLabelText(/^measurement$/i);
      expect(select).toHaveValue("body_temperature");
      expect(screen.queryByText("beats/min")).not.toBeInTheDocument();
      expect(screen.getByText("Cel")).toBeInTheDocument();
      expect(
        Array.from(select.querySelectorAll("option")).map((option) => option.getAttribute("value")),
      ).not.toContain("heart_rate");
    });
    view.unmount();
  });

  it("isolates write-context cache by organization and facility", () => {
    expect(manualVitalKeys.writeContext(ORG_A, FAC_1)).not.toEqual(
      manualVitalKeys.writeContext(ORG_A, FAC_2),
    );
    expect(manualVitalKeys.writeContext(ORG_A, null)).not.toEqual(
      manualVitalKeys.writeContext(ORG_B, null),
    );
  });
});
