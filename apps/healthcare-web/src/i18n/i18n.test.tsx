import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { changeLocale } from "../i18n";
import { clinicianPermissions, contextResponse, facilitiesResponse, org, ORG_A, organizationsResponse } from "../test/fixtures";
import { authenticateStaff, mockJsonFetch, renderApp } from "../test/render";

describe("i18n", () => {
  it("renders Indonesian by default and can switch to English without changing authorization", async () => {
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
    await changeLocale("id");
    renderApp("/app");
    expect(await screen.findByTestId("active-organization")).toHaveTextContent("Hospital A");
    expect(screen.getByRole("link", { name: /klinis/i })).toBeInTheDocument();
    await changeLocale("en");
    expect(screen.getByRole("link", { name: /clinical/i })).toBeInTheDocument();
    expect(screen.getByTestId("active-organization")).toHaveTextContent("Hospital A");
  });
});
