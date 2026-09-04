import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  createManualVitalMeasurement,
  fetchManualVitalsWriteContext,
  type ManualVitalMeasurementOption,
} from "../../api/manualVitals";
import { fetchChartSection } from "../../api/clinical";
import { ApiError } from "../../api/errors";
import {
  MANUAL_VITAL_MUTATION_KEY,
  clearManualVitalMutations,
  clinicalKeys,
  manualVitalKeys,
} from "../../api/queryClient";
import { getRegisteredQueryClient } from "../../auth/sessionLifecycle";
import { usePatientSelection } from "../../patient/PatientSelectionContext";
import { isAbortError } from "../../tenant/generation";
import { hasPermission } from "../../tenant/permissions";
import { useTenant } from "../../tenant/TenantContext";
import { clinicalChartCoordinator } from "../clinicalChartCoordinator";
import { clinicalQueryPolicy } from "../queryPolicy";

export interface EncounterOption {
  id: string;
  encounter_class: string;
  status: string;
  display_label: string;
  started_at: string;
  ended_at: string | null;
  facility_id: string | null;
}

function asEncounter(item: Record<string, unknown>): EncounterOption | null {
  if (typeof item.id !== "string") {
    return null;
  }
  return {
    id: item.id,
    encounter_class: typeof item.encounter_class === "string" ? item.encounter_class : "",
    status: typeof item.status === "string" ? item.status : "",
    display_label: typeof item.display_label === "string" ? item.display_label : item.id,
    started_at: typeof item.started_at === "string" ? item.started_at : "",
    ended_at: typeof item.ended_at === "string" ? item.ended_at : null,
    facility_id: typeof item.facility_id === "string" ? item.facility_id : null,
  };
}

function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

function measurementLabel(option: ManualVitalMeasurementOption, t: (key: string) => string): string {
  switch (option.measurement_key) {
    case "heart_rate":
      return t("manualVitals.heartRate");
    case "respiratory_rate":
      return t("manualVitals.respiratoryRate");
    case "body_temperature":
      return t("manualVitals.bodyTemperature");
    case "body_weight":
      return t("manualVitals.bodyWeight");
    case "body_height":
      return t("manualVitals.bodyHeight");
    default:
      return option.canonical_concept;
  }
}

