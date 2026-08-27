import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { fetchAccessibleFacilities, fetchMyContext, fetchMyOrganizations } from "../api/iam";
import { ApiError } from "../api/errors";
import { queryKeys, removeTenantScopedQueries } from "../api/queryClient";
import type {
  AccessibleFacilityDTO,
  AccessibleOrganizationDTO,
  FacilityScopeKind,
  StaffContextResponse,
  StaffSessionUserDTO,
} from "../api/generated/iam-shell";
import { useAuth } from "../auth/AuthContext";
import { resolveOrganizationChoice } from "./bootstrap";
import {
  clearPatientAndChartFilter,
  clearFacilityDependentCommandState,
} from "./clinicalBoundary";
import { resolveWorkFacilityChoice } from "./facilityPolicy";
import { isAbortError, TenantLoadCoordinator } from "./generation";
import {
  clearTabTenantStorage,
  readStoredOrganizationId,
  readStoredWorkFacilityId,
  writeStoredOrganizationId,
  writeStoredWorkFacilityId,
} from "./tabStorage";
import { TenantContext, type TenantContextValue, type TenantPhase } from "./TenantContext";
import { canReplaceTenantContext } from "./unsavedWork";

interface TenantProviderProps {
  children: ReactNode;
}

const emptyPermissions: string[] = [];

const idleTenant: TenantContextValue = {
  phase: "idle",
  provisioned: false,
  organizations: [],
  selectedOrganization: null,
  context: null,
  user: null,
  effectivePermissions: emptyPermissions,
  roleCodes: emptyPermissions,
  facilityScope: null,
  workFacilityRequired: false,
  accessibleFacilities: [],
  workFacilityId: null,
  workFacility: null,
  errorMessage: null,
  selectOrganization: async () => undefined,
  switchOrganization: async () => undefined,
  selectWorkFacility: () => undefined,
  refreshContext: async () => undefined,
  handleMembershipLoss: async () => undefined,
};

