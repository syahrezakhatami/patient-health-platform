import { render, type RenderOptions } from "@testing-library/react";

import { AppRoutes } from "../AppRoutes";
import { setAccessTokenForTests } from "../auth/tokenStore";
import { TestAppHarness } from "./TestAppHarness";
import "../i18n";

export function renderApp(initialPath = "/app", options?: RenderOptions) {
  return render(
    <TestAppHarness initialPath={initialPath}>
      <AppRoutes />
    </TestAppHarness>,
    options,
  );
}

export function authenticateStaff(): void {
  setAccessTokenForTests("test-staff-token");
}

export function mockJsonFetch(
  impl: (url: string, init?: RequestInit) => { status?: number; body: unknown } | null,
): void {
  globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const result = impl(url, init);
    if (!result) {
      return new Response(JSON.stringify({ error: { code: "not_found", message: "not found" } }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify(result.body), {
      status: result.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  };
}

export function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => {
    resolve = next;
  });
  return { promise, resolve };
}
