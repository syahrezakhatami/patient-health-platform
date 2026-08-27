import { useTranslation } from "react-i18next";

import { useTenant } from "../tenant/TenantContext";
import { FacilitySwitcher } from "./FacilitySwitcher";
import { LocaleSwitcher } from "./LocaleSwitcher";
import { OrganizationSwitcher } from "./OrganizationSwitcher";
import { UserMenu } from "./UserMenu";

export function TopBar() {
  const { t } = useTranslation();
  const { selectedOrganization, workFacility } = useTenant();
  const organizationLabel = selectedOrganization?.name ?? "—";
  const facilityLabel = workFacility?.name ?? t("facility.unset");

  return (
    <header className="topbar">
      <strong>{t("app.name")}</strong>
      <div className="context-chip" data-testid="active-organization" title={organizationLabel}>
        <span>{t("org.activeOrganization")}</span>
        <strong>{organizationLabel}</strong>
      </div>
      <div className="context-chip" data-testid="active-work-facility" title={facilityLabel}>
        <span>{t("facility.label")}</span>
        <strong>{facilityLabel}</strong>
      </div>
      <div className="topbar-actions">
        <OrganizationSwitcher />
        <FacilitySwitcher />
        <LocaleSwitcher />
        <UserMenu />
      </div>
    </header>
  );
}