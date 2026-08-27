import { describe, expect, it } from "vitest";

import { HEADER_CONTRACT_FAILURE, parseChartHeader } from "./header";

const REQUESTED = "11111111-1111-4111-8111-111111111111";
const CANONICAL = "22222222-2222-4222-8222-222222222222";

/** Representative SOURCE FastAPI PatientHeaderDTO JSON after the omit-null serializer. */
function frozenHeaderJson(overrides: Record<string, unknown> = {}) {
  return {
    requested_patient_identity_id: REQUESTED,
    canonical_patient_identity_id: CANONICAL,
    lifecycle_status: "ACTIVE",
    identity_kind: "PERSON",
    display_label: "Test Patient",
    given_name: "Test",
    family_name: "Patient",
    birth_date: "1990-01-01",
    age_years: 36,
    administrative_sex: null,
    mrn: ["MRN-1"],
    ...overrides,
  };
}

describe("chart header runtime contract", () => {
  it("parses the frozen source JSON shape including omitted allergy key", () => {
    const parsed = parseChartHeader(frozenHeaderJson(), REQUESTED, CANONICAL);
    expect(parsed).not.toBeNull();
    expect(parsed?.documentedAllergy).toBe("omitted");
    expect(parsed?.age_years).toBe(36);
    expect(parsed?.mrn).toEqual(["MRN-1"]);
    expect(parsed?.administrative_sex).toBeNull();
  });

  it("keeps documented_allergy_exists false distinct from omitted", () => {
    const parsed = parseChartHeader(
      frozenHeaderJson({ documented_allergy_exists: false }),
      REQUESTED,
      CANONICAL,
    );
    expect(parsed?.documentedAllergy).toBe("false");
  });

  it("keeps documented_allergy_exists true", () => {
    const parsed = parseChartHeader(
      frozenHeaderJson({ documented_allergy_exists: true }),
      REQUESTED,
      CANONICAL,
    );
    expect(parsed?.documentedAllergy).toBe("true");
  });

  it("fails when a critical field is renamed or missing", () => {
    const { canonical_patient_identity_id: _removed, ...rest } = frozenHeaderJson();
    expect(parseChartHeader(rest, REQUESTED, CANONICAL)).toBeNull();
    expect(HEADER_CONTRACT_FAILURE).toBe("chart_header_invalid");
  });

  it("fails when age_years is the wrong primitive type", () => {
    expect(parseChartHeader(frozenHeaderJson({ age_years: "36" }), REQUESTED, CANONICAL)).toBeNull();
  });

  it("fails when mrn is not a string array", () => {
    expect(parseChartHeader(frozenHeaderJson({ mrn: "MRN-1" }), REQUESTED, CANONICAL)).toBeNull();
  });

  it("fails when documented_allergy_exists is a non-boolean", () => {
    expect(
      parseChartHeader(frozenHeaderJson({ documented_allergy_exists: "yes" }), REQUESTED, CANONICAL),
    ).toBeNull();
  });

  it("fails when header identity ids do not match the shell envelope", () => {
    expect(
      parseChartHeader(frozenHeaderJson(), CANONICAL, REQUESTED),
    ).toBeNull();
  });

  it("accepts frozen age_years null and ignores omitted selected_encounter", () => {
    const parsed = parseChartHeader(
      frozenHeaderJson({ age_years: null, selected_encounter: undefined }),
      REQUESTED,
      CANONICAL,
    );
    expect(parsed?.age_years).toBeNull();
  });

  it("does not throw or embed PHI when the payload is hostile", () => {
    const hostile = {
      given_name: "SECRET-GIVEN",
      family_name: "SECRET-FAMILY",
      mrn: ["SECRET-MRN"],
      birth_date: "1815-12-10",
    };
    expect(() => parseChartHeader(hostile, REQUESTED, CANONICAL)).not.toThrow();
    expect(parseChartHeader(hostile, REQUESTED, CANONICAL)).toBeNull();
  });
});
