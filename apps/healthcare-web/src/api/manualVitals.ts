import { apiRequest } from "./client";
import { CLINICAL_CHART_PURPOSE } from "./clinical";

export interface ManualVitalMeasurementOption {
  measurement_key: string;
  display_unit: string;
  canonical_concept: string;
}

export interface ManualVitalsWriteContext {
  available: boolean;
  catalog_version: string | null;
  feature_version: string | null;
  measurements: ManualVitalMeasurementOption[];
}

export interface CreateManualVitalMeasurementRequest {
  expected_patient_identity_id: string;
  encounter_id: string;
  measurement_key: string;
  value: string;
  effective_at: string;
}

export interface ManualVitalWriteContext {
  organizationId: string;
  facilityId?: string | null;
  signal?: AbortSignal;
  idempotencyKey?: string;
}

function manualVitalsPath(organizationId: string): string {
  return `/api/v1/organizations/${encodeURIComponent(organizationId)}/clinical/manual-vitals/measurements`;
}

function headers(context: ManualVitalWriteContext) {
  return {
    organizationId: context.organizationId,
    facilityId: context.facilityId,
    purpose: CLINICAL_CHART_PURPOSE,
    signal: context.signal,
    idempotencyKey: context.idempotencyKey,
  };
}

export async function fetchManualVitalsWriteContext(
  context: ManualVitalWriteContext,
): Promise<ManualVitalsWriteContext> {
  return apiRequest<ManualVitalsWriteContext>({
    method: "GET",
    path: manualVitalsPath(context.organizationId),
    ...headers(context),
  });
}

export async function createManualVitalMeasurement(
  context: ManualVitalWriteContext,
  body: CreateManualVitalMeasurementRequest,
): Promise<Record<string, unknown>> {
  return apiRequest<Record<string, unknown>>({
    method: "POST",
    path: manualVitalsPath(context.organizationId),
    body,
    ...headers(context),
  });
}
