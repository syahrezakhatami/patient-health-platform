import { useTranslation } from "react-i18next";

import { visibleWorkspaces } from "../tenant/permissions";
import { useTenant } from "../tenant/TenantContext";

export function AppHomePage() {
  const { t } = useTranslation();
  const { effectivePermissions, roleCodes } = useTenant();
  const workspaces = visibleWorkspaces(effectivePermissions);
  return (
    <section>
      <h1>{t("workspace.homeTitle")}</h1>
      <p>{t("workspace.homeBody")}</p>
      {roleCodes.length > 0 ? (
        <p className="muted">
          {t("org.roles")}: {roleCodes.join(", ")}
        </p>
      ) : null}
      {workspaces.length === 0 ? <p>{t("workspace.noWorkspaces")}</p> : null}
    </section>
  );
}
