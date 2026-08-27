import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { canOpenWorkspace, type WorkspaceId } from "../tenant/permissions";
import { useTenant } from "../tenant/TenantContext";
import { Forbidden } from "./Forbidden";

/**
 * PermissionGate is UI-only. Hiding a route does not grant or deny access.
 * Backend authorization remains authoritative.
 */
export function PermissionGate({
  workspace,
  children,
}: {
  workspace: WorkspaceId;
  children: ReactNode;
}) {
  const { effectivePermissions } = useTenant();
  const { t } = useTranslation();
  if (!canOpenWorkspace(effectivePermissions, workspace)) {
    return (
      <Forbidden
        title={t("errors.forbiddenTitle")}
        body={t("errors.forbiddenBody")}
      />
    );
  }
  return children;
}
