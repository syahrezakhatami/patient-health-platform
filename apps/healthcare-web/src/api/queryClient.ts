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

export function removeTenantScopedQueries(client: QueryClient, organizationId: string): void {
  void client.cancelQueries({ queryKey: queryKeys.context(organizationId) });
  void client.cancelQueries({ queryKey: queryKeys.accessibleFacilities(organizationId) });
  void client.removeQueries({ queryKey: queryKeys.context(organizationId) });
  void client.removeQueries({ queryKey: queryKeys.accessibleFacilities(organizationId) });
  void client.removeQueries({
    predicate: (query) => query.queryKey.includes(organizationId),
  });
}
