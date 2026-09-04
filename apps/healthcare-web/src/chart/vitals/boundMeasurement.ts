import type { ManualVitalMeasurementOption } from "../../api/manualVitals";

/** Display and selection bind only to an exact selected measurement_key. */
export function boundMeasurement(
  measurements: readonly ManualVitalMeasurementOption[],
  measurementKey: string,
): ManualVitalMeasurementOption | null {
  if (!measurementKey) {
    return null;
  }
  return measurements.find((item) => item.measurement_key === measurementKey) ?? null;
}
