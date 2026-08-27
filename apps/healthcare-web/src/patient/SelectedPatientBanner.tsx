import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { usePatientSelection } from "../patient/PatientSelectionContext";
import { APP_PATHS } from "../routing/paths";
import { canOpenWorkspace } from "../tenant/permissions";
import { useTenant } from "../tenant/TenantContext";

function isAnonymousKind(kind: string): boolean {
  return kind === "ANONYMOUS" || kind === "TEMPORARY";
}

export function SelectedPatientBanner() {
  const { t } = useTranslation();
  const { selectedPatient, clearSelection } = usePatientSelection();
  const { effectivePermissions } = useTenant();
  const canOpenChart = canOpenWorkspace(effectivePermissions, "clinical");
  if (!selectedPatient) {
    return null;
  }
  return (
    <section className="patient-selected-banner" data-testid="selected-patient-banner" aria-live="polite">
      <h2>{t("patient.selectedTitle")}</h2>
      <p>
        <strong>{selectedPatient.displayName}</strong>
        {isAnonymousKind(selectedPatient.identityKind) ? ` — ${t("patient.anonymous")}` : null}
      </p>
      <p className="muted">
        {t("patient.dob")}: {selectedPatient.birthDate ?? t("patient.unknown")} · {t("patient.sex")}:{" "}
        {selectedPatient.administrativeSex ?? t("patient.unknown")} · {t("patient.mrn")}:{" "}
        {selectedPatient.organizationMrn ?? t("patient.unknown")}
      </p>
      <div className="chart-banner-actions">
        {canOpenChart ? (
          <Link className="button" to={APP_PATHS.clinicalChart}>
            {t("chart.openChart")}
          </Link>
        ) : null}
        <button type="button" className="button secondary" onClick={clearSelection}>
          {t("patient.clearSelection")}
        </button>
      </div>
    </section>
  );
}
