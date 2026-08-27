import { useMemo, useSyncExternalStore, type ReactNode } from "react";

import { useTenant } from "../tenant/TenantContext";
import { closePatientAndWipeChart } from "../chart/wipe";
import { PatientSelectionContext } from "./PatientSelectionContext";
import {
  getSelectedPatient,
  selectedPatientForOrganization,
  subscribeSelectedPatient,
} from "./selectionStore";

export function PatientSelectionProvider({ children }: { children: ReactNode }) {
  const { selectedOrganization } = useTenant();
  useSyncExternalStore(subscribeSelectedPatient, getSelectedPatient, getSelectedPatient);
  const organizationId = selectedOrganization?.organization_id ?? null;
  const selectedPatient = selectedPatientForOrganization(organizationId);

  const value = useMemo(
    () => ({
      selectedPatient,
      clearSelection: closePatientAndWipeChart,
    }),
    [selectedPatient],
  );

  return (
    <PatientSelectionContext.Provider value={value}>{children}</PatientSelectionContext.Provider>
  );
}
