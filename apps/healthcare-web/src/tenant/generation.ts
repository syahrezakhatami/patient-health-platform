export class TenantLoadCoordinator {
  private generation = 0;
  private controller: AbortController | null = null;

  begin(): { generation: number; signal: AbortSignal } {
    this.controller?.abort();
    this.controller = new AbortController();
    this.generation += 1;
    return { generation: this.generation, signal: this.controller.signal };
  }

  isCurrent(generation: number): boolean {
    return generation === this.generation;
  }

  abort(): void {
    this.controller?.abort();
    this.controller = null;
  }

  abortAndInvalidate(): void {
    this.abort();
    this.generation += 1;
  }
}

export function isAbortError(error: unknown): boolean {
  return (
    (error instanceof DOMException && error.name === "AbortError") ||
    (error instanceof Error && error.name === "AbortError")
  );
}

/** Abort when any of the provided signals abort (coordinator + TanStack Query). */
export function mergeAbortSignals(
  ...signals: Array<AbortSignal | undefined>
): AbortSignal | undefined {
  const present = signals.filter((item): item is AbortSignal => Boolean(item));
  if (present.length === 0) {
    return undefined;
  }
  if (present.length === 1) {
    return present[0];
  }
  if (typeof AbortSignal.any === "function") {
    return AbortSignal.any(present);
  }
  const controller = new AbortController();
  for (const signal of present) {
    if (signal.aborted) {
      controller.abort();
      break;
    }
    signal.addEventListener("abort", () => controller.abort(), { once: true });
  }
  return controller.signal;
}
