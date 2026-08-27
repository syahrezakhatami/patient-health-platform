const CALLBACK_PARAMS = ["code", "state", "session_state", "iss", "error", "error_description", "error_uri"];

export function stripOidcCallbackParams(): void {
  if (typeof window === "undefined") {
    return;
  }
  const url = new URL(window.location.href);
  let changed = false;
  for (const key of CALLBACK_PARAMS) {
    if (url.searchParams.has(key)) {
      url.searchParams.delete(key);
      changed = true;
    }
  }
  if (url.hash) {
    url.hash = "";
    changed = true;
  }
  if (changed) {
    const next = `${url.pathname}${url.search}`;
    window.history.replaceState({}, document.title, next || "/");
  }
}

export function callbackHasOidcError(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  return Boolean(new URLSearchParams(window.location.search).get("error"));
}

export function callbackLooksMalformed(): boolean {
  if (typeof window === "undefined") {
    return false;
  }
  const params = new URLSearchParams(window.location.search);
  if (params.get("error")) {
    return false;
  }
  const code = params.get("code");
  const state = params.get("state");
  if (!code || !state) {
    return true;
  }
  return false;
}
