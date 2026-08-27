import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import { LOCALE_STORAGE_KEY } from "../tenant/tabStorage";
import en from "./locales/en.json";
import id from "./locales/id.json";

export const SUPPORTED_LOCALES = ["id", "en"] as const;
export type AppLocale = (typeof SUPPORTED_LOCALES)[number];

export function isAppLocale(value: string | null | undefined): value is AppLocale {
  return value === "id" || value === "en";
}

export function detectLocale(): AppLocale {
  const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
  if (isAppLocale(stored)) {
    return stored;
  }
  const browser = navigator.language.toLowerCase();
  if (browser.startsWith("en")) {
    return "en";
  }
  return "id";
}

export function persistLocale(locale: AppLocale): void {
  localStorage.setItem(LOCALE_STORAGE_KEY, locale);
}

export async function changeLocale(locale: AppLocale): Promise<void> {
  persistLocale(locale);
  await i18n.changeLanguage(locale);
  document.documentElement.lang = locale === "id" ? "id" : "en";
}

void i18n.use(initReactI18next).init({
  resources: {
    id: { translation: id },
    en: { translation: en },
  },
  lng: typeof window === "undefined" ? "id" : detectLocale(),
  fallbackLng: "id",
  supportedLngs: [...SUPPORTED_LOCALES],
  interpolation: { escapeValue: true },
  returnNull: false,
});

if (typeof document !== "undefined") {
  document.documentElement.lang = i18n.language === "en" ? "en" : "id";
}

export default i18n;
