import { Log, UserManager, WebStorageStateStore, InMemoryWebStorage, type User } from "oidc-client-ts";

import { assertStaffClientConfig, isOidcConfigured, readPublicConfig, STAFF_AUDIENCE } from "../config";
import { assertStaffAccessToken } from "./audience";
import { callbackHasOidcError, callbackLooksMalformed, stripOidcCallbackParams } from "./callback";
import { storeReturnTo } from "./returnTo";
import { purgeWebStorageTokenLeakage, triggerSessionExpired } from "./sessionLifecycle";
import { clearAccessToken, setAccessToken } from "./tokenStore";

Log.setLevel(Log.NONE);

let manager: UserManager | null = null;
let userMemoryStore: InMemoryWebStorage | null = null;
let loginRedirectInFlight = false;

export function getOidcUserMemoryStore(): InMemoryWebStorage | null {
  return userMemoryStore;
}

function applyUser(user: User | null): void {
  if (!user?.access_token) {
    clearAccessToken();
    return;
  }
  try {
    assertStaffAccessToken(user.access_token);
    setAccessToken(user.access_token);
  } catch {
    clearAccessToken();
    void manager?.removeUser();
    triggerSessionExpired("expired");
  }
}

export function buildOidcSettings() {
  assertStaffClientConfig();
  const config = readPublicConfig();
  userMemoryStore = new InMemoryWebStorage();
  return {
    authority: config.oidcIssuer,
    client_id: config.oidcClientId,
    redirect_uri: config.oidcRedirectUri,
    post_logout_redirect_uri: config.oidcPostLogoutRedirectUri,
    silent_redirect_uri: config.oidcSilentRedirectUri || undefined,
    response_type: "code" as const,
    scope: config.oidcScope,
    loadUserInfo: false,
    monitorSession: false,
    automaticSilentRenew: Boolean(config.oidcSilentRedirectUri),
    filterProtocolClaims: true,
    disablePKCE: false,
    extraQueryParams: { audience: STAFF_AUDIENCE },
    extraTokenParams: { audience: STAFF_AUDIENCE },
    metadataSeed: config.oidcEndSessionUrl
      ? { end_session_endpoint: config.oidcEndSessionUrl }
      : undefined,
    userStore: new WebStorageStateStore({ store: userMemoryStore }),
    stateStore: new WebStorageStateStore({ store: window.sessionStorage }),
  };
}

export function getUserManager(): UserManager {
  if (manager) {
    return manager;
  }
  if (!isOidcConfigured()) {
    throw new Error("OIDC issuer and client id are not configured");
  }
  manager = new UserManager(buildOidcSettings());
  manager.events.addUserLoaded((user) => {
    applyUser(user);
  });
  manager.events.addUserUnloaded(() => {
    clearAccessToken();
  });
  manager.events.addAccessTokenExpired(() => {
    clearAccessToken();
    triggerSessionExpired("expired");
  });
  return manager;
}

export function resetUserManagerForTests(): void {
  manager = null;
  userMemoryStore = null;
  loginRedirectInFlight = false;
}

export async function restoreOidcUser(): Promise<boolean> {
  if (!isOidcConfigured()) {
    return false;
  }
  const user = await getUserManager().getUser();
  applyUser(user);
  return Boolean(user && !user.expired && user.access_token);
}

export async function startLogin(returnTo?: string): Promise<void> {
  if (loginRedirectInFlight) {
    return;
  }
  loginRedirectInFlight = true;
  storeReturnTo(returnTo ?? "/app");
  try {
    await getUserManager().signinRedirect({
      extraQueryParams: { audience: STAFF_AUDIENCE },
    });
  } catch {
    loginRedirectInFlight = false;
    throw new Error("Sign-in could not be started");
  }
}

export async function completeLoginCallback(): Promise<void> {
  loginRedirectInFlight = false;
  try {
    if (callbackHasOidcError() || callbackLooksMalformed()) {
      stripOidcCallbackParams();
      clearAccessToken();
      try {
        await manager?.removeUser();
      } catch {
        // Do not construct a UserManager solely to fail a bad callback.
      }
      return;
    }
    const user = await getUserManager().signinCallback();
    applyUser(user ?? null);
  } catch {
    clearAccessToken();
    try {
      await manager?.removeUser();
    } catch {
      // Handshake state may already be gone.
    }
  } finally {
    stripOidcCallbackParams();
    purgeWebStorageTokenLeakage();
  }
}

export async function logoutAtIdentityProvider(): Promise<void> {
  loginRedirectInFlight = false;
  if (!isOidcConfigured() || !manager) {
    return;
  }
  try {
    await manager.signoutRedirect();
  } catch {
    await manager.removeUser();
  }
}

export async function resetOidcClient(): Promise<void> {
  loginRedirectInFlight = false;
  if (!manager) {
    return;
  }
  try {
    await manager.removeUser();
  } catch {
    // In-memory user may already be gone.
  }
}

export function peekOidcStatePersistence(): { userStore: string; stateStore: string } {
  return {
    userStore: "memory",
    stateStore: "sessionStorage",
  };
}

export function inspectOidcClientSettings(): {
  responseType: string;
  disablePKCE: boolean;
  authority: string;
  clientId: string;
  audience: string;
  clientSecretSet: boolean;
  automaticSilentRenew: boolean;
  silentRedirectConfigured: boolean;
} {
  const settings = getUserManager().settings;
  return {
    responseType: settings.response_type,
    disablePKCE: settings.disablePKCE,
    authority: settings.authority,
    clientId: settings.client_id,
    audience: STAFF_AUDIENCE,
    clientSecretSet: Boolean(settings.client_secret),
    automaticSilentRenew: Boolean(settings.automaticSilentRenew),
    silentRedirectConfigured: Boolean(readPublicConfig().oidcSilentRedirectUri),
  };
}
