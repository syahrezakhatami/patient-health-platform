import { createContext, useContext } from "react";

export type AuthStatus = "loading" | "anonymous" | "authenticated" | "expired";

export interface AuthUserSummary {
  subject: string;
  displayName: string | null;
}

export interface AuthContextValue {
  status: AuthStatus;
  authenticated: boolean;
  loading: boolean;
  sessionExpired: boolean;
  user: AuthUserSummary | null;
  login: (returnTo?: string) => Promise<void>;
  logout: () => Promise<void>;
  completeCallback: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return value;
}
