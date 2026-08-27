import { Navigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { LoadingBoundary } from "../components/LoadingBoundary";
import { APP_PATHS } from "../routing/paths";
import { useTenant } from "../tenant/TenantContext";

export function SelectOrganizationPage() {
  const { t } = useTranslation();
  const { phase, organizations, selectOrganization, selectedOrganization, errorMessage } =
    useTenant();

  if (phase === "loading") {
    return <LoadingBoundary />;
  }
  if (phase === "unassigned") {
    return <Navigate to={APP_PATHS.unassigned} replace />;
  }
  if (phase === "ready" && selectedOrganization) {
    return <Navigate to={APP_PATHS.app} replace />;
  }

  return (
    <section className="panel">
      <h1>{t("org.selectTitle")}</h1>
      <p>{t("org.selectBody")}</p>
      {errorMessage ? <p role="alert">{errorMessage}</p> : null}
      <ul className="org-list">
        {organizations.map((organization) => (
          <li key={organization.organization_id}>
            <button
              type="button"
              className="button secondary org-option"
              onClick={() => void selectOrganization(organization.organization_id)}
            >
              {organization.name} ({organization.code})
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
