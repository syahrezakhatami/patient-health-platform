import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { APP_PATHS } from "../routing/paths";
import { LoadingBoundary } from "./LoadingBoundary";

/**
 * UX gate only. Backend authorization remains the security boundary.
 */
export function ProtectedRoute({ children }: { children?: ReactNode }) {
  const { authenticated, loading, sessionExpired } = useAuth();
  const location = useLocation();

  if (loading) {
    return <LoadingBoundary />;
  }
  if (sessionExpired) {
    return <Navigate to={APP_PATHS.sessionExpired} replace />;
  }
  if (!authenticated) {
    return <Navigate to={APP_PATHS.login} replace state={{ from: location.pathname }} />;
  }
  return children ?? <Outlet />;
}
