import { parseApiError, type ApiError } from "./errors";
import { getAccessToken } from "../auth/tokenStore";
import { triggerSessionExpired } from "../auth/sessionLifecycle";
import { readPublicConfig } from "../config";
import { isAbortError } from "../tenant/generation";

export type RequestPurpose =
  | "TREATMENT"
  | "REGISTRATION"
  | "IDENTITY_RESOLUTION"
  | "AUDIT"
  | "ADMINISTRATION";

export interface ApiRequestOptions {
  method?: string;
  path: string;
  body?: unknown;
  organizationId?: string | null;
  facilityId?: string | null;
  purpose?: RequestPurpose | null;
  signal?: AbortSignal;
}

const REQUEST_TIMEOUT_MS = 30_000;

function newCorrelationId(): string {
  return crypto.randomUUID();
}

function joinUrl(base: string, path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    throw new Error("API client only accepts relative paths");
  }
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${base}${normalized}`;
}

function combinedSignal(userSignal?: AbortSignal): AbortSignal {
  const timeout =
    typeof AbortSignal.timeout === "function" ? AbortSignal.timeout(REQUEST_TIMEOUT_MS) : undefined;
  if (userSignal && timeout && typeof AbortSignal.any === "function") {
    return AbortSignal.any([userSignal, timeout]);
  }
  return userSignal ?? timeout ?? new AbortController().signal;
}

export async function apiRequest<T>(options: ApiRequestOptions): Promise<T> {
  const config = readPublicConfig();
  const headers = new Headers();
  headers.set("Accept", "application/json");
  headers.set("X-Correlation-ID", newCorrelationId());

  const token = getAccessToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (options.organizationId) {
    headers.set("X-Organization-Id", options.organizationId);
  }
  if (options.facilityId) {
    headers.set("X-Facility-Id", options.facilityId);
  }
  if (options.purpose) {
    headers.set("X-Purpose", options.purpose);
  }
  if (options.body !== undefined) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(joinUrl(config.apiBaseUrl, options.path), {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: combinedSignal(options.signal),
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch (error) {
    if (isAbortError(error)) {
      throw error;
    }
    throw parseApiError(0, null) as ApiError;
  }

  if (response.status === 401) {
    triggerSessionExpired("unauthorized");
    throw parseApiError(401, null);
  }

  if (!response.ok) {
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    throw parseApiError(response.status, body);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
