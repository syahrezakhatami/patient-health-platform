import { QueryClient } from "@tanstack/react-query";

import { shouldRetryRequest } from "./errors";

export function createAppQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        refetchOnWindowFocus: true,
        refetchOnReconnect: true,
        retry: shouldRetryRequest,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

export const queryKeys = {
  organizations: () => ["iam-organizations"] as const,
  context: (organizationId: string) => ["iam-context", organizationId] as const,
  accessibleFacilities: (organizationId: string) =>
    ["accessible-facilities", organizationId] as const,
};

export const PATIENT_LOOKUP_MUTATION_KEY = ["patient-lookup"] as const;
export const CLINICAL_NOTE_MUTATION_KEY = ["clinical-note-write"] as const;

export const CLINICAL_GC_TIME_MS = 5 * 60_000;
export const CLINICAL_STALE_TIME_MS = 30_000;

export const clinicalKeys = {
  chart: (organizationId: string, patientIdentityId: string) =>
    ["clinical-chart", organizationId, patientIdentityId] as const,
  summary: (organizationId: string, patientIdentityId: string) =>
    ["clinical-summary", organizationId, patientIdentityId] as const,
  section: (organizationId: string, patientIdentityId: string, section: string) =>
    ["clinical-section", organizationId, patientIdentityId, section] as const,
  timeline: (organizationId: string, patientIdentityId: string) =>
    ["clinical-timeline", organizationId, patientIdentityId] as const,
};

export function isClinicalQueryKey(queryKey: readonly unknown[]): boolean {
  const head = queryKey[0];
  return (
    head === "clinical-chart" ||
    head === "clinical-summary" ||
    head === "clinical-section" ||
    head === "clinical-timeline"
  );
}

export function clearClinicalQueries(client: QueryClient): void {
  void client.cancelQueries({ predicate: (query) => isClinicalQueryKey(query.queryKey) });
  client.removeQueries({ predicate: (query) => isClinicalQueryKey(query.queryKey) });
}

export function clearDownstreamClinicalQueries(client: QueryClient): void {
  void client.cancelQueries({
    predicate: (query) => {
      const head = query.queryKey[0];
      return head === "clinical-summary" || head === "clinical-section" || head === "clinical-timeline";
    },
  });
  client.removeQueries({
    predicate: (query) => {
      const head = query.queryKey[0];
      return head === "clinical-summary" || head === "clinical-section" || head === "clinical-timeline";
    },
  });
}

/** Drop clinical PHI for other patients after the current load token is committed. */
export function retainCurrentClinicalQueries(
  client: QueryClient,
  organizationId: string,
  patientIdentityIds: readonly string[],
): void {
  const keep = new Set(patientIdentityIds.filter(Boolean));
  client.removeQueries({
    predicate: (query) => {
      if (!isClinicalQueryKey(query.queryKey)) {
        return false;
      }
      return query.queryKey[1] !== organizationId || !keep.has(String(query.queryKey[2] ?? ""));
    },
  });
}

export function clearPatientLookupMutations(client: QueryClient): void {
  const cache = client.getMutationCache();
  for (const mutation of cache.getAll()) {
    const key = mutation.options.mutationKey;
    if (Array.isArray(key) && key[0] === PATIENT_LOOKUP_MUTATION_KEY[0]) {
      cache.remove(mutation);
    }
  }
}

export function clearClinicalNoteMutations(client: QueryClient): void {
  const cache = client.getMutationCache();
  for (const mutation of cache.getAll()) {
    const key = mutation.options.mutationKey;
    if (Array.isArray(key) && key[0] === CLINICAL_NOTE_MUTATION_KEY[0]) {
      cache.remove(mutation);
    }
  }
}

export function removeTenantScopedQueries(client: QueryClient, organizationId: string): void {
  void client.cancelQueries({ queryKey: queryKeys.context(organizationId) });
  void client.cancelQueries({ queryKey: queryKeys.accessibleFacilities(organizationId) });
  void client.removeQueries({ queryKey: queryKeys.context(organizationId) });
  void client.removeQueries({ queryKey: queryKeys.accessibleFacilities(organizationId) });
  void client.removeQueries({
    predicate: (query) => query.queryKey.includes(organizationId),
  });
  clearPatientLookupMutations(client);
  clearClinicalNoteMutations(client);
  clearClinicalQueries(client);
}
