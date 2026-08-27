import { apiRequest, type RequestPurpose } from "./client";
import type { PatientLookupRequest, PatientLookupResponse } from "./generated/iam-shell";

export async function lookupPatients(options: {
  organizationId: string;
  facilityId?: string | null;
  purpose: RequestPurpose;
  body: PatientLookupRequest;
  signal?: AbortSignal;
}): Promise<PatientLookupResponse> {
  return apiRequest<PatientLookupResponse>({
    method: "POST",
    path: "/api/v1/mpi/patients/lookup",
    organizationId: options.organizationId,
    facilityId: options.facilityId,
    purpose: options.purpose,
    body: options.body,
    signal: options.signal,
  });
}
