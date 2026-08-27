import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuth } from "../auth/AuthContext";
import { APP_PATHS } from "../routing/paths";

export function SessionExpired() {
  const { t } = useTranslation();
  const { login } = useAuth();
  return (
    <section className="panel" role="status">
      <h1>{t("auth.sessionExpiredTitle")}</h1>
      <p>{t("auth.sessionExpiredBody")}</p>
      <button type="button" className="button" onClick={() => void login(APP_PATHS.app)}>
        {t("auth.signIn")}
      </button>
      <p>
        <Link to={APP_PATHS.login}>{t("auth.signIn")}</Link>
      </p>
    </section>
  );
}
