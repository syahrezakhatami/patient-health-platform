import type { QueryClient } from "@tanstack/react-query";

import { clearClinicalQueries } from "../api/queryClient";
import { getRegisteredQueryClient } from "../auth/sessionLifecycle";
import {
  clearSelectedPatient,
  setSelectedPatient,
  type SelectedPatientSummary,
} from "../patient/selectionStore";
import { clinicalChartCoordinator } from "./clinicalChartCoordinator";

export function wipeClinicalPhi(client?: QueryClient | null): void {
  clinicalChartCoordinator.abortAndInvalidate();
  const resolved = client ?? getRegisteredQueryClient();
  if (resolved) {
    clearClinicalQueries(resolved);
  }
}

export function selectPatientAndWipeChart(summary: SelectedPatientSummary): void {
  wipeClinicalPhi();
  setSelectedPatient(summary);
}

export function closePatientAndWipeChart(): void {
  wipeClinicalPhi();
  clearSelectedPatient();
}
