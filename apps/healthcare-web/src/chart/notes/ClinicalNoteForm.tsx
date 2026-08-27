import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  CLINICAL_NOTE_BODY_MAX,
  CLINICAL_NOTE_TYPES,
  createClinicalNote,
  fetchChartSection,
  finalizeClinicalNote,
  updateClinicalNoteDraft,
} from "../../api/clinical";
import { ApiError } from "../../api/errors";
import type { ClinicalNoteResponse, ClinicalNoteType } from "../../api/generated/iam-shell";
import {
  CLINICAL_NOTE_MUTATION_KEY,
  clearClinicalNoteMutations,
  clinicalKeys,
} from "../../api/queryClient";
import { getRegisteredQueryClient } from "../../auth/sessionLifecycle";
import { usePatientSelection } from "../../patient/PatientSelectionContext";
import { isAbortError } from "../../tenant/generation";
import { hasPermission } from "../../tenant/permissions";
import { useTenant } from "../../tenant/TenantContext";
import { confirmDiscardUnsavedWork, registerUnsavedWorkAdapter } from "../../tenant/unsavedWork";
import { clinicalChartCoordinator } from "../clinicalChartCoordinator";
import { clinicalQueryPolicy } from "../queryPolicy";

const DOCUMENTABLE = new Set(["PLANNED", "IN_PROGRESS", "FINISHED"]);

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

function isMeaningfulBody(value: string): boolean {
  return value.trim().length > 0;
}

