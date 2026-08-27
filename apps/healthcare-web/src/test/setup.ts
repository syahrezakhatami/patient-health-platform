import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

import { resetUserManagerForTests } from "../auth/oidc";
import { resetSessionExpiryLock } from "../auth/sessionLifecycle";
import { clearAccessToken } from "../auth/tokenStore";
import { clearTabTenantStorage } from "../tenant/tabStorage";
import { clearPatientAndChartFilter } from "../tenant/clinicalBoundary";
import { registerUnsavedWorkAdapter, registerUnsavedWorkGuard, registerUnsavedWorkPrompt } from "../tenant/unsavedWork";

afterEach(() => {
  cleanup();
  clearAccessToken();
  clearTabTenantStorage();
  clearPatientAndChartFilter();
  resetSessionExpiryLock();
  resetUserManagerForTests();
  registerUnsavedWorkGuard(null);
  registerUnsavedWorkAdapter(null);
  registerUnsavedWorkPrompt(null);
  sessionStorage.clear();
  localStorage.clear();
});
