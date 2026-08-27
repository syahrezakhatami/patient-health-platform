import { useTranslation } from "react-i18next";

export function SectionLoadingState() {
  const { t } = useTranslation();
  return (
    <p role="status" aria-live="polite">
      {t("errors.loading")}
    </p>
  );
}

export function SectionEmptyState({ messageKey }: { messageKey: string }) {
  const { t } = useTranslation();
  return <p className="muted">{t(messageKey)}</p>;
}

export function SectionUnavailableState() {
  const { t } = useTranslation();
  return (
    <p className="notice" role="status">
      {t("chart.unavailable")}
    </p>
  );
}

export function SectionErrorState({ onRetry }: { onRetry?: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="notice" role="alert">
      <p>{t("chart.sectionError")}</p>
      {onRetry ? (
        <button type="button" className="button secondary" onClick={onRetry}>
          {t("errors.retry")}
        </button>
      ) : null}
    </div>
  );
}
