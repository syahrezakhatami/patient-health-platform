import { createContext, useContext } from "react";

import type {
  AccessibleFacilityDTO,
  AccessibleOrganizationDTO,
  FacilityScopeKind,
  StaffContextResponse,
  StaffSessionUserDTO,
} from "../api/generated/iam-shell";

export type TenantPhase =
  | "idle"
  | "loading"
  | "unassigned"
  | "select-organization"
  | "ready"
  | "error";

export interface TenantContextValue {
  phase: TenantPhase;
  provisioned: boolean;
  organizations: AccessibleOrganizationDTO[];
  selectedOrganization: AccessibleOrganizationDTO | null;
  context: StaffContextResponse | null;
  user: StaffSessionUserDTO | null;
  effectivePermissions: string[];
  roleCodes: string[];
  facilityScope: FacilityScopeKind | null;
  workFacilityRequired: boolean;
  accessibleFacilities: AccessibleFacilityDTO[];
  workFacilityId: string | null;
  workFacility: AccessibleFacilityDTO | null;
  errorMessage: string | null;
  selectOrganization: (organizationId: string) => Promise<void>;
  switchOrganization: (organizationId: string) => Promise<void>;
  selectWorkFacility: (facilityId: string | null) => Promise<void>;
  refreshContext: () => Promise<void>;
  handleMembershipLoss: () => Promise<void>;
}

export const TenantContext = createContext<TenantContextValue | null>(null);

export function useTenant(): TenantContextValue {
  const value = useContext(TenantContext);
  if (!value) {
    throw new Error("useTenant must be used within TenantProvider");
  }
  return value;
}
