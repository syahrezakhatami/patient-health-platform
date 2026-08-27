import { useTranslation } from "react-i18next";

import { useAuth } from "../auth/AuthContext";

export function UnassignedPage() {
  const { t } = useTranslation();
  const { logout } = useAuth();
  return (
    <section className="panel" role="status">
      <h1>{t("org.unassignedTitle")}</h1>
      <p>{t("org.unassignedBody")}</p>
      <button type="button" className="button danger" onClick={() => void logout()}>
        {t("auth.signOut")}
      </button>
    </section>
  );
}
