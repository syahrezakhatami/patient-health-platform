import type { ChartSection } from "../api/generated/iam-shell";

/** Frozen ChartSection enum order. Navigation intersects this with authorized_sections. */
export const CHART_SECTION_ORDER: readonly ChartSection[] = [
  "encounters",
  "notes",
  "conditions",
  "observations",
  "laboratory",
  "medications",
  "allergies",
  "consents",
  "immunizations",
  "procedures",
  "medical-devices",
  "adverse-events",
  "family-histories",
];

const KNOWN = new Set<string>(CHART_SECTION_ORDER);

export function isChartSection(value: string): value is ChartSection {
  return KNOWN.has(value);
}

export function visibleAuthorizedSections(authorized: readonly string[]): ChartSection[] {
  const allowed = new Set<ChartSection>();
  for (const item of authorized) {
    if (isChartSection(item)) {
      allowed.add(item);
    }
    // Unknown slugs are ignored. Do not log the value: it is a server code, but
    // diagnostics must never include patient identifiers or clinical text.
  }
  return CHART_SECTION_ORDER.filter((section) => allowed.has(section));
}

export const SECTION_LABEL_KEY: Record<ChartSection, string> = {
  encounters: "chart.sections.encounters",
  notes: "chart.sections.notes",
  conditions: "chart.sections.conditions",
  observations: "chart.sections.observations",
  laboratory: "chart.sections.laboratory",
  medications: "chart.sections.medications",
  allergies: "chart.sections.allergies",
  consents: "chart.sections.consents",
  immunizations: "chart.sections.immunizations",
  procedures: "chart.sections.procedures",
  "medical-devices": "chart.sections.medicalDevices",
  "adverse-events": "chart.sections.adverseEvents",
  "family-histories": "chart.sections.familyHistories",
};
