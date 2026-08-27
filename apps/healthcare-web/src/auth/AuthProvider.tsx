import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { isOidcConfigured } from "../config";
import { clearTabTenantStorage } from "../tenant/tabStorage";
import { clearPatientAndChartFilter } from "../tenant/clinicalBoundary";
import { AuthContext, type AuthStatus, type AuthUserSummary } from "./AuthContext";
import {
  completeLoginCallback,
  logoutAtIdentityProvider,
  resetOidcClient,
  restoreOidcUser,
  startLogin,
} from "./oidc";
import { consumeReturnTo } from "./returnTo";
import {
  clearSensitiveClientState,
  registerSessionHandler,
  resetSessionExpiryLock,
  type SessionExpiredReason,
} from "./sessionLifecycle";
import { getAccessToken } from "./tokenStore";

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const navigate = useNavigate();
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [user, setUser] = useState<AuthUserSummary | null>(null);

  const applyAuthenticated = useCallback(() => {
    resetSessionExpiryLock();
    setUser({ subject: "staff", displayName: null });
    setStatus("authenticated");
  }, []);

  const clearLocalSession = useCallback(() => {
    clearSensitiveClientState();
    void resetOidcClient();
    clearTabTenantStorage();
    clearPatientAndChartFilter();
    setUser(null);
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (getAccessToken()) {
        if (!cancelled) {
          applyAuthenticated();
        }
        return;
      }
      if (!isOidcConfigured()) {
        if (!cancelled) {
          setStatus("anonymous");
        }
        return;
      }
      try {
        const restored = await restoreOidcUser();
        if (cancelled) {
          return;
        }
        if (restored && getAccessToken()) {
          applyAuthenticated();
          return;
        }
      } catch {
        // Discovery/network failure is not a password fallback.
      }
      if (!cancelled) {
        setStatus("anonymous");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [applyAuthenticated]);

  useEffect(() => {
    registerSessionHandler((reason: SessionExpiredReason) => {
      clearLocalSession();
      setStatus(reason === "logout" ? "anonymous" : "expired");
      if (reason === "logout") {
        navigate("/login", { replace: true });
        return;
      }
      navigate("/session-expired", { replace: true });
    });
    return () => {
      registerSessionHandler(() => undefined);
    };
  }, [clearLocalSession, navigate]);

  const login = useCallback(async (returnTo?: string) => {
    await startLogin(returnTo);
  }, []);

  const completeCallback = useCallback(async () => {
    await completeLoginCallback();
    if (!getAccessToken()) {
      setStatus("anonymous");
      navigate("/login", { replace: true });
      return;
    }
    applyAuthenticated();
    navigate(consumeReturnTo(), { replace: true });
  }, [applyAuthenticated, navigate]);

  const logout = useCallback(async () => {
    clearLocalSession();
    setStatus("anonymous");
    if (isOidcConfigured()) {
      try {
        await logoutAtIdentityProvider();
        return;
      } catch {
        navigate("/login", { replace: true });
        return;
      }
    }
    navigate("/login", { replace: true });
  }, [clearLocalSession, navigate]);

  const value = useMemo(
    () => ({
      status,
      authenticated: status === "authenticated",
      loading: status === "loading",
      sessionExpired: status === "expired",
      user,
      login,
      logout,
      completeCallback,
    }),
    [status, user, login, logout, completeCallback],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
