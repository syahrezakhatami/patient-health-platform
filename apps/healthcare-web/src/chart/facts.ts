const HIDDEN_KEYS = new Set([
  "body_text",
  "note_text",
  "lookup_value",
  "identifier_value",
  "nik",
  "bpjs",
  "raw_value",
]);

const PREFERRED_KEYS = [
  "display_label",
  "code_display",
  "code",
  "status",
  "clinical_status",
  "verification_status",
  "category",
  "record_status",
  "note_type",
  "encounter_class",
  "severity",
  "criticality",
  "dose_numeric",
  "dose_unit",
  "route",
  "unit",
  "value_text",
  "value_numeric",
  "value_boolean",
  "interpretation",
  "specimen_type",
  "relationship",
  "decision",
  "scope",
  "association_status",
  "started_at",
  "ended_at",
  "onset_at",
  "occurred_at",
  "effective_at",
  "authored_at",
  "recorded_at",
  "ordered_at",
  "collected_at",
  "finalized_at",
  "facility_id",
];

function asRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return {};
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "";
}

export function factTitle(item: Record<string, unknown>, fallback: string): string {
  return (
    formatValue(item.display_label) ||
    formatValue(item.code_display) ||
    formatValue(item.code) ||
    formatValue(item.note_type) ||
    fallback
  );
}

export function factFields(item: Record<string, unknown>): Array<{ key: string; value: string }> {
  const fields: Array<{ key: string; value: string }> = [];
  const seen = new Set<string>();
  for (const key of PREFERRED_KEYS) {
    if (HIDDEN_KEYS.has(key) || !(key in item)) {
      continue;
    }
    const value = formatValue(item[key]);
    if (!value) {
      continue;
    }
    seen.add(key);
    fields.push({ key, value });
  }
  return fields;
}

export function nestedRecords(item: Record<string, unknown>, key: string): Record<string, unknown>[] {
  const value = item[key];
  if (!Array.isArray(value)) {
    return [];
  }
  return value.map(asRecord);
}

export function asFact(item: unknown): Record<string, unknown> {
  return asRecord(item);
}

export function isVitalObservation(item: Record<string, unknown>): boolean {
  return item.category === "VITAL_SIGNS";
}
