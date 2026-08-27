import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { PatientLookupPanel } from "../patient/PatientLookupPanel";
import { usePatientSelection } from "../patient/PatientSelectionContext";
import { lookupPurposeForWorkspace } from "../patient/purpose";
import { APP_PATHS } from "../routing/paths";
import { hasPermission, type WorkspaceId } from "../tenant/permissions";
import { useTenant } from "../tenant/TenantContext";

export function EmptyWorkspace({ titleKey }: { titleKey: string }) {
  const { t } = useTranslation();
  return (
    <section className="workspace-empty">
      <h1>{t(titleKey)}</h1>
      <p>{t("workspace.empty")}</p>
    </section>
  );
}

function WorkspaceWithLookup({
  titleKey,
  workspace,
}: {
  titleKey: string;
  workspace: WorkspaceId;
}) {
  const { t } = useTranslation();
  const { effectivePermissions, selectedOrganization } = useTenant();
  const canLookup = hasPermission(effectivePermissions, "mpi.identity.read");
  const purpose = lookupPurposeForWorkspace(workspace);
  if (!canLookup || !purpose) {
    return (
      <section className="workspace-empty">
        <h1>{t(titleKey)}</h1>
        <p>{t("workspace.empty")}</p>
      </section>
    );
  }
  return (
    <section>
      <h1>{t(titleKey)}</h1>
      <PatientLookupPanel
        key={selectedOrganization?.organization_id ?? workspace}
        purpose={purpose}
      />
    </section>
  );
}

export function RegistrationWorkspacePage() {
  return <WorkspaceWithLookup titleKey="workspace.registrationTitle" workspace="registration" />;
}

export function ClinicalWorkspacePage() {
  const { t } = useTranslation();
  const { selectedPatient } = usePatientSelection();
  return (
    <>
      <WorkspaceWithLookup titleKey="workspace.clinicalTitle" workspace="clinical" />
      {selectedPatient ? (
        <p>
          <Link className="button" to={APP_PATHS.clinicalChart}>
            {t("chart.openChart")}
          </Link>
        </p>
      ) : null}
    </>
  );
}

export function IdentityWorkspacePage() {
  return <WorkspaceWithLookup titleKey="workspace.identityTitle" workspace="identity" />;
}

export function AuditWorkspacePage() {
  return <WorkspaceWithLookup titleKey="workspace.auditTitle" workspace="audit" />;
}

export function AdministrationWorkspacePage() {
  return <EmptyWorkspace titleKey="workspace.adminTitle" />;
}
