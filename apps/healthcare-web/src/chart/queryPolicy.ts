import { shouldRetryRequest } from "../api/errors";
import { CLINICAL_GC_TIME_MS, CLINICAL_STALE_TIME_MS } from "../api/queryClient";

export const clinicalQueryPolicy = {
  staleTime: CLINICAL_STALE_TIME_MS,
  gcTime: CLINICAL_GC_TIME_MS,
  refetchOnWindowFocus: false,
  refetchOnReconnect: false,
  retry: shouldRetryRequest,
  placeholderData: undefined,
} as const;
