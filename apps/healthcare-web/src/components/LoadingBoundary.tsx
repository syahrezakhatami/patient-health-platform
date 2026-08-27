import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

interface LoadingBoundaryProps {
  children?: ReactNode;
  label?: string;
}

export function LoadingBoundary({ children, label }: LoadingBoundaryProps) {
  const { t } = useTranslation();
  return (
    <div role="status" aria-live="polite" className="panel">
      <p>{label ?? t("errors.loading")}</p>
      {children}
    </div>
  );
}
