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
