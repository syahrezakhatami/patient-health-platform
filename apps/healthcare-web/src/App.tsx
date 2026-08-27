import { useState, type ReactNode } from "react";
import { QueryClientProvider } from "@tanstack/react-query";

import { createAppQueryClient } from "./api/queryClient";
import { AuthProvider } from "./auth/AuthProvider";
import { registerQueryClient } from "./auth/sessionLifecycle";
import { AppRoutes } from "./AppRoutes";
import { UnsavedWorkDialog } from "./components/UnsavedWorkDialog";
import { PatientSelectionProvider } from "./patient/PatientSelectionProvider";
import { TenantProvider } from "./tenant/TenantProvider";

export function AppProviders({ children }: { children: ReactNode }) {
  const [client] = useState(() => {
    const queryClient = createAppQueryClient();
    registerQueryClient(queryClient);
    return queryClient;
  });

  return (
    <QueryClientProvider client={client}>
      <AuthProvider>
        <TenantProvider>
          <PatientSelectionProvider>
            <UnsavedWorkDialog />
            {children}
          </PatientSelectionProvider>
        </TenantProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default function App() {
  return (
    <AppProviders>
      <AppRoutes />
    </AppProviders>
  );
}
