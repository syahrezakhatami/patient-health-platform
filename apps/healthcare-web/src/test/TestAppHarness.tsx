import { QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";

import { createAppQueryClient } from "../api/queryClient";
import { AuthProvider } from "../auth/AuthProvider";
import { registerQueryClient } from "../auth/sessionLifecycle";
import { UnsavedWorkDialog } from "../components/UnsavedWorkDialog";
import { PatientSelectionProvider } from "../patient/PatientSelectionProvider";
import { TenantProvider } from "../tenant/TenantProvider";

export function TestAppHarness({
  children,
  initialPath,
}: {
  children: ReactNode;
  initialPath: string;
}) {
  const [client] = useState(() => {
    const queryClient = createAppQueryClient();
    registerQueryClient(queryClient);
    return queryClient;
  });
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialPath]}>
        <AuthProvider>
          <TenantProvider>
            <PatientSelectionProvider>
              <UnsavedWorkDialog />
              {children}
            </PatientSelectionProvider>
          </TenantProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}
