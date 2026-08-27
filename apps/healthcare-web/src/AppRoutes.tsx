import { Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "./auth/AuthContext";
import { AppShell } from "./components/AppShell";
import { LoadingBoundary } from "./components/LoadingBoundary";
import { NotFound } from "./components/NotFound";
import { PermissionGate } from "./components/PermissionGate";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AppHomePage } from "./pages/AppHomePage";
import { CallbackPage } from "./pages/CallbackPage";
import { LoginPage } from "./pages/LoginPage";
import { SelectOrganizationPage } from "./pages/SelectOrganizationPage";
import { SessionExpiredPage } from "./pages/SessionExpiredPage";
import { UnassignedPage } from "./pages/UnassignedPage";
import {
  AdministrationWorkspacePage,
  AuditWorkspacePage,
  ClinicalWorkspacePage,
  IdentityWorkspacePage,
  RegistrationWorkspacePage,
} from "./pages/WorkspacePages";
import { APP_PATHS } from "./routing/paths";
import { useTenant } from "./tenant/TenantContext";

function TenantLayout() {
  const { phase } = useTenant();
  const { loading } = useAuth();

  if (loading || phase === "loading" || phase === "idle") {
    return <LoadingBoundary />;
  }
  if (phase === "unassigned") {
    return <Navigate to={APP_PATHS.unassigned} replace />;
  }
  if (phase === "select-organization") {
    return <Navigate to={APP_PATHS.selectOrganization} replace />;
  }
  if (phase === "error") {
    return <SelectOrganizationPage />;
  }
  return <AppShell />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path={APP_PATHS.login} element={<LoginPage />} />
      <Route path={APP_PATHS.callback} element={<CallbackPage />} />
      <Route path={APP_PATHS.sessionExpired} element={<SessionExpiredPage />} />
      <Route element={<ProtectedRoute />}>
        <Route path={APP_PATHS.selectOrganization} element={<SelectOrganizationPage />} />
        <Route path={APP_PATHS.unassigned} element={<UnassignedPage />} />
        <Route element={<TenantLayout />}>
          <Route path={APP_PATHS.app} element={<AppHomePage />} />
          <Route
            path={APP_PATHS.registration}
            element={
              <PermissionGate workspace="registration">
                <RegistrationWorkspacePage />
              </PermissionGate>
            }
          />
          <Route
            path={APP_PATHS.clinical}
            element={
              <PermissionGate workspace="clinical">
                <ClinicalWorkspacePage />
              </PermissionGate>
            }
          />
          <Route
            path={APP_PATHS.identity}
            element={
              <PermissionGate workspace="identity">
                <IdentityWorkspacePage />
              </PermissionGate>
            }
          />
          <Route
            path={APP_PATHS.audit}
            element={
              <PermissionGate workspace="audit">
                <AuditWorkspacePage />
              </PermissionGate>
            }
          />
          <Route
            path={APP_PATHS.admin}
            element={
              <PermissionGate workspace="admin">
                <AdministrationWorkspacePage />
              </PermissionGate>
            }
          />
        </Route>
      </Route>
      <Route path="/" element={<Navigate to={APP_PATHS.app} replace />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