function localDateTimeInputValue(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function toOffsetIso(localValue: string): string {
  const parsed = new Date(localValue);
  if (Number.isNaN(parsed.getTime())) {
    throw new Error("invalid datetime");
  }
  return parsed.toISOString();
}

export function ManualVitalForm({
  organizationId,
  facilityId,
  patientIdentityId,
  generation,
  signal,
}: {
  organizationId: string;
  facilityId: string | null;
  patientIdentityId: string;
  generation: number;
  signal: AbortSignal;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { selectedPatient } = usePatientSelection();
  const { effectivePermissions } = useTenant();
  const [encounterId, setEncounterId] = useState("");
  const [measurementKey, setMeasurementKey] = useState("");
  const [value, setValue] = useState("");
  const [effectiveAt, setEffectiveAt] = useState(localDateTimeInputValue(new Date()));
  const [formGeneration, setFormGeneration] = useState(0);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const idempotencyRef = useRef(newIdempotencyKey());
  const contextRef = useRef({ organizationId, patientIdentityId, facilityId });

  const canCreate = hasPermission(effectivePermissions, "clinical.observation.create");
  const writeContextQuery = useQuery({
    queryKey: manualVitalKeys.writeContext(organizationId),
    queryFn: ({ signal: querySignal }) => {
      if (!clinicalChartCoordinator.isCurrent(generation)) {
        throw new DOMException("Aborted", "AbortError");
      }
      return fetchManualVitalsWriteContext({
        organizationId,
        facilityId,
        signal: querySignal,
      });
    },
    enabled: Boolean(selectedPatient && selectedPatient.organizationId === organizationId && canCreate),
    ...clinicalQueryPolicy,
  });

  const encountersQuery = useQuery({
    queryKey: clinicalKeys.section(organizationId, patientIdentityId, "encounters"),
    queryFn: ({ signal: querySignal }) => {
      if (!clinicalChartCoordinator.isCurrent(generation)) {
        throw new DOMException("Aborted", "AbortError");
      }
      return fetchChartSection({
        organizationId,
        facilityId,
        patientIdentityId,
        section: "encounters",
        signal: querySignal,
      });
    },
    enabled: Boolean(
      selectedPatient &&
        selectedPatient.organizationId === organizationId &&
        writeContextQuery.data?.available,
    ),
    ...clinicalQueryPolicy,
  });

  const measurements = writeContextQuery.data?.measurements ?? [];
  const encounters = useMemo(() => {
    const items = (encountersQuery.data?.items ?? []) as Array<Record<string, unknown>>;
    return items.map(asEncounter).filter((item): item is EncounterOption => item !== null);
  }, [encountersQuery.data]);

  useEffect(() => {
    const previous = contextRef.current;
    if (
      previous.organizationId !== organizationId ||
      previous.patientIdentityId !== patientIdentityId ||
      previous.facilityId !== facilityId
    ) {
      setEncounterId("");
      setMeasurementKey("");
      setValue("");
      setEffectiveAt(localDateTimeInputValue(new Date()));
      setErrorKey(null);
      idempotencyRef.current = newIdempotencyKey();
      setFormGeneration((current) => current + 1);
      clearManualVitalMutations(getRegisteredQueryClient() ?? queryClient);
      contextRef.current = { organizationId, patientIdentityId, facilityId };
    }
  }, [organizationId, patientIdentityId, facilityId, queryClient]);

  useEffect(() => {
    if (measurements.length === 0) {
      setMeasurementKey("");
      return;
    }
    if (!measurements.some((item) => item.measurement_key === measurementKey)) {
      setMeasurementKey(measurements[0]?.measurement_key ?? "");
    }
  }, [measurementKey, measurements]);

  const selectedMeasurement =
    measurements.find((item) => item.measurement_key === measurementKey) ??
    measurements[0] ??
    null;

  const invalidateReads = (orgId: string, patientId: string) => {
    void queryClient.invalidateQueries({
      queryKey: clinicalKeys.section(orgId, patientId, "observations"),
    });
    void queryClient.invalidateQueries({
      queryKey: clinicalKeys.timeline(orgId, patientId),
    });
    void queryClient.invalidateQueries({
      queryKey: clinicalKeys.summary(orgId, patientId),
    });
  };

  const mutation = useMutation({
    mutationKey: MANUAL_VITAL_MUTATION_KEY,
    retry: false,
    gcTime: 0,
    mutationFn: (vars: {
      generation: number;
      organizationId: string;
      patientIdentityId: string;
      encounterId: string;
      measurementKey: string;
      value: string;
      effectiveAt: string;
      idempotencyKey: string;
    }) =>
      createManualVitalMeasurement(
        {
          organizationId: vars.organizationId,
          facilityId,
          signal,
          idempotencyKey: vars.idempotencyKey,
        },
        {
          expected_patient_identity_id: vars.patientIdentityId,
          encounter_id: vars.encounterId,
          measurement_key: vars.measurementKey,
          value: vars.value,
          effective_at: vars.effectiveAt,
        },
      ),
    onSuccess: (_result, vars) => {
      invalidateReads(vars.organizationId, vars.patientIdentityId);
      clearManualVitalMutations(queryClient);
      if (
        vars.generation !== formGeneration ||
        vars.organizationId !== organizationId ||
        vars.patientIdentityId !== patientIdentityId
      ) {
        return;
      }
      setValue("");
      setErrorKey(null);
      idempotencyRef.current = newIdempotencyKey();
    },
    onError: (error, vars) => {
      clearManualVitalMutations(queryClient);
      if (
        vars.generation !== formGeneration ||
        vars.organizationId !== organizationId ||
        vars.patientIdentityId !== patientIdentityId
      ) {
        return;
      }
      if (isAbortError(error)) {
        setErrorKey("manualVitals.abortNotRollback");
        return;
      }
      if (error instanceof ApiError) {
        if (error.backendCode === "idempotency_key_conflict") {
          setErrorKey("manualVitals.idempotencyConflict");
          return;
        }
        if (error.status === 403) {
          setErrorKey("manualVitals.forbidden");
          return;
        }
        if (error.status === 404) {
          setErrorKey("manualVitals.notFound");
          return;
        }
        if (error.status === 422) {
          setErrorKey("manualVitals.validation");
          return;
        }
      }
      setErrorKey("manualVitals.saveFailed");
    },
  });

  if (!selectedPatient || selectedPatient.organizationId !== organizationId) {
    return null;
  }
  if (!canCreate || writeContextQuery.isPending) {
    return null;
  }
  if (writeContextQuery.error || !writeContextQuery.data?.available || measurements.length === 0) {
    return null;
  }

  const submit = () => {
    if (!encounterId || !measurementKey || !value.trim()) {
      setErrorKey("manualVitals.validation");
      return;
    }
    let effectiveAtIso: string;
    try {
      effectiveAtIso = toOffsetIso(effectiveAt);
    } catch {
      setErrorKey("manualVitals.validation");
      return;
    }
    setErrorKey(null);
    mutation.mutate({
      generation: formGeneration,
      organizationId,
      patientIdentityId,
      encounterId,
      measurementKey,
      value: value.trim(),
      effectiveAt: effectiveAtIso,
      idempotencyKey: idempotencyRef.current,
    });
  };

  return (
    <section className="manual-vital-form">
      <h3>{t("manualVitals.title")}</h3>
      <label>
        {t("manualVitals.encounter")}
        <select value={encounterId} onChange={(event) => setEncounterId(event.target.value)}>
          <option value="">{t("manualVitals.selectEncounter")}</option>
          {encounters.map((encounter) => (
            <option key={encounter.id} value={encounter.id}>
              {encounter.display_label} ({encounter.status})
            </option>
          ))}
        </select>
      </label>
      <label>
        {t("manualVitals.measurement")}
        <select value={measurementKey} onChange={(event) => setMeasurementKey(event.target.value)}>
          {measurements.map((option) => (
            <option key={option.measurement_key} value={option.measurement_key}>
              {measurementLabel(option, t)}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t("manualVitals.value")}
        <input
          inputMode="decimal"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          aria-label={t("manualVitals.value")}
        />
        {selectedMeasurement ? (
          <span className="muted">{selectedMeasurement.display_unit}</span>
        ) : null}
      </label>
      <label>
        {t("manualVitals.effectiveAt")}
        <input
          type="datetime-local"
          value={effectiveAt}
          onChange={(event) => setEffectiveAt(event.target.value)}
        />
      </label>
      {errorKey ? <p role="alert">{t(errorKey)}</p> : null}
      <button type="button" disabled={mutation.isPending} onClick={submit}>
        {t("manualVitals.save")}
      </button>
    </section>
  );
}
