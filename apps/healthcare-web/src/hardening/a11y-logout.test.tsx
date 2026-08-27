import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { getAccessToken } from "../auth/tokenStore";
import {
  clinicianPermissions,
  contextResponse,
  facilitiesResponse,
  org,
  ORG_A,
  organizationsResponse,
} from "../test/fixtures";
import { authenticateStaff, mockJsonFetch, renderApp } from "../test/render";

describe("accessibility and post-logout navigation", () => {
  it("exposes skip link and labeled context switchers", async () => {
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
    renderApp("/app");
    expect(await screen.findByTestId("active-organization")).toHaveTextContent("Hospital A");
    expect(screen.getByRole("link", { name: /skip to main content|lewati ke konten utama/i })).toHaveAttribute(
      "href",
      "#main-content",
    );
    expect(screen.getByLabelText(/language|bahasa/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /sign out|keluar/i })).toBeInTheDocument();
  });

  it("does not restore protected UI after logout when /app is opened again", async () => {
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
    const view = renderApp("/app");
    expect(await screen.findByTestId("active-organization")).toHaveTextContent("Hospital A");
    await userEvent.click(screen.getByRole("button", { name: /sign out|keluar/i }));
    expect(getAccessToken()).toBeNull();
    expect(await screen.findByRole("heading", { name: /staff sign-in|masuk staf/i })).toBeInTheDocument();
    view.unmount();
    renderApp("/app");
    expect(await screen.findByRole("heading", { name: /staff sign-in|masuk staf/i })).toBeInTheDocument();
    expect(screen.queryByTestId("active-organization")).not.toBeInTheDocument();
  });
});
