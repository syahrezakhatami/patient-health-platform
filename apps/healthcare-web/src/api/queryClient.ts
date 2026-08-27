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

export function clearPatientLookupMutations(client: QueryClient): void {
  const cache = client.getMutationCache();
  for (const mutation of cache.getAll()) {
    const key = mutation.options.mutationKey;
    if (Array.isArray(key) && key[0] === PATIENT_LOOKUP_MUTATION_KEY[0]) {
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
}
