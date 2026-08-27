import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { useAuth } from "../auth/AuthContext";
import { stripOidcCallbackParams } from "../auth/callback";
import { APP_PATHS } from "../routing/paths";

export function CallbackPage() {
  const { t } = useTranslation();
  const { completeCallback } = useAuth();
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    void completeCallback()
      .then(() => {
        stripOidcCallbackParams();
      })
      .catch(() => {
        stripOidcCallbackParams();
        setFailed(true);
      });
  }, [completeCallback]);

  if (failed) {
    return (
      <section className="panel" role="alert">
        <h1>{t("auth.callbackError")}</h1>
        <a href={APP_PATHS.login}>{t("auth.signIn")}</a>
      </section>
    );
  }

  return (
    <section className="panel" role="status">
      <h1>{t("auth.callbackTitle")}</h1>
    </section>
  );
}