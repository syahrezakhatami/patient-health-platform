import { createContext, useContext } from "react";

import type { SelectedPatientSummary } from "./selectionStore";

export interface PatientSelectionContextValue {
  selectedPatient: SelectedPatientSummary | null;
  clearSelection: () => void;
}

export const PatientSelectionContext = createContext<PatientSelectionContextValue | null>(null);

export function usePatientSelection(): PatientSelectionContextValue {
  const value = useContext(PatientSelectionContext);
  if (!value) {
    throw new Error("usePatientSelection must be used within PatientSelectionProvider");
  }
  return value;
}
