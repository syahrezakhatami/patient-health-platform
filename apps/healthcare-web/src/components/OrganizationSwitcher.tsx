import { useTranslation } from "react-i18next";

import { useTenant } from "../tenant/TenantContext";

export function OrganizationSwitcher() {
  const { t } = useTranslation();
  const { organizations, selectedOrganization, switchOrganization, phase } = useTenant();
  if (organizations.length < 2 || phase !== "ready") {
    return null;
  }
  return (
    <div className="field" style={{ margin: 0 }}>
      <label htmlFor="organization-switcher">{t("org.switch")}</label>
      <select
        id="organization-switcher"
        value={selectedOrganization?.organization_id ?? ""}
        onChange={(event) => {
          void switchOrganization(event.target.value);
        }}
      >
        {organizations.map((organization) => (
          <option key={organization.organization_id} value={organization.organization_id}>
            {organization.name}
          </option>
        ))}
      </select>
    </div>
  );
}
