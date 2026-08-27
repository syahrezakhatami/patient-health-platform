import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { fetchChartShell, fetchChartSummary } from "../api/clinical";
import { ApiError } from "../api/errors";
import { clinicalKeys, clearClinicalQueries, clearDownstreamClinicalQueries, retainCurrentClinicalQueries } from "../api/queryClient";
import { usePatientSelection } from "../patient/PatientSelectionContext";
import {
  applyCanonicalChartPatient,
  getSelectedPatient,
  getSelectionEpoch,
} from "../patient/selectionStore";
import { APP_PATHS } from "../routing/paths";
import { isAbortError, mergeAbortSignals } from "../tenant/generation";
import { canOpenWorkspace } from "../tenant/permissions";
import { useTenant } from "../tenant/TenantContext";
import { isChartSection, visibleAuthorizedSections } from "./catalog";
import { ChartNavigation, type ChartView } from "./ChartNavigation";
import { clinicalChartCoordinator } from "./clinicalChartCoordinator";
import { ClinicalSectionView } from "./ClinicalSectionView";
import { ClinicalSummary } from "./ClinicalSummary";
import { headerDisplayName, parseChartHeader } from "./header";
import { PatientSafetyBanner } from "./PatientSafetyBanner";
import { clinicalQueryPolicy } from "./queryPolicy";
import { SectionErrorState, SectionLoadingState, SectionUnavailableState } from "./sectionStates";
import { TimelineView } from "./TimelineView";
import { closePatientAndWipeChart } from "./wipe";

interface LoadToken {
  generation: number;
  signal: AbortSignal;
  epoch: number;
  patientId: string;
  orgId: string;
}

