import { describe, expect, it } from "vitest";

import { mergeAbortSignals, TenantLoadCoordinator } from "./generation";

describe("TenantLoadCoordinator", () => {
  it("increments generation on begin and abortAndInvalidate, but not on abort", () => {
    const coordinator = new TenantLoadCoordinator();
    const first = coordinator.begin();
    expect(coordinator.isCurrent(first.generation)).toBe(true);
    coordinator.abort();
    expect(coordinator.isCurrent(first.generation)).toBe(true);
    expect(first.signal.aborted).toBe(true);
    coordinator.abortAndInvalidate();
    expect(coordinator.isCurrent(first.generation)).toBe(false);
    const second = coordinator.begin();
    expect(second.generation).toBeGreaterThan(first.generation);
    expect(coordinator.isCurrent(second.generation)).toBe(true);
  });
});

describe("mergeAbortSignals", () => {
  it("aborts when either TanStack or coordinator signal aborts", () => {
    const tanstack = new AbortController();
    const coordinator = new AbortController();
    const merged = mergeAbortSignals(tanstack.signal, coordinator.signal);
    expect(merged).toBeDefined();
    expect(merged?.aborted).toBe(false);
    coordinator.abort();
    expect(merged?.aborted).toBe(true);
  });

  it("uses once listeners in the fallback path so abort does not leak handlers", () => {
    const original = AbortSignal.any.bind(AbortSignal);
    const added: boolean[] = [];
    Object.defineProperty(AbortSignal, "any", { configurable: true, value: undefined });
    try {
      const first = new AbortController();
      const second = new AbortController();
      const add = first.signal.addEventListener.bind(first.signal);
      first.signal.addEventListener = (
        type: string,
        listener: EventListenerOrEventListenerObject,
        options?: boolean | AddEventListenerOptions,
      ) => {
        added.push(typeof options === "object" && options.once === true);
        add(type, listener, options);
      };
      const merged = mergeAbortSignals(first.signal, second.signal);
      first.abort();
      expect(merged?.aborted).toBe(true);
      expect(added.every(Boolean)).toBe(true);
    } finally {
      Object.defineProperty(AbortSignal, "any", { configurable: true, value: original });
    }
  });
});
