import { useMutation } from "@tanstack/react-query";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import type { RequestPurpose } from "../api/client";
import { ApiError } from "../api/errors";
import type {
  PatientLookupResponse,
  PatientLookupResult,
  PatientLookupType,
} from "../api/generated/iam-shell";
import { PATIENT_LOOKUP_MUTATION_KEY } from "../api/queryClient";
import { lookupPatients } from "../api/patients";
import { isAbortError } from "../tenant/generation";
import { useTenant } from "../tenant/TenantContext";
import { patientLookupCoordinator } from "./lookupCoordinator";
import { setSelectedPatient, summaryFromLookupResult } from "./selectionStore";

const LOOKUP_TYPES: PatientLookupType[] = ["MRN", "NIK", "BPJS", "PATIENT_IDENTITY_ID"];

function isAnonymousKind(kind: string): boolean {
  return kind === "ANONYMOUS" || kind === "TEMPORARY";
}

export function PatientLookupPanel({ purpose }: { purpose: RequestPurpose }) {
  const { t } = useTranslation();
  const headingId = useId();
  const { selectedOrganization, workFacilityId, effectivePermissions } = useTenant();
  const organizationId = selectedOrganization?.organization_id ?? null;
  const [lookupType, setLookupType] = useState<PatientLookupType>("MRN");
  const [lookupValue, setLookupValue] = useState("");
  const [result, setResult] = useState<PatientLookupResponse | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const resultHeadingRef = useRef<HTMLHeadingElement | null>(null);
  const organizationIdRef = useRef(organizationId);

  const canLookup = effectivePermissions.includes("mpi.identity.read");

  const mutation = useMutation({
    mutationKey: PATIENT_LOOKUP_MUTATION_KEY,
    mutationFn: lookupPatients,
    retry: false,
    gcTime: 0,
  });

  useEffect(() => {
    organizationIdRef.current = organizationId;
  }, [organizationId]);

  useEffect(() => {
    return () => {
      patientLookupCoordinator.abortAndInvalidate();
    };
  }, []);

  useEffect(() => {
    if (result) {
      resultHeadingRef.current?.focus();
    }
  }, [result]);

  const submitting = mutation.isPending;

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    const value = lookupValue.trim();
    if (!organizationId || !canLookup || !value) {
      return;
    }
    const { generation, signal } = patientLookupCoordinator.begin();
    const requestOrganizationId = organizationId;
    setResult(null);
    setStatusMessage(null);
    mutation.reset();
    mutation.mutate(
      {
        organizationId: requestOrganizationId,
        facilityId: workFacilityId,
        purpose,
        body: { lookup_type: lookupType, lookup_value: value },
        signal,
      },
      {
        onSuccess: (data) => {
          if (!patientLookupCoordinator.isCurrent(generation)) {
            return;
          }
          if (organizationIdRef.current !== requestOrganizationId) {
            return;
          }
          setResult(data);
          if (data.outcome === "none") {
            setStatusMessage(t("patient.noMatch"));
          } else if (data.outcome === "ambiguous") {
            setStatusMessage(t("patient.ambiguous"));
          } else if (data.outcome === "review_required") {
            setStatusMessage(t("patient.reviewRequired"));
          } else {
            setStatusMessage(t("patient.confirmPrompt"));
          }
        },
        onError: (error) => {
          if (isAbortError(error) || !patientLookupCoordinator.isCurrent(generation)) {
            return;
          }
          if (organizationIdRef.current !== requestOrganizationId) {
            return;
          }
          setResult(null);
          setStatusMessage(lookupErrorMessage(error, t));
        },
      },
    );
  };

  const selectPatient = (hit: PatientLookupResult) => {
    if (!organizationId || !hit.selectable) {
      return;
    }
    setSelectedPatient(summaryFromLookupResult(hit, organizationId));
    setLookupValue("");
    setResult(null);
    mutation.reset();
    setStatusMessage(t("patient.selected"));
  };

  const organizationName = selectedOrganization?.name ?? "—";

  const results = result?.results ?? [];
  const showConfirmation = result?.outcome === "one" && results.length === 1 && results[0]?.selectable;

  if (!canLookup) {
    return (
      <section className="patient-lookup" aria-labelledby={headingId}>
        <h2 id={headingId}>{t("patient.lookupTitle")}</h2>
        <p>{t("patient.lookupForbidden")}</p>
      </section>
    );
  }

  return (
    <section className="patient-lookup" aria-labelledby={headingId}>
      <h2 id={headingId}>{t("patient.lookupTitle")}</h2>
      <p>
        {t("org.activeOrganization")}: <strong data-testid="lookup-active-organization">{organizationName}</strong>
      </p>
      <form onSubmit={onSubmit}>
        <div className="field">
          <label htmlFor="patient-lookup-type">{t("patient.lookupType")}</label>
          <select
            id="patient-lookup-type"
            value={lookupType}
            onChange={(event) => setLookupType(event.target.value as PatientLookupType)}
          >
            {LOOKUP_TYPES.map((type) => (
              <option key={type} value={type}>
                {t(`patient.types.${type}`)}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="patient-lookup-value">{t("patient.lookupValue")}</label>
          <input
            id="patient-lookup-value"
            name="lookup_value"
            autoComplete="off"
            spellCheck={false}
            value={lookupValue}
            onChange={(event) => setLookupValue(event.target.value)}
          />
        </div>
        <button type="submit" className="button" disabled={!lookupValue.trim()}>
          {submitting ? t("patient.searching") : t("patient.search")}
        </button>
      </form>
      <div aria-live="polite" className="patient-lookup-status">
        {statusMessage ? <p role="status">{statusMessage}</p> : null}
      </div>
      {result ? (
        <div className="patient-lookup-results">
          <h3 ref={resultHeadingRef} tabIndex={-1}>
            {t("patient.resultsTitle")}
          </h3>
          {result.outcome === "none" ? <p>{t("patient.noMatchBody")}</p> : null}
          {result.outcome === "ambiguous" || result.truncated ? (
            <p>{t("patient.ambiguousBody")}</p>
          ) : null}
          {result.outcome === "review_required" ? <p>{t("patient.reviewRequiredBody")}</p> : null}
          {results.map((hit) => (
            <article
              key={hit.patient_identity_id}
              className="patient-confirmation-card"
              data-testid="patient-confirmation-card"
            >
              <dl>
                <div>
                  <dt>{t("patient.name")}</dt>
                  <dd>{hit.display_name}</dd>
                </div>
                <div>
                  <dt>{t("patient.dob")}</dt>
                  <dd>{hit.birth_date ?? t("patient.unknown")}</dd>
                </div>
                <div>
                  <dt>{t("patient.sex")}</dt>
                  <dd>{hit.administrative_sex ?? t("patient.unknown")}</dd>
                </div>
                <div>
                  <dt>{t("patient.mrn")}</dt>
                  <dd>{hit.organization_mrn ?? t("patient.unknown")}</dd>
                </div>
                <div>
                  <dt>{t("org.activeOrganization")}</dt>
                  <dd>{organizationName}</dd>
                </div>
              </dl>
              {isAnonymousKind(hit.identity_kind) ? (
                <p className="notice">{t("patient.anonymous")}</p>
              ) : null}
              {showConfirmation && hit.selectable ? (
                <button type="button" className="button" onClick={() => selectPatient(hit)}>
                  {t("patient.selectPatient")}
                </button>
              ) : null}
            </article>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function lookupErrorMessage(error: unknown, t: (key: string) => string): string {
  if (!(error instanceof ApiError)) {
    return t("errors.generic");
  }
  if (error.status === 409) {
    return t("patient.retired");
  }
  if (error.status === 429) {
    return t("errors.rateLimited");
  }
  if (error.status === 403) {
    return t("errors.forbiddenBody");
  }
  if (error.status === 422) {
    return t("patient.invalidLookup");
  }
  return t("errors.generic");
}
