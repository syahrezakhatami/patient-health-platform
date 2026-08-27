import { describe, expect, it } from "vitest";

import {
  FACILITY_STORAGE_KEY,
  LOCALE_STORAGE_KEY,
  ORG_STORAGE_KEY,
  readStoredOrganizationId,
  usesSessionStorageForTenantContext,
  writeStoredOrganizationId,
} from "./tabStorage";
import { ORG_A, ORG_B } from "../test/fixtures";

describe("multi-tab tenant storage", () => {
  it("persists organization ids in sessionStorage, not localStorage", () => {
    expect(usesSessionStorageForTenantContext()).toBe(true);
    writeStoredOrganizationId(ORG_A);
    expect(sessionStorage.getItem(ORG_STORAGE_KEY)).toBe(ORG_A);
    expect(localStorage.getItem(ORG_STORAGE_KEY)).toBeNull();
    expect(readStoredOrganizationId()).toBe(ORG_A);
  });

  it("allows conceptually independent tab organization ids", () => {
    const tabA = { [ORG_STORAGE_KEY]: ORG_A };
    const tabB = { [ORG_STORAGE_KEY]: ORG_B };
    expect(tabA[ORG_STORAGE_KEY]).not.toBe(tabB[ORG_STORAGE_KEY]);
    expect(localStorage.getItem(ORG_STORAGE_KEY)).toBeNull();
  });

  it("keeps locale storage separate from tenant context", () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, "en");
    writeStoredOrganizationId(ORG_A);
    expect(localStorage.getItem(ORG_STORAGE_KEY)).toBeNull();
    expect(sessionStorage.getItem(LOCALE_STORAGE_KEY)).toBeNull();
    expect(sessionStorage.getItem(FACILITY_STORAGE_KEY)).toBeNull();
  });
});
