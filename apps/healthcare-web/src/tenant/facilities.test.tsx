import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { FACILITY_STORAGE_KEY } from "../tenant/tabStorage";
import { resolveWorkFacilityChoice } from "../tenant/facilityPolicy";
import {
  getChartFacilityFilterId,
  setChartFacilityFilterId,
  workFacilityMustNotBecomeChartFilter,
} from "../tenant/clinicalBoundary";
import {
  clinicianPermissions,
  contextResponse,
  FAC_1,
  FAC_2,
  facilitiesResponse,
  org,
  ORG_A,
  organizationsResponse,
} from "../test/fixtures";
import { authenticateStaff, mockJsonFetch, renderApp } from "../test/render";

const twoFacilities = [
  { id: FAC_1, name: "Site 1", code: "S1", facility_type: "HOSPITAL_SITE", status: "ACTIVE" },
  { id: FAC_2, name: "Site 2", code: "S2", facility_type: "HOSPITAL_SITE", status: "ACTIVE" },
];

describe("facility work context", () => {
  it("does not auto-select a facility for ALL_IN_ORGANIZATION", () => {
    expect(
      resolveWorkFacilityChoice({
        facilityScope: "ALL_IN_ORGANIZATION",
        workFacilityRequired: false,
        facilities: twoFacilities,
        storedFacilityId: null,
      }),
    ).toEqual({ kind: "unset" });
  });

  it("auto-selects EXPLICIT when exactly one facility is accessible", () => {
    expect(
      resolveWorkFacilityChoice({
        facilityScope: "EXPLICIT",
        workFacilityRequired: true,
        facilities: [twoFacilities[0]!],
        storedFacilityId: null,
      }),
    ).toEqual({ kind: "auto", facilityId: FAC_1 });
  });

  it("requires a choice when EXPLICIT has multiple facilities", () => {
    expect(
      resolveWorkFacilityChoice({
        facilityScope: "EXPLICIT",
        workFacilityRequired: true,
        facilities: twoFacilities,
        storedFacilityId: null,
      }).kind,
    ).toBe("choose");
  });

  it("renders an EXPLICIT single facility as the work context", async () => {
    authenticateStaff();
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
          body: facilitiesResponse(ORG_A, {
            facility_scope: "EXPLICIT",
            facilities: [twoFacilities[0]!],
          }),
        };
      }
      return null;
    });
    renderApp("/app");
    expect(await screen.findByTestId("active-work-facility")).toHaveTextContent("Site 1");
  });

  it("does not pick the first facility when several EXPLICIT facilities exist", async () => {
    authenticateStaff();
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
          body: facilitiesResponse(ORG_A, { facility_scope: "EXPLICIT", facilities: twoFacilities }),
        };
      }
      return null;
    });
    renderApp("/app");
    expect(await screen.findByRole("heading", { name: /select a work facility|pilih fasilitas kerja/i })).toBeInTheDocument();
    expect(screen.getByTestId("active-work-facility")).not.toHaveTextContent("Site 1");
    await userEvent.selectOptions(screen.getByLabelText(/work facility|fasilitas kerja/i), FAC_2);
    expect(screen.getByTestId("active-work-facility")).toHaveTextContent("Site 2");
  });

  it("keeps work facility independent from the chart facility filter", () => {
    setChartFacilityFilterId(null);
    expect(workFacilityMustNotBecomeChartFilter(FAC_1, getChartFacilityFilterId())).toBe(true);
    expect(sessionStorage.getItem(FACILITY_STORAGE_KEY)).toBeNull();
  });
});
