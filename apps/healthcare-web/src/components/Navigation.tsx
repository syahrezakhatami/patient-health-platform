import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { APP_PATHS } from "../routing/paths";
import { hasPermission, visibleWorkspaces, type WorkspaceId } from "../tenant/permissions";
import { useTenant } from "../tenant/TenantContext";

const WORKSPACE_PATH: Record<WorkspaceId, string> = {
  registration: APP_PATHS.registration,
  clinical: APP_PATHS.clinical,
  identity: APP_PATHS.identity,
  audit: APP_PATHS.audit,
  admin: APP_PATHS.admin,
};

const WORKSPACE_LABEL: Record<WorkspaceId, string> = {
  registration: "nav.registration",
  clinical: "nav.clinical",
  identity: "nav.identity",
  audit: "nav.audit",
  admin: "nav.admin",
};

export function Navigation() {
  const { t } = useTranslation();
  const { effectivePermissions } = useTenant();
  const workspaces = visibleWorkspaces(effectivePermissions);
  const canLookup = hasPermission(effectivePermissions, "mpi.identity.read");

  return (
    <nav aria-label={t("app.name")}>
      <ul>
        <li>
          <NavLink to={APP_PATHS.app} end>
            {t("nav.home")}
          </NavLink>
        </li>
        {canLookup ? (
          <li>
            <NavLink to={APP_PATHS.patientSelect}>{t("nav.selectPatient")}</NavLink>
          </li>
        ) : null}
        {workspaces.map((workspace) => (
          <li key={workspace}>
            <NavLink to={WORKSPACE_PATH[workspace]}>{t(WORKSPACE_LABEL[workspace])}</NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
