import { useTranslation } from "react-i18next";

export function EmptyWorkspace({ titleKey }: { titleKey: string }) {
  const { t } = useTranslation();
  return (
    <section className="workspace-empty">
      <h1>{t(titleKey)}</h1>
      <p>{t("workspace.empty")}</p>
    </section>
  );
}

export function RegistrationWorkspacePage() {
  return <EmptyWorkspace titleKey="workspace.registrationTitle" />;
}

export function ClinicalWorkspacePage() {
  return <EmptyWorkspace titleKey="workspace.clinicalTitle" />;
}

export function IdentityWorkspacePage() {
  return <EmptyWorkspace titleKey="workspace.identityTitle" />;
}

export function AuditWorkspacePage() {
  return <EmptyWorkspace titleKey="workspace.auditTitle" />;
}

export function AdministrationWorkspacePage() {
  return <EmptyWorkspace titleKey="workspace.adminTitle" />;
}
