import type { ReactNode } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import { SelectedPatientBanner } from "../patient/SelectedPatientBanner";
import { useTenant } from "../tenant/TenantContext";
import { Navigation } from "./Navigation";
import { TopBar } from "./TopBar";

export function AppShell({ children }: { children?: ReactNode }) {
  const { t } = useTranslation();
  const location = useLocation();
  const { facilityScope, workFacilityRequired, workFacilityId, accessibleFacilities } = useTenant();
  const needsFacilityChoice =
    workFacilityRequired && !workFacilityId && accessibleFacilities.length > 1;

  useEffect(() => {
    document.getElementById("main-content")?.focus();
  }, [location.pathname]);

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">
        {t("app.skipToContent")}
      </a>
      <TopBar />
      <aside className="sidebar">
        <Navigation />
      </aside>
      <main id="main-content" className="content" tabIndex={-1}>
        {facilityScope === "ALL_IN_ORGANIZATION" ? (
          <p className="muted">{t("facility.allInOrganizationHint")}</p>
        ) : null}
        {needsFacilityChoice ? (
          <div className="notice" role="status">
            <h2>{t("facility.requiredTitle")}</h2>
            <p>{t("facility.requiredBody")}</p>
          </div>
        ) : null}
        <SelectedPatientBanner />
        {children ?? <Outlet />}
      </main>
    </div>
  );
}