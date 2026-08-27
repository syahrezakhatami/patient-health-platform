import { describe, expect, it, vi } from "vitest";

import { inspectOidcClientSettings, peekOidcStatePersistence, resetUserManagerForTests } from "../auth/oidc";
import { purgeWebStorageTokenLeakage } from "../auth/sessionLifecycle";
import { InMemoryWebStorage, UserManager, WebStorageStateStore } from "oidc-client-ts";
import { getAccessToken, setAccessTokenForTests } from "../auth/tokenStore";

describe("OIDC storage hardening", () => {
  it("documents memory user store and sessionStorage handshake state", () => {
    expect(peekOidcStatePersistence()).toEqual({
      userStore: "memory",
      stateStore: "sessionStorage",
    });
  });

  it("configures Authorization Code + PKCE without a client secret", () => {
    vi.stubEnv("VITE_OIDC_ISSUER", "http://localhost:8080/realms/php-dev");
    vi.stubEnv("VITE_OIDC_CLIENT_ID", "php-healthcare-web");
    vi.stubEnv("VITE_OIDC_AUDIENCE", "php-api");
    resetUserManagerForTests();
    const settings = inspectOidcClientSettings();
    expect(settings.responseType).toBe("code");
    expect(settings.disablePKCE).toBe(false);
    expect(settings.authority).toBe("http://localhost:8080/realms/php-dev");
    expect(settings.clientId).toBe("php-healthcare-web");
    expect(settings.audience).toBe("php-api");
    expect(settings.clientSecretSet).toBe(false);
    expect(settings.automaticSilentRenew).toBe(false);
    expect(settings.silentRedirectConfigured).toBe(false);
  });

  it("does not persist access, refresh, or id tokens to Web Storage via userStore", async () => {
    const memory = new InMemoryWebStorage();
    const userStore = new WebStorageStateStore({ store: memory });
    const manager = new UserManager({
      authority: "http://localhost:8080/realms/php-dev",
      client_id: "php-healthcare-web",
      redirect_uri: "http://localhost:3000/auth/callback",
      response_type: "code",
      scope: "openid profile",
      userStore,
      stateStore: new WebStorageStateStore({ store: window.sessionStorage }),
    });
    const tokenBlob = JSON.stringify({
      access_token: "access.token.value",
      refresh_token: "refresh.token.value",
      id_token: "id.token.value",
    });
    await manager.settings.userStore.set("user", tokenBlob);
    expect(JSON.stringify(localStorage)).not.toContain("access.token.value");
    expect(JSON.stringify(sessionStorage)).not.toContain("refresh.token.value");
    expect(JSON.stringify(sessionStorage)).not.toContain("id.token.value");
    expect(await manager.settings.userStore.get("user")).toContain("access.token.value");
    expect(JSON.stringify(localStorage)).not.toContain("access.token.value");
  });

  it("purges leaked token JSON from Web Storage without moving tokens to localStorage", () => {
    sessionStorage.setItem("oidc.user:leak", JSON.stringify({ access_token: "leaked.access", refresh_token: "leaked.refresh" }));
    localStorage.setItem("should-not-hold-tokens", "ok");
    purgeWebStorageTokenLeakage();
    expect(sessionStorage.getItem("oidc.user:leak")).toBeNull();
    expect(localStorage.getItem("should-not-hold-tokens")).toBe("ok");
    expect(JSON.stringify(localStorage)).not.toContain("leaked.access");
  });

  it("keeps the application access token in process memory only", () => {
    setAccessTokenForTests("memory-only-access-token");
    expect(getAccessToken()).toBe("memory-only-access-token");
    expect(localStorage.getItem("memory-only-access-token")).toBeNull();
    expect(sessionStorage.getItem("memory-only-access-token")).toBeNull();
    expect(`${localStorage.getItem("oidc.user") ?? ""}`).not.toContain("memory-only-access-token");
  });
});
