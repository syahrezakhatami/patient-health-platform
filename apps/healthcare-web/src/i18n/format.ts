import type { AppLocale } from "./index";

export function formatDate(value: Date, locale: AppLocale): string {
  return new Intl.DateTimeFormat(locale === "id" ? "id-ID" : "en-GB", {
    dateStyle: "medium",
  }).format(value);
}

export function formatNumber(value: number, locale: AppLocale): string {
  return new Intl.NumberFormat(locale === "id" ? "id-ID" : "en-GB").format(value);
}