function AuthenticatedTenantProvider({ children }: TenantProviderProps) {
  const queryClient = useQueryClient();
  const [coordinator] = useState(() => new TenantLoadCoordinator());
  const [phase, setPhase] = useState<TenantPhase>("loading");
  const [provisioned, setProvisioned] = useState(false);
  const [organizations, setOrganizations] = useState<AccessibleOrganizationDTO[]>([]);
  const [selectedOrganization, setSelectedOrganization] = useState<AccessibleOrganizationDTO | null>(
    null,
  );
  const [context, setContext] = useState<StaffContextResponse | null>(null);
  const [user, setUser] = useState<StaffSessionUserDTO | null>(null);
  const [accessibleFacilities, setAccessibleFacilities] = useState<AccessibleFacilityDTO[]>([]);
  const [workFacilityId, setWorkFacilityId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const resetTenantState = useCallback(() => {
    setSelectedOrganization(null);
    setContext(null);
    setAccessibleFacilities([]);
    setWorkFacilityId(null);
    setErrorMessage(null);
    clearPatientAndChartFilter();
    clearFacilityDependentCommandState();
  }, []);

  const activateOrganization = useCallback(
    async (organizationId: string, previousOrganizationId: string | null) => {
      if (!canReplaceTenantContext()) {
        return;
      }
      if (previousOrganizationId && previousOrganizationId !== organizationId) {
        removeTenantScopedQueries(queryClient, previousOrganizationId);
        writeStoredWorkFacilityId(null);
        setWorkFacilityId(null);
        clearPatientAndChartFilter();
        clearFacilityDependentCommandState();
        setContext(null);
        setAccessibleFacilities([]);
      }

      const { generation, signal } = coordinator.begin();
      const listed = organizations.find((organization) => organization.organization_id === organizationId);
      if (listed) {
        setSelectedOrganization(listed);
      }

      const nextContext = await fetchMyContext(organizationId, signal);
      const facilities = await fetchAccessibleFacilities(organizationId, signal);
      if (!coordinator.isCurrent(generation)) {
        return;
      }
      if (nextContext.organization.organization_id !== organizationId) {
        return;
      }
      if (facilities.organization_id !== organizationId) {
        return;
      }

      const facilityChoice = resolveWorkFacilityChoice({
        facilityScope: nextContext.facility_scope,
        workFacilityRequired: nextContext.work_facility_required,
        facilities: facilities.facilities,
        storedFacilityId:
          previousOrganizationId && previousOrganizationId !== organizationId
            ? null
            : readStoredWorkFacilityId(),
      });

      let nextFacilityId: string | null = null;
      if (facilityChoice.kind === "auto" || facilityChoice.kind === "restore") {
        nextFacilityId = facilityChoice.facilityId;
      }
      if (nextFacilityId && !facilities.facilities.some((facility) => facility.id === nextFacilityId)) {
        nextFacilityId = null;
      }

      queryClient.setQueryData(queryKeys.context(organizationId), nextContext);
      queryClient.setQueryData(queryKeys.accessibleFacilities(organizationId), facilities);
      writeStoredOrganizationId(organizationId);
      writeStoredWorkFacilityId(nextFacilityId);
      setContext(nextContext);
      setUser(nextContext.user);
      setSelectedOrganization(nextContext.organization);
      setAccessibleFacilities(facilities.facilities);
      setWorkFacilityId(nextFacilityId);
      setPhase("ready");
    },
    [coordinator, organizations, queryClient],
  );

  const bootstrap = useCallback(async () => {
    try {
      const { generation, signal } = coordinator.begin();
      const listed = await fetchMyOrganizations(signal);
      if (!coordinator.isCurrent(generation)) {
        return;
      }
      setProvisioned(listed.provisioned);
      setOrganizations(listed.organizations ?? []);
      if (listed.user) {
        setUser(listed.user);
      }
      const resolution = resolveOrganizationChoice({
        organizations: listed.organizations,
        storedOrganizationId: readStoredOrganizationId(),
      });
      if (resolution.kind === "unassigned") {
        resetTenantState();
        writeStoredOrganizationId(null);
        writeStoredWorkFacilityId(null);
        setPhase("unassigned");
        return;
      }
      if (resolution.kind === "select") {
        setSelectedOrganization(null);
        setContext(null);
        setPhase("select-organization");
        return;
      }
      await activateOrganization(resolution.organizationId, null);
    } catch (error) {
      if (isAbortError(error)) {
        return;
      }
      if (error instanceof ApiError && error.status === 401) {
        return;
      }
      setErrorMessage(error instanceof ApiError ? error.message : null);
      setPhase("error");
    }
  }, [activateOrganization, coordinator, resetTenantState]);

  useEffect(() => {
    // Defer so oxlint react(set-state-in-effect) does not treat post-await
    // setState as synchronous. Race safety is TenantLoadCoordinator + AbortSignal.
    const handle = window.setTimeout(() => {
      void bootstrap();
    }, 0);
    return () => {
      window.clearTimeout(handle);
      coordinator.abort();
    };
  }, [bootstrap, coordinator]);

  const selectOrganization = useCallback(
    async (organizationId: string) => {
      try {
        await activateOrganization(organizationId, selectedOrganization?.organization_id ?? null);
      } catch (error) {
        if (isAbortError(error)) {
          return;
        }
        if (error instanceof ApiError && (error.status === 403 || error.status === 404)) {
          await bootstrap();
          return;
        }
        if (error instanceof ApiError && error.status === 401) {
          return;
        }
        setErrorMessage(error instanceof ApiError ? error.message : null);
        setPhase("error");
      }
    },
    [activateOrganization, bootstrap, selectedOrganization],
  );

  const switchOrganization = useCallback(
    async (organizationId: string) => {
      if (organizationId === selectedOrganization?.organization_id) {
        return;
      }
      await selectOrganization(organizationId);
    },
    [selectOrganization, selectedOrganization],
  );

  const selectWorkFacility = useCallback(
    (facilityId: string | null) => {
      if (facilityId === workFacilityId) {
        return;
      }
      if (facilityId && !accessibleFacilities.some((facility) => facility.id === facilityId)) {
        return;
      }
      if (!canReplaceTenantContext()) {
        return;
      }
      clearFacilityDependentCommandState();
      setWorkFacilityId(facilityId);
      writeStoredWorkFacilityId(facilityId);
    },
    [accessibleFacilities, workFacilityId],
  );

  const refreshContext = useCallback(async () => {
    const organizationId = selectedOrganization?.organization_id;
    if (!organizationId) {
      return;
    }
    try {
      await activateOrganization(organizationId, organizationId);
    } catch (error) {
      if (isAbortError(error)) {
        return;
      }
      if (error instanceof ApiError && (error.status === 403 || error.status === 404)) {
        writeStoredOrganizationId(null);
        writeStoredWorkFacilityId(null);
        resetTenantState();
        await bootstrap();
      }
    }
  }, [activateOrganization, bootstrap, resetTenantState, selectedOrganization]);

  useEffect(() => {
    if (phase !== "ready") {
      return;
    }
    const onFocus = () => {
      void refreshContext();
    };
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [phase, refreshContext]);

  const handleMembershipLoss = useCallback(async () => {
    const previous = selectedOrganization?.organization_id;
    if (previous) {
      removeTenantScopedQueries(queryClient, previous);
    }
    clearTabTenantStorage();
    resetTenantState();
    await bootstrap();
  }, [bootstrap, queryClient, resetTenantState, selectedOrganization]);

  const workFacility =
    accessibleFacilities.find((facility) => facility.id === workFacilityId) ?? null;

  const value = useMemo(
    () => ({
      phase,
      provisioned,
      organizations,
      selectedOrganization,
      context,
      user,
      effectivePermissions: context?.effective_permissions ?? emptyPermissions,
      roleCodes: context?.role_codes ?? selectedOrganization?.role_codes ?? emptyPermissions,
      facilityScope: (context?.facility_scope ?? null) as FacilityScopeKind | null,
      workFacilityRequired: context?.work_facility_required ?? false,
      accessibleFacilities,
      workFacilityId,
      workFacility,
      errorMessage,
      selectOrganization,
      switchOrganization,
      selectWorkFacility,
      refreshContext,
      handleMembershipLoss,
    }),
    [
      phase,
      provisioned,
      organizations,
      selectedOrganization,
      context,
      user,
      accessibleFacilities,
      workFacilityId,
      workFacility,
      errorMessage,
      selectOrganization,
      switchOrganization,
      selectWorkFacility,
      refreshContext,
      handleMembershipLoss,
    ],
  );

  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>;
}

export function TenantProvider({ children }: TenantProviderProps) {
  const { authenticated } = useAuth();
  if (!authenticated) {
    return <TenantContext.Provider value={idleTenant}>{children}</TenantContext.Provider>;
  }
  return <AuthenticatedTenantProvider>{children}</AuthenticatedTenantProvider>;
}
