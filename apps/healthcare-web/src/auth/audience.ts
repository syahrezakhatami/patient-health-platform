import { FORBIDDEN_AUDIENCES, STAFF_AUDIENCE } from "../config";

function decodeBase64Url(value: string): string {
  const padded = value.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(value.length / 4) * 4, "=");
  return atob(padded);
}

export function readTokenAudiences(token: string): string[] {
  const parts = token.split(".");
  if (parts.length !== 3) {
    return [];
  }
  try {
    const payload = JSON.parse(decodeBase64Url(parts[1] ?? "")) as { aud?: unknown };
    if (typeof payload.aud === "string") {
      return [payload.aud];
    }
    if (Array.isArray(payload.aud)) {
      return payload.aud.filter((item): item is string => typeof item === "string");
    }
    return [];
  } catch {
    return [];
  }
}

export function assertStaffAccessToken(token: string): void {
  const audiences = readTokenAudiences(token);
  if (audiences.length === 0) {
    throw new Error("Access token is missing a staff API audience");
  }
  if (audiences.some((audience) => (FORBIDDEN_AUDIENCES as readonly string[]).includes(audience))) {
    throw new Error("Patient and platform API audiences are not permitted in Healthcare Web");
  }
  if (!audiences.includes(STAFF_AUDIENCE)) {
    throw new Error("Access token audience must include php-api");
  }
}
