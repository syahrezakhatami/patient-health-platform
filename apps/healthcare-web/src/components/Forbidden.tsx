import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { APP_PATHS } from "../routing/paths";

export function Forbidden({ title, body }: { title?: string; body?: string }) {
  const { t } = useTranslation();
  return (
    <section className="panel" role="alert">
      <h1>{title ?? t("errors.forbiddenTitle")}</h1>
      <p>{body ?? t("errors.forbiddenBody")}</p>
      <p>
        <Link to={APP_PATHS.app}>{t("nav.home")}</Link>
      </p>
    </section>
  );
}
