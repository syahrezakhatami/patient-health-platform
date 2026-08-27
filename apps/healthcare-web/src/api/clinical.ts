import { apiRequest } from "./client";
import type {
  ChartSection,
  ChartShellResponse,
  ClinicalNoteResponse,
  ClinicalNoteType,
  ClinicalSummaryResponse,
  CreateClinicalNoteRequest,
  FinalizeClinicalNoteRequest,
  SectionPageResponse,
  TimelinePageResponse,
  UpdateClinicalNoteRequest,
} from "./generated/iam-shell";

/** Clinical Chart MVP always uses Clinical workspace purpose. Not lookup purpose. */
export const CLINICAL_CHART_PURPOSE = "TREATMENT" as const;

export const TIMELINE_PAGE_SIZE = 50;

function chartBase(patientIdentityId: string): string {
  return `/api/v1/clinical/patients/${encodeURIComponent(patientIdentityId)}/chart`;
}

export interface ClinicalReadContext {
  organizationId: string;
  facilityId?: string | null;
  patientIdentityId: string;
  signal?: AbortSignal;
}

/**
 * Work facility is sent only as X-Facility-Id via apiRequest.
 * Never append query facility_id (chart facility filter is deferred).
 */
function headers(context: ClinicalReadContext) {
  return {
    organizationId: context.organizationId,
    facilityId: context.facilityId,
    purpose: CLINICAL_CHART_PURPOSE,
    signal: context.signal,
  };
}

export async function fetchChartShell(context: ClinicalReadContext): Promise<ChartShellResponse> {
  return apiRequest<ChartShellResponse>({
    method: "GET",
    path: chartBase(context.patientIdentityId),
    ...headers(context),
  });
}

export async function fetchChartSummary(
  context: ClinicalReadContext,
): Promise<ClinicalSummaryResponse> {
  return apiRequest<ClinicalSummaryResponse>({
    method: "GET",
    path: `${chartBase(context.patientIdentityId)}/summary`,
    ...headers(context),
  });
}

export async function fetchChartTimeline(
  context: ClinicalReadContext & { cursor?: string | null },
): Promise<TimelinePageResponse> {
  const params = new URLSearchParams();
  params.set("limit", String(TIMELINE_PAGE_SIZE));
  if (context.cursor) {
    params.set("cursor", context.cursor);
  }
  return apiRequest<TimelinePageResponse>({
    method: "GET",
    path: `${chartBase(context.patientIdentityId)}/timeline?${params.toString()}`,
    ...headers(context),
  });
}

export async function fetchChartSection(
  context: ClinicalReadContext & { section: ChartSection },
): Promise<SectionPageResponse> {
  return apiRequest<SectionPageResponse>({
    method: "GET",
    path: `${chartBase(context.patientIdentityId)}/sections/${encodeURIComponent(context.section)}`,
    ...headers(context),
  });
}

export const CLINICAL_NOTE_TYPES: ClinicalNoteType[] = [
  "PROGRESS",
  "ADMISSION",
  "ED",
  "DISCHARGE",
  "OTHER",
];

export const CLINICAL_NOTE_BODY_MAX = 20_000;

export interface ClinicalNoteWriteContext {
  organizationId: string;
  facilityId?: string | null;
  signal?: AbortSignal;
  idempotencyKey?: string | null;
}

function writeHeaders(context: ClinicalNoteWriteContext) {
  return {
    organizationId: context.organizationId,
    facilityId: context.facilityId,
    purpose: CLINICAL_CHART_PURPOSE,
    signal: context.signal,
    idempotencyKey: context.idempotencyKey,
  };
}

export async function createClinicalNote(
  context: ClinicalNoteWriteContext,
  body: CreateClinicalNoteRequest,
): Promise<ClinicalNoteResponse> {
  return apiRequest<ClinicalNoteResponse>({
    method: "POST",
    path: "/api/v1/clinical/notes",
    body,
    ...writeHeaders(context),
  });
}

export async function updateClinicalNoteDraft(
  context: ClinicalNoteWriteContext,
  noteId: string,
  body: UpdateClinicalNoteRequest,
): Promise<ClinicalNoteResponse> {
  return apiRequest<ClinicalNoteResponse>({
    method: "POST",
    path: `/api/v1/clinical/notes/${encodeURIComponent(noteId)}`,
    body,
    ...writeHeaders(context),
  });
}

export async function finalizeClinicalNote(
  context: ClinicalNoteWriteContext,
  noteId: string,
  body: FinalizeClinicalNoteRequest,
): Promise<ClinicalNoteResponse> {
  return apiRequest<ClinicalNoteResponse>({
    method: "POST",
    path: `/api/v1/clinical/notes/${encodeURIComponent(noteId)}/finalize`,
    body,
    ...writeHeaders(context),
  });
}
