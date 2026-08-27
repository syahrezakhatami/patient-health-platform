export type UnsavedWorkReason =
  | "patient"
  | "organization"
  | "facility"
  | "navigation"
  | "logout"
  | "chart-view";

type UnsavedWorkAdapter = {
  isDirty: () => boolean;
  discard: () => void;
};

type UnsavedWorkPrompt = (reason: UnsavedWorkReason) => Promise<boolean>;

let adapter: UnsavedWorkAdapter | null = null;
let prompt: UnsavedWorkPrompt | null = null;

export function registerUnsavedWorkAdapter(next: UnsavedWorkAdapter | null): void {
  adapter = next;
}

export function registerUnsavedWorkPrompt(next: UnsavedWorkPrompt | null): void {
  prompt = next;
}

export function hasUnsavedWork(): boolean {
  return adapter ? adapter.isDirty() : false;
}

export function canReplaceTenantContext(): boolean {
  return !hasUnsavedWork();
}

export function forceDiscardUnsavedWork(): void {
  adapter?.discard();
}

/** True when the caller should continue. False when the user chose Stay. */
export async function confirmDiscardUnsavedWork(reason: UnsavedWorkReason): Promise<boolean> {
  if (!hasUnsavedWork()) {
    return true;
  }
  if (!prompt) {
    return false;
  }
  const discard = await prompt(reason);
  if (discard) {
    adapter?.discard();
    return true;
  }
  return false;
}

/** @deprecated Tests and the previous silent guard still import this registrar. */
export function registerUnsavedWorkGuard(guard: (() => boolean) | null): void {
  if (!guard) {
    adapter = null;
    return;
  }
  adapter = {
    isDirty: guard,
    discard: () => undefined,
  };
}
