import { describe, expect, it } from "vitest";

import { callbackHasOidcError, callbackLooksMalformed, stripOidcCallbackParams } from "../auth/callback";
import { completeLoginCallback } from "../auth/oidc";
import { safeReturnTo } from "../auth/returnTo";
import { getAccessToken, setAccessTokenForTests } from "../auth/tokenStore";

describe("callback and open-redirect hardening", () => {
  it("rejects external, protocol-relative, javascript, and encoded redirects", () => {
    expect(safeReturnTo("https://evil.example")).toBe("/app");
    expect(safeReturnTo("//evil.example")).toBe("/app");
    expect(safeReturnTo("javascript:alert(1)")).toBe("/app");
    expect(safeReturnTo("https%3A%2F%2Fevil.example%2Fphish")).toBe("/app");
    expect(safeReturnTo("%2F%2Fevil.example")).toBe("/app");
    expect(safeReturnTo("/login")).toBe("/app");
    expect(safeReturnTo("/app/clinical")).toBe("/app/clinical");
    expect(safeReturnTo("/select-organization")).toBe("/select-organization");
  });

  it("treats missing state/code as malformed and OIDC error as failed callback", () => {
    window.history.replaceState({}, "", "/auth/callback?code=abc");
    expect(callbackLooksMalformed()).toBe(true);
    window.history.replaceState({}, "", "/auth/callback?error=access_denied");
    expect(callbackHasOidcError()).toBe(true);
    expect(callbackLooksMalformed()).toBe(false);
  });

  it("strips OIDC callback parameters from the URL", () => {
    window.history.replaceState({}, "", "/auth/callback?code=secret-code&state=xyz&error_description=nope");
    stripOidcCallbackParams();
    expect(window.location.search).not.toContain("code=");
    expect(window.location.search).not.toContain("state=");
    expect(window.location.href).not.toContain("secret-code");
  });

  it("does not authenticate on malformed, error, or replayed callbacks", async () => {
    setAccessTokenForTests("pre-callback-token");
    window.history.replaceState({}, "", "/auth/callback?code=abc");
    await completeLoginCallback();
    expect(getAccessToken()).toBeNull();
    expect(window.location.search).not.toContain("code=");

    setAccessTokenForTests("pre-callback-token");
    window.history.replaceState({}, "", "/auth/callback?error=access_denied&error_description=nope");
    await completeLoginCallback();
    expect(getAccessToken()).toBeNull();
    expect(window.location.href).not.toContain("error_description");

    setAccessTokenForTests("pre-callback-token");
    window.history.replaceState({}, "", "/auth/callback?code=replayed&state=stale-state");
    await completeLoginCallback();
    expect(getAccessToken()).toBeNull();
  });
});
