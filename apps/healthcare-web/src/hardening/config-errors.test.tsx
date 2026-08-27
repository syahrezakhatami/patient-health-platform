import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { parseApiError, userFacingMessage } from "../api/errors";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { STAFF_AUDIENCE, validatePublicConfig, type PublicAppConfig } from "../config";

const valid: PublicAppConfig = {
  apiBaseUrl: "",
  oidcIssuer: "http://localhost:8080/realms/php-dev",
  oidcClientId: "php-healthcare-web",
  oidcRedirectUri: "http://localhost:3000/auth/callback",
  oidcSilentRedirectUri: "",
  oidcPostLogoutRedirectUri: "http://localhost:3000/login",
  oidcEndSessionUrl: "",
  oidcScope: "openid profile",
  oidcAudience: STAFF_AUDIENCE,
};

function Boom(): ReactNode {
  throw new Error("component boom Bearer aaa.bbb.ccc stack");
}

describe("config validation and safe errors", () => {
  it("rejects non-staff audiences, secret-shaped env, and missing production OIDC", () => {
    expect(() => validatePublicConfig(valid, true)).not.toThrow();
    expect(() => validatePublicConfig({ ...valid, oidcAudience: "php-patient" }, true)).toThrow(/php-api/);
    expect(() => validatePublicConfig({ ...valid, oidcClientId: "client-secret-value" }, true)).toThrow(
      /secret-shaped/,
    );
    expect(() => validatePublicConfig({ ...valid, oidcIssuer: "", oidcClientId: "" }, true)).toThrow(
      /VITE_OIDC/,
    );
  });

  it("does not render component stacks or tokens from the error boundary", () => {
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByRole("heading", { name: /something went wrong/i })).toBeInTheDocument();
    expect(screen.queryByText(/Bearer/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/aaa\.bbb\.ccc/)).not.toBeInTheDocument();
    errorSpy.mockRestore();
  });

  it("uses generic copy for timeout/network failures", () => {
    const mapped = parseApiError(0, { stack: "Error: timeout" });
    expect(mapped.message).toBe(userFacingMessage("network"));
    expect(mapped.message).not.toMatch(/timeout|stack/i);
  });
});
