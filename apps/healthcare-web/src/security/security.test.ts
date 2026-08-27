import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { shouldRetryRequest } from "../api/errors";
import { ApiError } from "../api/errors";
import { pathContainsForbiddenIdentifier, patientChartPath, APP_PATHS } from "../routing/paths";
import { ORG_A } from "../test/fixtures";

const srcRoot = join(dirname(fileURLToPath(import.meta.url)), "..");

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const path = join(dir, entry);
    const stat = statSync(path);
    if (stat.isDirectory()) {
      return walk(path);
    }
    return path.endsWith(".ts") || path.endsWith(".tsx") ? [path] : [];
  });
}

describe("security and privacy posture", () => {
  it("does not use dangerouslySetInnerHTML, service workers, or persisted query cache", () => {
    const files = walk(srcRoot).filter(
      (path) => !path.includes("/test/") && !path.includes(".test."),
    );
    const blob = files.map((file) => readFileSync(file, "utf8")).join("\n");
    expect(blob).not.toMatch(/dangerouslySetInnerHTML/);
    expect(blob).not.toMatch(/\binnerHTML\b/);
    expect(blob).not.toMatch(/document\.write/);
    expect(blob).not.toMatch(/\beval\(/);
    expect(blob).not.toMatch(/new Function/);
    expect(blob).not.toMatch(/serviceWorker/);
    expect(blob).not.toMatch(/persistQueryClient|createSyncStoragePersister|createAsyncStoragePersister/);
    expect(blob).not.toMatch(/gtag\(|hotjar|analytics\.js/i);
    expect(blob).not.toMatch(/signinResourceOwnerCredentials/);
    expect(blob).not.toMatch(/client_secret\s*:/);
    expect(blob).not.toMatch(/audience:\s*["']php-patient["']/);
    expect(blob).not.toMatch(/method:\s*["']GET["'][\s\S]{0,160}\/api\/v1\/clinical\/notes\//);
    expect(blob).not.toMatch(/indexedDB\.open|window\.indexedDB|caches\.open\(/);
    expect(blob).not.toMatch(/new BroadcastChannel/);
  });

  it("forbids identifier leakage in URLs", () => {
    expect(pathContainsForbiddenIdentifier("/app/patients?nik=123")).toBe(true);
    expect(pathContainsForbiddenIdentifier("/app/lookup?bpjs=0001")).toBe(true);
    expect(pathContainsForbiddenIdentifier("/app?mrn=abc")).toBe(true);
    expect(pathContainsForbiddenIdentifier("/app?patient_name=budi")).toBe(true);
    expect(pathContainsForbiddenIdentifier(`/app/clinical/patients/${ORG_A}`)).toBe(false);
    expect(patientChartPath(ORG_A)).toBe(`/app/clinical/patients/${ORG_A}`);
    expect(APP_PATHS.clinicalChart).toBe("/app/clinical/chart");
    expect(APP_PATHS.clinicalChart.includes(ORG_A)).toBe(false);
    expect(() => patientChartPath("not-a-uuid")).toThrow();
  });

  it("does not retry 401/403/404/409/422/429 and bounds 5xx to three attempts", () => {
    expect(shouldRetryRequest(0, new ApiError(401, "session_expired", "x", null))).toBe(false);
    expect(shouldRetryRequest(0, new ApiError(403, "permission_denied", "x", null))).toBe(false);
    expect(shouldRetryRequest(0, new ApiError(404, "not_found", "x", null))).toBe(false);
    expect(shouldRetryRequest(0, new ApiError(409, "conflict", "x", null))).toBe(false);
    expect(shouldRetryRequest(0, new ApiError(422, "validation", "x", null))).toBe(false);
    expect(shouldRetryRequest(0, new ApiError(429, "rate_limited", "x", null))).toBe(false);
    expect(shouldRetryRequest(0, new ApiError(500, "server_error", "x", null))).toBe(true);
    expect(shouldRetryRequest(1, new ApiError(500, "server_error", "x", null))).toBe(true);
    expect(shouldRetryRequest(2, new ApiError(500, "server_error", "x", null))).toBe(false);
    expect(shouldRetryRequest(0, new DOMException("Aborted", "AbortError"))).toBe(false);
  });
});
