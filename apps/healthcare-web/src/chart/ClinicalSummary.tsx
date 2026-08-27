import { useTranslation } from "react-i18next";

import type { ChartSection } from "../api/generated/iam-shell";
import type { ClinicalSummaryResponse, SummaryItemDTO } from "../api/generated/iam-shell";
import { SECTION_LABEL_KEY } from "./catalog";
import type { ChartPatientHeader } from "./header";
import { SectionEmptyState, SectionUnavailableState } from "./sectionStates";

function SummaryList({
  titleKey,
  items,
  authorized,
}: {
  titleKey: string;
  items: SummaryItemDTO[] | null | undefined;
  authorized: boolean;
}) {
  const { t } = useTranslation();
  if (!authorized) {
    return (
      <section className="chart-summary-block">
        <h3>{t(titleKey)}</h3>
        <SectionUnavailableState />
      </section>
    );
  }
  if (items == null) {
    return (
      <section className="chart-summary-block">
        <h3>{t(titleKey)}</h3>
        <p className="muted">{t("chart.summaryOmitted")}</p>
      </section>
    );
  }
  if (items.length === 0) {
    return (
      <section className="chart-summary-block">
        <h3>{t(titleKey)}</h3>
        <SectionEmptyState messageKey="chart.summaryEmpty" />
      </section>
    );
  }
  return (
    <section className="chart-summary-block">
      <h3>{t(titleKey)}</h3>
      <ul>
        {items.map((item) => (
          <li key={`${item.source_type}:${item.source_id}`}>
            {item.code_display || item.code || item.source_type}
            {item.status ? ` · ${item.status}` : ""}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function ClinicalSummary({
  summary,
  authorized,
  allergy,
}: {
  summary: ClinicalSummaryResponse;
  authorized: Set<ChartSection>;
  allergy: ChartPatientHeader["documentedAllergy"];
}) {
  const { t } = useTranslation();
  const allergyAuthorized = authorized.has("allergies");

  return (
    <div className="chart-summary">
      <h2>{t("chart.summary")}</h2>
      <section className="chart-summary-block" data-testid="allergy-safety">
        <h3>{t(SECTION_LABEL_KEY.allergies)}</h3>
        {!allergyAuthorized || allergy === "omitted" ? (
          <SectionUnavailableState />
        ) : allergy === "true" ? (
          <p>{t("chart.allergyDocumented")}</p>
        ) : (
          <p>{t("chart.allergyNoneDocumented")}</p>
        )}
      </section>
      <SummaryList
        titleKey={SECTION_LABEL_KEY.conditions}
        items={summary.active_conditions}
        authorized={authorized.has("conditions")}
      />
      <SummaryList
        titleKey={SECTION_LABEL_KEY.medications}
        items={summary.active_medications}
        authorized={authorized.has("medications")}
      />
      {allergyAuthorized && allergy === "true" ? (
        <SummaryList
          titleKey="chart.allergyRecords"
          items={summary.active_allergies}
          authorized
        />
      ) : null}
      <SummaryList
        titleKey="chart.vitals"
        items={summary.recent_vitals}
        authorized={authorized.has("observations")}
      />
      <SummaryList
        titleKey={SECTION_LABEL_KEY.laboratory}
        items={summary.recent_lab_results}
        authorized={authorized.has("laboratory")}
      />
      <SummaryList
        titleKey={SECTION_LABEL_KEY.procedures}
        items={summary.recent_procedures}
        authorized={authorized.has("procedures")}
      />
    </div>
  );
}
