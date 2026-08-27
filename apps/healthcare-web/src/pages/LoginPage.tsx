import { Navigate, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useState } from "react";

import { useAuth } from "../auth/AuthContext";
import { isOidcConfigured } from "../config";
import { safeReturnTo } from "../auth/returnTo";
import { APP_PATHS } from "../routing/paths";

export function LoginPage() {
  const { t } = useTranslation();
  const { login, authenticated } = useAuth();
  const location = useLocation();
  const [started, setStarted] = useState(false);
  const from =
    location.state && typeof location.state === "object" && "from" in location.state
      ? safeReturnTo(String((location.state as { from?: string }).from))
      : APP_PATHS.app;

  if (authenticated) {
    return <Navigate to={from} replace />;
  }

  return (
    <section className="panel">
      <h1>{t("auth.loginTitle")}</h1>
      <p>{t("auth.loginBody")}</p>
      {!isOidcConfigured() ? <p role="alert">{t("auth.oidcMissing")}</p> : null}
      <button
        type="button"
        className="button"
        disabled={!isOidcConfigured() || started}
        onClick={() => {
          setStarted(true);
          void login(from);
        }}
      >
        {started ? t("auth.signingIn") : t("auth.signIn")}
      </button>
    </section>
  );
}
