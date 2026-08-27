import type { ChartSection } from "../api/generated/iam-shell";
import { SECTION_LABEL_KEY } from "./catalog";

export type ChartView = "summary" | "timeline" | ChartSection;

export function ChartNavigation({
  sections,
  view,
  onChange,
  t,
}: {
  sections: ChartSection[];
  view: ChartView;
  onChange: (view: ChartView) => void;
  t: (key: string) => string;
}) {
  const items: Array<{ id: ChartView; label: string }> = [
    { id: "summary", label: t("chart.summary") },
    ...sections.map((section) => ({ id: section, label: t(SECTION_LABEL_KEY[section]) })),
    { id: "timeline", label: t("chart.timeline") },
  ];

  return (
    <nav className="chart-nav" aria-label={t("chart.navLabel")}>
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            <button
              type="button"
              className={view === item.id ? "chart-nav-current" : undefined}
              aria-current={view === item.id ? "page" : undefined}
              onClick={() => onChange(item.id)}
            >
              {item.label}
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}
