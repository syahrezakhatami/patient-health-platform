import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { fetchChartSection } from "../api/clinical";
import { ApiError } from "../api/errors";
import type { ChartSection } from "../api/generated/iam-shell";
import { clinicalKeys } from "../api/queryClient";
import { isAbortError, mergeAbortSignals } from "../tenant/generation";
import { SECTION_LABEL_KEY } from "./catalog";
import { clinicalChartCoordinator } from "./clinicalChartCoordinator";
import { asFact, factFields, factTitle, isVitalObservation, nestedRecords } from "./facts";
import { ClinicalNoteForm } from "./notes/ClinicalNoteForm";
import { clinicalQueryPolicy } from "./queryPolicy";
import {
  SectionEmptyState,
  SectionErrorState,
  SectionLoadingState,
  SectionUnavailableState,
} from "./sectionStates";

function FactCard({ item, title }: { item: Record<string, unknown>; title: string }) {
  const fields = factFields(item);
  const specimens = nestedRecords(item, "specimens");
  const results = nestedRecords(item, "results");
  return (
    <article className="chart-fact-card">
      <h3>{title}</h3>
      <dl>
        {fields.map((field) => (
          <div key={field.key}>
            <dt>{field.key}</dt>
            <dd>{field.value}</dd>
          </div>
        ))}
      </dl>
      {specimens.map((specimen, index) => (
        <div key={String(specimen.id ?? index)} className="chart-nested">
          <h4>{factTitle(specimen, "specimen")}</h4>
        </div>
      ))}
      {results.map((result, index) => (
        <div key={String(result.id ?? index)} className="chart-nested">
          <h4>{factTitle(result, "result")}</h4>
        </div>
      ))}
    </article>
  );
}

export function ClinicalSectionView({
  organizationId,
  facilityId,
  patientIdentityId,
  section,
  generation,
  signal,
  onForbidden,
}: {
  organizationId: string;
  facilityId: string | null;
  patientIdentityId: string;
  section: ChartSection;
  generation: number;
  signal: AbortSignal;
  onForbidden?: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [forbidden, setForbidden] = useState(false);
  const query = useQuery({
    queryKey: clinicalKeys.section(organizationId, patientIdentityId, section),
    queryFn: ({ signal: querySignal }) => {
      if (!clinicalChartCoordinator.isCurrent(generation)) {
        throw new DOMException("Aborted", "AbortError");
      }
      return fetchChartSection({
        organizationId,
        facilityId,
        patientIdentityId,
        section,
        signal: mergeAbortSignals(querySignal, signal),
      });
    },
    enabled: !forbidden,
    ...clinicalQueryPolicy,
  });

  useEffect(() => {
    if (forbidden) {
      return;
    }
    if (!(query.error instanceof ApiError) || query.error.status !== 403) {
      return;
    }
    const handle = window.setTimeout(() => {
      setForbidden(true);
      queryClient.removeQueries({
        queryKey: clinicalKeys.section(organizationId, patientIdentityId, section),
      });
      onForbidden?.();
    }, 0);
    return () => window.clearTimeout(handle);
  }, [forbidden, onForbidden, organizationId, patientIdentityId, query.error, queryClient, section]);

  if (forbidden || (query.error instanceof ApiError && query.error.status === 403)) {
    return <SectionUnavailableState />;
  }
  if (query.isPending) {
    return <SectionLoadingState />;
  }
  if (query.error) {
    if (isAbortError(query.error)) {
      return <SectionLoadingState />;
    }
    return <SectionErrorState onRetry={() => void query.refetch()} />;
  }
  const items = (query.data?.items ?? []).map(asFact);
  if (items.length === 0 && section !== "notes") {
    return <SectionEmptyState messageKey="chart.sectionEmpty" />;
  }

  const vitals = section === "observations" ? items.filter(isVitalObservation) : [];
  const rest = section === "observations" ? items.filter((item) => !isVitalObservation(item)) : items;

  return (
    <div className="chart-section">
      <h2>{t(SECTION_LABEL_KEY[section])}</h2>
      {section === "notes" ? (
        <ClinicalNoteForm
          organizationId={organizationId}
          facilityId={facilityId}
          patientIdentityId={patientIdentityId}
          generation={generation}
          signal={signal}
        />
      ) : null}
      {section === "notes" ? <p className="muted">{t("chart.notesMetadataOnly")}</p> : null}
      {section === "notes" && items.length === 0 ? <SectionEmptyState messageKey="chart.sectionEmpty" /> : null}
      {section === "observations" && vitals.length > 0 ? (
        <section>
          <h3>{t("chart.vitals")}</h3>
          {vitals.map((item, index) => (
            <FactCard key={String(item.id ?? index)} item={item} title={factTitle(item, t("chart.vitals"))} />
          ))}
        </section>
      ) : null}
      {rest.map((item, index) => (
        <FactCard
          key={String(item.id ?? index)}
          item={item}
          title={factTitle(item, t(SECTION_LABEL_KEY[section]))}
        />
      ))}
    </div>
  );
}
