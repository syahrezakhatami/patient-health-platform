import { describe, expect, it } from "vitest";

import { boundMeasurement } from "./boundMeasurement";

const CATALOG = [
  {
    measurement_key: "heart_rate",
    display_unit: "beats/min",
    canonical_concept: "Heart rate",
  },
  {
    measurement_key: "respiratory_rate",
    display_unit: "breaths/min",
    canonical_concept: "Respiratory rate",
  },
  {
    measurement_key: "body_temperature",
    display_unit: "Cel",
    canonical_concept: "Body temperature",
  },
  {
    measurement_key: "body_weight",
    display_unit: "kg",
    canonical_concept: "Body weight",
  },
  {
    measurement_key: "body_height",
    display_unit: "cm",
    canonical_concept: "Body height",
  },
] as const;

describe("boundMeasurement", () => {
  it("does not infer a unit from catalog position when no key is selected", () => {
    expect(boundMeasurement(CATALOG, "")).toBeNull();
    expect(boundMeasurement(CATALOG, "heart_rate")?.display_unit).toBe("beats/min");
  });

  it("binds each catalog key to its own unit", () => {
    expect(boundMeasurement(CATALOG, "heart_rate")?.display_unit).toBe("beats/min");
    expect(boundMeasurement(CATALOG, "respiratory_rate")?.display_unit).toBe("breaths/min");
    expect(boundMeasurement(CATALOG, "body_temperature")?.display_unit).toBe("Cel");
    expect(boundMeasurement(CATALOG, "body_weight")?.display_unit).toBe("kg");
    expect(boundMeasurement(CATALOG, "body_height")?.display_unit).toBe("cm");
  });

  it("does not keep a stale key after the site subset drops it", () => {
    const temperatureOnly = CATALOG.filter((item) => item.measurement_key === "body_temperature");
    expect(boundMeasurement(temperatureOnly, "heart_rate")).toBeNull();
    expect(boundMeasurement(temperatureOnly, "body_temperature")?.display_unit).toBe("Cel");
  });

  it("does not bind unsupported or unknown keys", () => {
    expect(boundMeasurement(CATALOG, "spo2")).toBeNull();
    expect(boundMeasurement(CATALOG, "blood_pressure")).toBeNull();
  });
});
