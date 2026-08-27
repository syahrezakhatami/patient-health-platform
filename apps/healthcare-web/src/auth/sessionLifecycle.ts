import type { QueryClient } from "@tanstack/react-query";

import { RETURN_TO_STORAGE_KEY } from "./returnTo";
import { clearAccessToken } from "./tokenStore";
import { clearPatientAndChartFilter } from "../tenant/clinicalBoundary";
import { clearTabTenantStorage } from "../tenant/tabStorage";

export type SessionExpiredReason = "unauthorized" | "expired" | "logout";

type SessionHandler = (reason: SessionExpiredReason) => void;

let handler: SessionHandler | null = null;
let queryClientRef: QueryClient | null = null;
let expiryInFlight = false;

export function registerQueryClient(client: QueryClient): void {
  queryClientRef = client;
}

export function getRegisteredQueryClient(): QueryClient | null {
  return queryClientRef;
}

export function registerSessionHandler(next: SessionHandler): void {
  handler = next;
}

export function resetSessionExpiryLock(): void {
  expiryInFlight = false;
}

export function isSessionExpiryInFlight(): boolean {
  return expiryInFlight;
}

/** Idempotent: concurrent 401s must not start multiple redirects or logins. */
export function triggerSessionExpired(reason: SessionExpiredReason = "expired"): void {
  if (expiryInFlight && reason !== "logout") {
    return;
  }
  expiryInFlight = true;
  handler?.(reason);
}

const TOKEN_LEAK = /"access_token"|"refresh_token"|"id_token"/;

/** Remove any Web Storage entry that accidentally contains OIDC tokens. */
export function purgeWebStorageTokenLeakage(): void {
  if (typeof window === "undefined") {
    return;
  }
  for (const storage of [window.sessionStorage, window.localStorage]) {
    const keys: string[] = [];
    for (let i = 0; i < storage.length; i += 1) {
      const key = storage.key(i);
      if (key) {
        keys.push(key);
      }
    }
    for (const key of keys) {
      const value = storage.getItem(key) ?? "";
      if (TOKEN_LEAK.test(value)) {
        storage.removeItem(key);
      }
    }
  }
}

/** Transient oidc-client-ts handshake keys (state / nonce / PKCE verifier). */
export function clearOidcHandshakeStorage(): void {
  if (typeof window === "undefined") {
    return;
  }
  const keys: string[] = [];
  for (let i = 0; i < sessionStorage.length; i += 1) {
    const key = sessionStorage.key(i);
    if (key?.startsWith("oidc.")) {
      keys.push(key);
    }
  }
  for (const key of keys) {
    sessionStorage.removeItem(key);
  }
  sessionStorage.removeItem(RETURN_TO_STORAGE_KEY);
}

export function clearSensitiveClientState(): void {
  clearAccessToken();
  queryClientRef?.clear();
  clearPatientAndChartFilter();
  clearTabTenantStorage();
  clearOidcHandshakeStorage();
  purgeWebStorageTokenLeakage();
}
