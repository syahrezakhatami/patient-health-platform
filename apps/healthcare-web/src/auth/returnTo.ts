const INTERNAL_PREFIXES = [
  "/app",
  "/select-organization",
  "/unassigned",
] as const;

function decodeCandidate(value: string): string | null {
  let current = value.trim();
  for (let i = 0; i < 3; i += 1) {
    try {
      const decoded = decodeURIComponent(current.replace(/\+/g, " "));
      if (decoded === current) {
        break;
      }
      current = decoded;
    } catch {
      return null;
    }
  }
  return current;
}

function isInternalPath(path: string): boolean {
  const lower = path.toLowerCase();
  if (
    lower.startsWith("javascript:") ||
    lower.startsWith("data:") ||
    lower.startsWith("vbscript:")
  ) {
    return false;
  }
  if (!path.startsWith("/") || path.startsWith("//") || path.includes("://")) {
    return false;
  }
  if (path.includes("\\") || path.includes("@")) {
    return false;
  }
  const pathname = path.split("?")[0]?.split("#")[0] ?? path;
  return INTERNAL_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

/** Reject open redirects. Only same-origin app paths are allowed. */
export function safeReturnTo(candidate: string | null | undefined, fallback = "/app"): string {
  if (!candidate) {
    return fallback;
  }
  const decoded = decodeCandidate(candidate);
  if (!decoded || !isInternalPath(decoded)) {
    return fallback;
  }
  return decoded;
}

export const RETURN_TO_STORAGE_KEY = "php.healthcare-web.return-to";

export function storeReturnTo(path: string): void {
  sessionStorage.setItem(RETURN_TO_STORAGE_KEY, safeReturnTo(path));
}

export function consumeReturnTo(): string {
  const stored = sessionStorage.getItem(RETURN_TO_STORAGE_KEY);
  sessionStorage.removeItem(RETURN_TO_STORAGE_KEY);
  return safeReturnTo(stored);
}
