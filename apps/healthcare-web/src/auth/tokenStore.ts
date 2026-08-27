/**
 * In-memory access-token store.
 *
 * Bearer tokens stay in process memory only. Never write them to localStorage,
 * sessionStorage, IndexedDB, logs, or error UI.
 */
let accessToken: string | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function clearAccessToken(): void {
  accessToken = null;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}

/** Test-only helper. Production OIDC path validates audience before calling setAccessToken. */
export function setAccessTokenForTests(token: string | null): void {
  accessToken = token;
}
