import { useTranslation } from "react-i18next";

import { usePatientSelection } from "../patient/PatientSelectionContext";

function isAnonymousKind(kind: string): boolean {
  return kind === "ANONYMOUS" || kind === "TEMPORARY";
}

export function SelectedPatientBanner() {
  const { t } = useTranslation();
  const { selectedPatient, clearSelection } = usePatientSelection();
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
      <button type="button" className="button secondary" onClick={clearSelection}>
        {t("patient.clearSelection")}
      </button>
    </section>
  );
}