export function ClinicalChartPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { selectedPatient } = usePatientSelection();
  const { selectedOrganization, workFacilityId, effectivePermissions } = useTenant();
  const orgId = selectedOrganization?.organization_id ?? null;
  const [view, setView] = useState<ChartView>("summary");
  const [identityUpdated, setIdentityUpdated] = useState(false);
  const [load, setLoad] = useState<LoadToken | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const viewMounted = useRef(false);
  const startedSelectionAt = useRef<string | null>(null);

  const tenantBound =
    Boolean(selectedPatient && orgId && selectedPatient.organizationId === orgId);
  const canClinical = canOpenWorkspace(effectivePermissions, "clinical");
  const loadCommitted = Boolean(
    load &&
      tenantBound &&
      selectedPatient &&
      load.orgId === orgId &&
      load.epoch === getSelectionEpoch(),
  );

  useEffect(() => {
    const stored = getSelectedPatient();
    if (stored && orgId && stored.organizationId !== orgId) {
      closePatientAndWipeChart();
    }
  }, [orgId]);

  useEffect(() => {
    // Defer so oxlint react(set-state-in-effect) does not treat coordinator
    // begin + load token assignment as a synchronous render cascade.
    const handle = window.setTimeout(() => {
      if (!selectedPatient || !orgId || selectedPatient.organizationId !== orgId) {
        startedSelectionAt.current = null;
        clinicalChartCoordinator.abortAndInvalidate();
        setView("summary");
        setIdentityUpdated(false);
        setLoad(null);
        return;
      }
      if (startedSelectionAt.current === selectedPatient.selectedAt) {
        return;
      }
      startedSelectionAt.current = selectedPatient.selectedAt;
      setView("summary");
      setIdentityUpdated(false);
      const token = clinicalChartCoordinator.begin();
      setLoad({
        generation: token.generation,
        signal: token.signal,
        epoch: getSelectionEpoch(),
        patientId: selectedPatient.patientIdentityId,
        orgId,
      });
    }, 0);
    return () => window.clearTimeout(handle);
  }, [orgId, selectedPatient]);

  const shellQuery = useQuery({
    queryKey: load && tenantBound ? clinicalKeys.chart(load.orgId, load.patientId) : ["chart-idle", "shell"],
    queryFn: ({ signal }) => {
      if (
        !load ||
        !clinicalChartCoordinator.isCurrent(load.generation) ||
        load.epoch !== getSelectionEpoch() ||
        !getSelectedPatient()
      ) {
        throw new DOMException("Aborted", "AbortError");
      }
      return fetchChartShell({
        organizationId: load.orgId,
        facilityId: workFacilityId,
        patientIdentityId: load.patientId,
        signal: mergeAbortSignals(signal, load.signal),
      });
    },
    enabled: Boolean(loadCommitted && canClinical),
    ...clinicalQueryPolicy,
  });

  const header = useMemo(() => {
    if (!shellQuery.data) {
      return null;
    }
    return parseChartHeader(
      shellQuery.data.header,
      shellQuery.data.requested_patient_identity_id,
      shellQuery.data.canonical_patient_identity_id,
    );
  }, [shellQuery.data]);
  const headerInvalid = Boolean(shellQuery.isSuccess && shellQuery.data && !header);

  useEffect(() => {
    if (!shellQuery.data || !load || !header) {
      return;
    }
    if (!clinicalChartCoordinator.isCurrent(load.generation)) {
      return;
    }
    if (shellQuery.data.canonical_patient_identity_id === load.patientId) {
      return;
    }
    const applied = applyCanonicalChartPatient(
      {
        patientIdentityId: shellQuery.data.canonical_patient_identity_id,
        organizationId: load.orgId,
        displayName: headerDisplayName(header, selectedPatient?.displayName ?? ""),
        displayLabel: header.display_label,
        birthDate: header.birth_date,
        administrativeSex: header.administrative_sex,
        organizationMrn: header.mrn[0] ?? null,
        identityKind: header.identity_kind,
        lifecycleStatus: header.lifecycle_status,
        selectedAt: selectedPatient?.selectedAt ?? new Date().toISOString(),
      },
      {
        epoch: load.epoch,
        organizationId: load.orgId,
        requestedPatientId: load.patientId,
      },
    );
    if (applied) {
      window.setTimeout(() => setIdentityUpdated(true), 0);
    }
  }, [header, load, selectedPatient, shellQuery.data]);

  const canonicalId = shellQuery.data?.canonical_patient_identity_id ?? load?.patientId ?? "";
  const authorized = useMemo(
    () => new Set(visibleAuthorizedSections(shellQuery.data?.authorized_sections ?? [])),
    [shellQuery.data?.authorized_sections],
  );
  const navSections = visibleAuthorizedSections(shellQuery.data?.authorized_sections ?? []);

  useEffect(() => {
    if (!loadCommitted || !load || !tenantBound) {
      if (!tenantBound || !getSelectedPatient()) {
        clearClinicalQueries(queryClient);
      }
      return undefined;
    }
    retainCurrentClinicalQueries(queryClient, load.orgId, [load.patientId, canonicalId]);
    return () => {
      if (!getSelectedPatient()) {
        clearClinicalQueries(queryClient);
      }
    };
  }, [canonicalId, load, loadCommitted, queryClient, tenantBound]);

  useEffect(() => {
    if (headerInvalid || (shellQuery.isError && !isAbortError(shellQuery.error))) {
      clearDownstreamClinicalQueries(queryClient);
    }
  }, [headerInvalid, queryClient, shellQuery.error, shellQuery.isError]);

  useEffect(() => {
    if (!shellQuery.isSuccess || !header) {
      return undefined;
    }
    if (isChartSection(view) && !authorized.has(view)) {
      if (load && canonicalId) {
        queryClient.removeQueries({ queryKey: clinicalKeys.section(load.orgId, canonicalId, view) });
      }
      window.setTimeout(() => setView("summary"), 0);
    }
    return undefined;
  }, [authorized, canonicalId, header, load, queryClient, shellQuery.isSuccess, view]);

  useEffect(() => {
    if (!viewMounted.current) {
      viewMounted.current = true;
      return;
    }
    contentRef.current?.focus();
  }, [view]);

  const summaryQuery = useQuery({
    queryKey: load && tenantBound ? clinicalKeys.summary(load.orgId, canonicalId) : ["chart-idle", "summary"],
    queryFn: ({ signal }) => {
      if (
        !load ||
        !clinicalChartCoordinator.isCurrent(load.generation) ||
        load.epoch !== getSelectionEpoch() ||
        !getSelectedPatient()
      ) {
        throw new DOMException("Aborted", "AbortError");
      }
      return fetchChartSummary({
        organizationId: load.orgId,
        facilityId: workFacilityId,
        patientIdentityId: canonicalId,
        signal: mergeAbortSignals(signal, load.signal),
      });
    },
    enabled: Boolean(
      loadCommitted && canClinical && shellQuery.isSuccess && Boolean(header) && canonicalId,
    ),
    ...clinicalQueryPolicy,
  });

  const changePatient = () => {
    closePatientAndWipeChart();
    void navigate(APP_PATHS.patientSelect);
  };

  if (!canClinical) {
    return (
      <section>
        <h1>{t("chart.title")}</h1>
        <p>{t("errors.forbiddenBody")}</p>
      </section>
    );
  }

  if (!tenantBound || !selectedPatient || !orgId) {
    return (
      <section data-testid="chart-patient-gate">
        <h1>{t("chart.title")}</h1>
        <p>{t("chart.selectPatientFirst")}</p>
        <Link className="button" to={APP_PATHS.patientSelect}>
          {t("nav.selectPatient")}
        </Link>
      </section>
    );
  }

  const shellError = shellQuery.error;
  if (!loadCommitted || (shellQuery.isPending && !shellQuery.data)) {
    return (
      <section>
        <h1>{t("chart.title")}</h1>
        <SectionLoadingState />
      </section>
    );
  }
  if ((shellError && !isAbortError(shellError)) || headerInvalid) {
    const status = shellError instanceof ApiError ? shellError.status : 0;
    const messageKey =
      status === 409
        ? "chart.retired"
        : status === 404
          ? "chart.notFound"
          : "chart.shellError";
    return (
      <section data-testid="chart-shell-error">
        <h1>{t("chart.title")}</h1>
        <p className="notice" role="alert">
          {t(messageKey)}
        </p>
        <button type="button" className="button" onClick={changePatient}>
          {t("chart.changePatient")}
        </button>
      </section>
    );
  }

  const activeSection = isChartSection(view) ? view : null;
  const sectionUnauthorized = Boolean(activeSection && !authorized.has(activeSection));

  return (
    <section className="clinical-chart" data-testid="clinical-chart">
      <h1>{t("chart.title")}</h1>
      <PatientSafetyBanner
        header={header}
        fallbackName={selectedPatient.displayName}
        fallbackDob={selectedPatient.birthDate}
        fallbackSex={selectedPatient.administrativeSex}
        fallbackMrn={selectedPatient.organizationMrn}
        identityKind={selectedPatient.identityKind}
        identityUpdated={identityUpdated}
        onChangePatient={changePatient}
      />
      <ChartNavigation sections={navSections} view={view} onChange={setView} t={t} />
      <div ref={contentRef} className="chart-content" tabIndex={-1}>
      {view === "summary" ? (
        summaryQuery.isPending ? (
          <SectionLoadingState />
        ) : summaryQuery.error && !isAbortError(summaryQuery.error) ? (
          summaryQuery.error instanceof ApiError && summaryQuery.error.status === 403 ? (
            <SectionUnavailableState />
          ) : (
            <SectionErrorState onRetry={() => void summaryQuery.refetch()} />
          )
        ) : summaryQuery.data && header ? (
          <ClinicalSummary
            summary={summaryQuery.data}
            authorized={authorized}
            allergy={header.documentedAllergy}
          />
        ) : summaryQuery.data ? (
          <ClinicalSummary
            summary={summaryQuery.data}
            authorized={authorized}
            allergy="omitted"
          />
        ) : null
      ) : null}
      {view === "timeline" && loadCommitted && load ? (
        <TimelineView
          organizationId={load.orgId}
          facilityId={workFacilityId}
          patientIdentityId={canonicalId}
          generation={load.generation}
          signal={load.signal}
        />
      ) : null}
      {activeSection && sectionUnauthorized ? <SectionUnavailableState /> : null}
      {activeSection && !sectionUnauthorized && loadCommitted && load ? (
        <ClinicalSectionView
          organizationId={load.orgId}
          facilityId={workFacilityId}
          patientIdentityId={canonicalId}
          section={activeSection}
          generation={load.generation}
          signal={load.signal}
          onForbidden={() => {
            void shellQuery.refetch();
          }}
        />
      ) : null}
      </div>
    </section>
  );
}
