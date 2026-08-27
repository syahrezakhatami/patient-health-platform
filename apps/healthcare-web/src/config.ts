/** Staff Healthcare Web talks to the php-api audience only. */
export const STAFF_AUDIENCE = "php-api";

export const PLATFORM_AUDIENCE = "php-platform";
export const PATIENT_AUDIENCE = "php-patient";

export const FORBIDDEN_AUDIENCES = [PLATFORM_AUDIENCE, PATIENT_AUDIENCE] as const;

export interface PublicAppConfig {
  apiBaseUrl: string;
  oidcIssuer: string;
  oidcClientId: string;
  oidcRedirectUri: string;
  oidcSilentRedirectUri: string;
  oidcPostLogoutRedirectUri: string;
  oidcEndSessionUrl: string;
  oidcScope: string;
  oidcAudience: string;
}

function trimSlash(value: string): string {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

export function readPublicConfig(): PublicAppConfig {
  const oidcAudience = (import.meta.env.VITE_OIDC_AUDIENCE ?? STAFF_AUDIENCE).trim();
  return {
    apiBaseUrl: trimSlash(import.meta.env.VITE_API_BASE_URL ?? ""),
    oidcIssuer: (import.meta.env.VITE_OIDC_ISSUER ?? "").trim(),
    oidcClientId: (import.meta.env.VITE_OIDC_CLIENT_ID ?? "").trim(),
    oidcRedirectUri:
      (import.meta.env.VITE_OIDC_REDIRECT_URI ?? "").trim() ||
      `${window.location.origin}/auth/callback`,
    oidcSilentRedirectUri: (import.meta.env.VITE_OIDC_SILENT_REDIRECT_URI ?? "").trim(),
    oidcPostLogoutRedirectUri:
      (import.meta.env.VITE_OIDC_POST_LOGOUT_REDIRECT_URI ?? "").trim() ||
      `${window.location.origin}/login`,
    oidcEndSessionUrl: (import.meta.env.VITE_OIDC_END_SESSION_URL ?? "").trim(),
    oidcScope: (import.meta.env.VITE_OIDC_SCOPE ?? "openid profile").trim(),
    oidcAudience,
  };
}

export function isOidcConfigured(): boolean {
  const config = readPublicConfig();
  return Boolean(config.oidcIssuer && config.oidcClientId);
}

export function assertStaffClientConfig(): void {
  const { oidcAudience } = readPublicConfig();
  if (oidcAudience !== STAFF_AUDIENCE) {
    throw new Error("Healthcare Web OIDC audience must be php-api");
  }
}

const SECRET_SHAPED = /(secret|password|private[_-]?key|BEGIN )/i;

export function validatePublicConfig(config: PublicAppConfig, requireOidc: boolean): void {
  if (config.oidcAudience !== STAFF_AUDIENCE) {
    throw new Error("Healthcare Web OIDC audience must be php-api");
  }
  const publicValues = [
    config.oidcIssuer,
    config.oidcClientId,
    config.oidcRedirectUri,
    config.oidcPostLogoutRedirectUri,
    config.oidcScope,
    config.apiBaseUrl,
  ];
  for (const value of publicValues) {
    if (SECRET_SHAPED.test(value)) {
      throw new Error("Frontend env must not contain secret-shaped values");
    }
  }
  if (requireOidc && (!config.oidcIssuer || !config.oidcClientId)) {
    throw new Error("VITE_OIDC_ISSUER and VITE_OIDC_CLIENT_ID are required");
  }
}