export function ClinicalNoteForm({
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
  const { selectedOrganization, workFacility, user, effectivePermissions } = useTenant();
  const [encounterId, setEncounterId] = useState("");
  const [noteType, setNoteType] = useState<ClinicalNoteType>("PROGRESS");
  const [bodyText, setBodyText] = useState("");
  const [noteId, setNoteId] = useState<string | null>(null);
  const [version, setVersion] = useState<number | null>(null);
  const [status, setStatus] = useState<"idle" | "DRAFT" | "FINAL">("idle");
  const [formGeneration, setFormGeneration] = useState(0);
  const [confirmFinalize, setConfirmFinalize] = useState(false);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [errorFocus, setErrorFocus] = useState(0);
  const createKeyRef = useRef(newIdempotencyKey());
  const finalizeKeyRef = useRef(newIdempotencyKey());
  const [savedBody, setSavedBody] = useState("");
  const errorRef = useRef<HTMLParagraphElement>(null);
  const contextRef = useRef({ organizationId, patientIdentityId, facilityId });

  const canCreate = hasPermission(effectivePermissions, "clinical.note.create");
  const canUpdate = hasPermission(effectivePermissions, "clinical.note.update_draft");
  const canFinalize = hasPermission(effectivePermissions, "clinical.note.finalize");
  const readOnly = status === "FINAL";
  const trimmed = bodyText.trim();
  const dirty =
    !readOnly &&
    isMeaningfulBody(bodyText) &&
    trimmed !== savedBody.trim();

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
    enabled: Boolean(selectedPatient && selectedPatient.organizationId === organizationId),
    ...clinicalQueryPolicy,
  });

  const encounters = useMemo(() => {
    const items = (encountersQuery.data?.items ?? []) as Array<Record<string, unknown>>;
    return items.map(asEncounter).filter((item): item is EncounterOption => item !== null);
  }, [encountersQuery.data]);

  const selectedEncounter = encounters.find((item) => item.id === encounterId) ?? null;

  useEffect(() => {
    registerUnsavedWorkAdapter({
      isDirty: () => dirty,
      discard: () => {
        setBodyText("");
        setEncounterId("");
        setNoteType("PROGRESS");
        setNoteId(null);
        setVersion(null);
        setStatus("idle");
        setConfirmFinalize(false);
        setErrorKey(null);
        setSavedBody("");
        createKeyRef.current = newIdempotencyKey();
        finalizeKeyRef.current = newIdempotencyKey();
        setFormGeneration((value) => value + 1);
        const client = getRegisteredQueryClient() ?? queryClient;
        clearClinicalNoteMutations(client);
      },
    });
    return () => {
      registerUnsavedWorkAdapter(null);
    };
  }, [dirty, queryClient]);

  useEffect(() => {
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!dirty) {
        return;
      }
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  useEffect(() => {
    if (!dirty) {
      return;
    }
    const marker = { phpClinicalNoteUnsaved: true };
    window.history.pushState(marker, "");
    let ignoreNextPop = false;
    const onPopState = () => {
      if (ignoreNextPop) {
        return;
      }
      void confirmDiscardUnsavedWork("navigation").then((ok) => {
        if (!ok) {
          window.history.pushState(marker, "");
          return;
        }
        ignoreNextPop = true;
        window.history.back();
      });
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [dirty]);

  useEffect(() => {
    const previous = contextRef.current;
    if (
      previous.organizationId !== organizationId ||
      previous.patientIdentityId !== patientIdentityId ||
      previous.facilityId !== facilityId
    ) {
      setFormGeneration((value) => value + 1);
      contextRef.current = { organizationId, patientIdentityId, facilityId };
    }
  }, [organizationId, patientIdentityId, facilityId]);

  useEffect(() => {
    if (errorKey) {
      errorRef.current?.focus();
    }
  }, [errorFocus, errorKey]);

  const matchesCommand = (vars: {
    generation: number;
    organizationId: string;
    patientIdentityId: string;
    encounterId: string;
    noteId: string | null;
  }) =>
    vars.generation === formGeneration &&
    vars.organizationId === organizationId &&
    vars.patientIdentityId === patientIdentityId &&
    vars.encounterId === encounterId &&
    vars.noteId === noteId;

  const invalidateReads = (orgId: string, patientId: string) => {
    void queryClient.invalidateQueries({
      queryKey: clinicalKeys.section(orgId, patientId, "notes"),
    });
    void queryClient.invalidateQueries({
      queryKey: clinicalKeys.timeline(orgId, patientId),
    });
  };

  const applySuccess = (note: ClinicalNoteResponse, vars: { generation: number; organizationId: string; patientIdentityId: string; encounterId: string; noteId: string | null }) => {
    invalidateReads(vars.organizationId, vars.patientIdentityId);
    clearClinicalNoteMutations(queryClient);
    if (!matchesCommand(vars)) {
      return;
    }
    setNoteId(note.id);
    setVersion(note.version);
    setStatus(note.record_status === "FINAL" ? "FINAL" : "DRAFT");
    setBodyText(note.body_text);
    setSavedBody(note.body_text);
    setErrorKey(null);
    if (note.record_status === "FINAL") {
      finalizeKeyRef.current = newIdempotencyKey();
    } else {
      createKeyRef.current = newIdempotencyKey();
    }
  };

  const mapError = (error: unknown): string => {
    if (isAbortError(error)) {
      return "note.abortNotRollback";
    }
    if (error instanceof ApiError) {
      if (error.backendCode === "note_version_conflict") {
        return "note.versionConflict";
      }
      if (error.backendCode === "note_not_draft") {
        return "note.notDraft";
      }
      if (error.backendCode === "idempotency_key_conflict") {
        return "note.idempotencyConflict";
      }
      if (error.backendCode === "encounter_facility_mismatch" || error.backendCode === "note_facility_mismatch") {
        return "note.facilityMismatch";
      }
      if (error.backendCode === "identity_not_usable") {
        return "note.identityNotUsable";
      }
      if (error.backendCode === "encounter_not_documentable") {
        return "note.encounterNotDocumentable";
      }
      if (error.status === 403) {
        return "note.forbidden";
      }
      if (error.status === 404) {
        return "note.notFound";
      }
      if (error.status === 422) {
        return "note.validation";
      }
    }
    return "note.saveFailed";
  };

  const createMutation = useMutation({
    mutationKey: CLINICAL_NOTE_MUTATION_KEY,
    retry: false,
    gcTime: 0,
    mutationFn: (vars: {
      generation: number;
      organizationId: string;
      patientIdentityId: string;
      encounterId: string;
      noteId: string | null;
      body: string;
      noteType: ClinicalNoteType;
      idempotencyKey: string;
    }) =>
      createClinicalNote(
        {
          organizationId: vars.organizationId,
          facilityId,
          signal,
          idempotencyKey: vars.idempotencyKey,
        },
        {
          expected_patient_identity_id: vars.patientIdentityId,
          encounter_id: vars.encounterId,
          note_type: vars.noteType,
          body_text: vars.body,
        },
      ),
    onSuccess: (note, vars) => applySuccess(note, vars),
    onError: (error, vars) => {
      clearClinicalNoteMutations(queryClient);
      if (!matchesCommand(vars)) {
        return;
      }
      setErrorKey(mapError(error));
      setErrorFocus((value) => value + 1);
    },
  });

  const updateMutation = useMutation({
    mutationKey: CLINICAL_NOTE_MUTATION_KEY,
    retry: false,
    gcTime: 0,
    mutationFn: (vars: {
      generation: number;
      organizationId: string;
      patientIdentityId: string;
      encounterId: string;
      noteId: string | null;
      body: string;
      expectedVersion: number;
    }) => {
      if (!vars.noteId) {
        throw new Error("missing note");
      }
      return updateClinicalNoteDraft(
        { organizationId: vars.organizationId, facilityId, signal },
        vars.noteId,
        {
          expected_patient_identity_id: vars.patientIdentityId,
          expected_version: vars.expectedVersion,
          body_text: vars.body,
        },
      );
    },
    onSuccess: (note, vars) => applySuccess(note, vars),
    onError: (error, vars) => {
      clearClinicalNoteMutations(queryClient);
      if (!matchesCommand(vars)) {
        return;
      }
      setErrorKey(mapError(error));
      setErrorFocus((value) => value + 1);
    },
  });

  const finalizeMutation = useMutation({
    mutationKey: CLINICAL_NOTE_MUTATION_KEY,
    retry: false,
    gcTime: 0,
    mutationFn: (vars: {
      generation: number;
      organizationId: string;
      patientIdentityId: string;
      encounterId: string;
      noteId: string | null;
      idempotencyKey: string;
    }) => {
      if (!vars.noteId) {
        throw new Error("missing note");
      }
      return finalizeClinicalNote(
        {
          organizationId: vars.organizationId,
          facilityId,
          signal,
          idempotencyKey: vars.idempotencyKey,
        },
        vars.noteId,
        { expected_patient_identity_id: vars.patientIdentityId },
      );
    },
    onSuccess: (note, vars) => {
      if (matchesCommand(vars)) {
        setConfirmFinalize(false);
      }
      applySuccess(note, vars);
    },
    onError: (error, vars) => {
      clearClinicalNoteMutations(queryClient);
      if (!matchesCommand(vars)) {
        return;
      }
      setErrorKey(mapError(error));
      setErrorFocus((value) => value + 1);
    },
  });

  const pending = createMutation.isPending || updateMutation.isPending || finalizeMutation.isPending;
  const bodyTooLong = bodyText.length > CLINICAL_NOTE_BODY_MAX;
  const canSave =
    !readOnly &&
    !pending &&
    !bodyTooLong &&
    isMeaningfulBody(bodyText) &&
    Boolean(encounterId) &&
    (noteId ? canUpdate : canCreate);
  const canSign = !readOnly && status === "DRAFT" && Boolean(noteId) && canFinalize && !pending;

  const saveDraft = () => {
    if (!canSave || !selectedPatient) {
      return;
    }
    setErrorKey(null);
    if (noteId && version !== null) {
      updateMutation.mutate({
        generation: formGeneration,
        organizationId,
        patientIdentityId,
        encounterId,
        noteId,
        body: bodyText,
        expectedVersion: version,
      });
      return;
    }
    createMutation.mutate({
      generation: formGeneration,
      organizationId,
      patientIdentityId,
      encounterId,
      noteId,
      body: bodyText,
      noteType,
      idempotencyKey: createKeyRef.current,
    });
  };

  if (!selectedPatient || selectedPatient.organizationId !== organizationId) {
    return null;
  }
  if (!canCreate && !noteId) {
    return null;
  }

  return (
    <form
      className="clinical-note-form"
      data-testid="clinical-note-form"
      onSubmit={(event) => {
        event.preventDefault();
        saveDraft();
      }}
    >
      <h3>{t("note.formTitle")}</h3>
      <p className="muted">{t("note.formHint")}</p>
      {errorKey ? (
        <p ref={errorRef} className="notice" role="alert" tabIndex={-1}>
          {t(errorKey)}
        </p>
      ) : null}
      <div className="field">
        <label htmlFor="clinical-note-encounter">{t("note.encounter")}</label>
        <select
          id="clinical-note-encounter"
          value={encounterId}
          disabled={Boolean(noteId) || readOnly || pending}
          onChange={(event) => setEncounterId(event.target.value)}
          required
        >
          <option value="">{t("note.chooseEncounter")}</option>
          {encounters.map((encounter) => (
            <option key={encounter.id} value={encounter.id} disabled={!DOCUMENTABLE.has(encounter.status)}>
              {encounter.display_label} · {encounter.encounter_class} · {encounter.status} · {encounter.started_at}
              {encounter.facility_id ? ` · ${encounter.facility_id}` : ""}
            </option>
          ))}
        </select>
        {encountersQuery.isError ? (
          <p className="notice" role="alert">
            {t("note.encountersUnavailable")}
          </p>
        ) : encounters.length === 0 && encountersQuery.isSuccess ? (
          <p className="muted">{t("note.noEncounters")}</p>
        ) : null}
      </div>
      {selectedEncounter ? (
        <p className="muted" data-testid="note-encounter-context">
          {selectedEncounter.encounter_class} · {selectedEncounter.status} · {selectedEncounter.started_at}
          {workFacility ? ` · ${workFacility.name}` : ""}
        </p>
      ) : null}
      <div className="field">
        <label htmlFor="clinical-note-type">{t("note.noteType")}</label>
        <select
          id="clinical-note-type"
          value={noteType}
          disabled={Boolean(noteId) || readOnly || pending}
          onChange={(event) => setNoteType(event.target.value as ClinicalNoteType)}
        >
          {CLINICAL_NOTE_TYPES.map((type) => (
            <option key={type} value={type}>
              {t(`note.types.${type}`)}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="clinical-note-body">{t("note.body")}</label>
        <textarea
          id="clinical-note-body"
          value={bodyText}
          disabled={readOnly || pending}
          required
          rows={12}
          aria-invalid={bodyTooLong || undefined}
          onChange={(event) => setBodyText(event.target.value)}
        />
        <p className="muted">
          {bodyText.length}/{CLINICAL_NOTE_BODY_MAX}
        </p>
        {bodyTooLong ? (
          <p className="notice" role="alert">
            {t("note.bodyTooLong")}
          </p>
        ) : null}
      </div>
      <p data-testid="clinical-note-status">
        {status === "FINAL" ? t("note.statusFinal") : status === "DRAFT" ? t("note.statusDraft") : t("note.statusNew")}
      </p>
      {!readOnly ? (
        <div className="modal-actions">
          <button type="submit" className="button" disabled={!canSave}>
            {pending ? t("note.saving") : t("note.saveDraft")}
          </button>
          <button
            type="button"
            className="button"
            disabled={!canSign}
            onClick={() => setConfirmFinalize(true)}
          >
            {t("note.finalize")}
          </button>
        </div>
      ) : (
        <p role="status">{t("note.finalConfirmation")}</p>
      )}
      {confirmFinalize ? (
        <div className="modal-backdrop" role="presentation">
          <div
            className="modal"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="finalize-note-title"
            aria-describedby="finalize-note-body"
          >
            <h2 id="finalize-note-title">{t("note.finalizeTitle")}</h2>
            <p id="finalize-note-body">{t("note.finalizeBody")}</p>
            <ul>
              <li>
                {t("note.patient")}: {selectedPatient.displayName}
              </li>
              <li>
                {t("note.encounter")}: {selectedEncounter?.display_label}
              </li>
              <li>
                {t("org.activeOrganization")}: {selectedOrganization?.name}
              </li>
              <li>
                {t("facility.label")}: {workFacility?.name ?? t("facility.unset")}
              </li>
              <li>
                {t("note.author")}: {user?.display_name}
              </li>
              <li>{t("note.statusDraft")}</li>
            </ul>
            <div className="modal-actions">
              <button type="button" className="button" onClick={() => setConfirmFinalize(false)}>
                {t("note.stay")}
              </button>
              <button
                type="button"
                className="button danger"
                disabled={finalizeMutation.isPending}
                onClick={() => {
                  if (!noteId) {
                    return;
                  }
                  finalizeMutation.mutate({
                    generation: formGeneration,
                    organizationId,
                    patientIdentityId,
                    encounterId,
                    noteId,
                    idempotencyKey: finalizeKeyRef.current,
                  });
                }}
              >
                {t("note.confirmFinalize")}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </form>
  );
}
