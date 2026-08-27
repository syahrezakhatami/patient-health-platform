/**
 * Extension point for future unsaved clinical forms.
 * Organization/facility switch, logout, and session expiry must consult this
 * before replacing tenant context. This shell has no form state yet.
 */
type UnsavedWorkGuard = () => boolean;

let unsavedWorkGuard: UnsavedWorkGuard | null = null;

export function registerUnsavedWorkGuard(guard: UnsavedWorkGuard | null): void {
  unsavedWorkGuard = guard;
}

export function hasUnsavedWork(): boolean {
  return unsavedWorkGuard ? unsavedWorkGuard() : false;
}

export function canReplaceTenantContext(): boolean {
  return !hasUnsavedWork();
}
