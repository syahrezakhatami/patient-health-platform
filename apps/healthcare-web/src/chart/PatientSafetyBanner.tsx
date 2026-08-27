import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { APP_PATHS } from "../routing/paths";
import { useTenant } from "../tenant/TenantContext";
import { canOpenWorkspace } from "../tenant/permissions";
import type { ChartPatientHeader } from "./header";

function isAnonymousKind(kind: string): boolean {
  return kind === "ANONYMOUS" || kind === "TEMPORARY";
}

export function PatientSafetyBanner({
  header,
  fallbackName,
  fallbackDob,
  fallbackSex,
  fallbackMrn,
  identityKind,
  identityUpdated,
  onChangePatient,
}: {
  header: ChartPatientHeader | null;
  fallbackName: string;
  fallbackDob: string | null;
  fallbackSex: string | null;
  fallbackMrn: string | null;
  identityKind: string;
  identityUpdated: boolean;
  onChangePatient: () => void;
}) {
  const { t } = useTranslation();
  const { selectedOrganization, workFacility, effectivePermissions } = useTenant();
  const name = header
    ? [header.given_name, header.family_name].filter(Boolean).join(" ").trim() ||
      header.display_label ||
      fallbackName
    : fallbackName;
  const dob = header?.birth_date ?? fallbackDob;
  const sex = header?.administrative_sex ?? fallbackSex;
  const mrn = header?.mrn.length ? header.mrn.join(", ") : (fallbackMrn ?? null);
  const age = header?.age_years;
  const kind = header?.identity_kind || identityKind;
  const canClinical = canOpenWorkspace(effectivePermissions, "clinical");

  return (
    <section className="patient-safety-banner" aria-label={t("chart.bannerLabel")} data-testid="patient-safety-banner">
      <h2>{t("chart.bannerTitle")}</h2>
      {identityUpdated ? (
        <p className="notice" role="status">
          {t("chart.identityUpdated")}
        </p>
      ) : null}
      <p>
        <strong>{name}</strong>
        {isAnonymousKind(kind) ? ` — ${t("patient.anonymous")}` : null}
      </p>
      <dl className="chart-banner-fields">
        <div>
          <dt>{t("patient.dob")}</dt>
          <dd>{dob ?? t("patient.unknown")}</dd>
        </div>
        <div>
          <dt>{t("chart.age")}</dt>
          <dd>{age === null || age === undefined ? t("patient.unknown") : String(age)}</dd>
        </div>
        <div>
          <dt>{t("patient.sex")}</dt>
          <dd>{sex ?? t("patient.unknown")}</dd>
        </div>
        <div>
          <dt>{t("patient.mrn")}</dt>
          <dd>{mrn ?? t("patient.unknown")}</dd>
        </div>
        <div>
          <dt>{t("org.activeOrganization")}</dt>
          <dd>{selectedOrganization?.name ?? t("patient.unknown")}</dd>
        </div>
        <div>
          <dt>{t("facility.label")}</dt>
          <dd>{workFacility?.name ?? t("facility.unset")}</dd>
        </div>
      </dl>
      <div className="chart-banner-actions">
        <button type="button" className="button secondary" onClick={onChangePatient}>
          {t("chart.changePatient")}
        </button>
        {canClinical ? (
          <Link className="button secondary" to={APP_PATHS.patientSelect}>
            {t("nav.selectPatient")}
          </Link>
        ) : null}
      </div>
    </section>
  );
}
