import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { APP_PATHS } from "../routing/paths";

export function NotFound() {
  const { t } = useTranslation();
  return (
    <section className="panel">
      <h1>{t("errors.notFoundTitle")}</h1>
      <p>{t("errors.notFoundBody")}</p>
      <p>
        <Link to={APP_PATHS.app}>{t("nav.home")}</Link>
      </p>
    </section>
  );
}
