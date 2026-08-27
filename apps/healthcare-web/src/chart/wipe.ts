import type { QueryClient } from "@tanstack/react-query";

import { clearClinicalNoteMutations, clearClinicalQueries } from "../api/queryClient";
import { getRegisteredQueryClient } from "../auth/sessionLifecycle";
import {
  clearSelectedPatient,
  setSelectedPatient,
  type SelectedPatientSummary,
} from "../patient/selectionStore";
import { confirmDiscardUnsavedWork, forceDiscardUnsavedWork } from "../tenant/unsavedWork";
import { clinicalChartCoordinator } from "./clinicalChartCoordinator";

export function wipeClinicalPhi(client?: QueryClient | null): void {
  forceDiscardUnsavedWork();
  clinicalChartCoordinator.abortAndInvalidate();
  const resolved = client ?? getRegisteredQueryClient();
  if (resolved) {
    clearClinicalQueries(resolved);
    clearClinicalNoteMutations(resolved);
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

export async function requestClosePatientAndWipeChart(): Promise<boolean> {
  if (!(await confirmDiscardUnsavedWork("patient"))) {
    return false;
  }
  closePatientAndWipeChart();
  return true;
}

export async function requestSelectPatientAndWipeChart(
  summary: SelectedPatientSummary,
): Promise<boolean> {
  if (!(await confirmDiscardUnsavedWork("patient"))) {
    return false;
  }
  selectPatientAndWipeChart(summary);
  return true;
}
