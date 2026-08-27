import { apiRequest } from "./client";
import type {
  AccessibleFacilitiesResponse,
  StaffContextResponse,
  StaffOrganizationsResponse,
} from "./generated/iam-shell";

export async function fetchMyOrganizations(signal?: AbortSignal): Promise<StaffOrganizationsResponse> {
  const response = await apiRequest<StaffOrganizationsResponse>({
    path: "/api/v1/iam/me/organizations",
    signal,
  });
  return {
    ...response,
    organizations: response.organizations ?? [],
    user: response.user ?? null,
  };
}

export async function fetchMyContext(
  organizationId: string,
  signal?: AbortSignal,
): Promise<StaffContextResponse> {
  return apiRequest<StaffContextResponse>({
    path: "/api/v1/iam/me/context",
    organizationId,
    signal,
  });
}

export async function fetchAccessibleFacilities(
  organizationId: string,
  signal?: AbortSignal,
): Promise<AccessibleFacilitiesResponse> {
  return apiRequest<AccessibleFacilitiesResponse>({
    path: `/api/v1/organizations/${organizationId}/facilities/accessible`,
    organizationId,
    signal,
  });
}
