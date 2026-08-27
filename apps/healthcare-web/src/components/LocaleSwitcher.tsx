import { useTranslation } from "react-i18next";

import { changeLocale, type AppLocale } from "../i18n";

export function LocaleSwitcher() {
  const { t, i18n } = useTranslation();
  const current = (i18n.language.startsWith("en") ? "en" : "id") as AppLocale;
  return (
    <div className="field" style={{ margin: 0 }}>
      <label htmlFor="locale-switcher">{t("locale.label")}</label>
      <select
        id="locale-switcher"
        value={current}
        onChange={(event) => {
          void changeLocale(event.target.value as AppLocale);
        }}
      >
        <option value="id">{t("locale.id")}</option>
        <option value="en">{t("locale.en")}</option>
      </select>
    </div>
  );
}
