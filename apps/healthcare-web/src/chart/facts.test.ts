import { describe, expect, it } from "vitest";

import { asFact, factFields, isVitalObservation, nestedRecords } from "./facts";

describe("clinical fact presentation", () => {
  it("never surfaces note body or identifier secrets", () => {
    const fields = factFields(
      asFact({
        code_display: "Progress note",
        note_type: "PROGRESS",
        body_text: "SECRET-BODY",
        note_text: "SECRET-NOTE",
        nik: "1234567890123456",
        bpjs: "BPJS-1",
        identifier_value: "NIK-RAW",
      }),
    );
    const blob = JSON.stringify(fields);
    expect(blob).toContain("Progress note");
    expect(blob).not.toContain("SECRET-BODY");
    expect(blob).not.toContain("SECRET-NOTE");
    expect(blob).not.toContain("1234567890123456");
    expect(blob).not.toContain("BPJS-1");
  });

  it("groups vitals by category without hiding or double-counting other observations", () => {
    const vital = asFact({ id: "v1", category: "VITAL_SIGNS", code_display: "HR" });
    const lab = asFact({ id: "o1", category: "LABORATORY", code_display: "Na" });
    const items = [vital, lab];
    const vitals = items.filter(isVitalObservation);
    const rest = items.filter((item) => !isVitalObservation(item));
    expect(vitals).toHaveLength(1);
    expect(rest).toHaveLength(1);
    expect(vitals[0]?.id).toBe("v1");
    expect(rest[0]?.id).toBe("o1");
    expect([...vitals, ...rest]).toHaveLength(items.length);
  });

  it("does not invent omitted laboratory nested layers", () => {
    const order = asFact({ id: "lab-1", code_display: "CBC" });
    expect(nestedRecords(order, "specimens")).toEqual([]);
    expect(nestedRecords(order, "results")).toEqual([]);
  });
});
