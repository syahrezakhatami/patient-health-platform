export type ApiErrorCode =
  | "session_expired"
  | "permission_denied"
  | "not_found"
  | "conflict"
  | "validation"
  | "rate_limited"
  | "server_error"
  | "network"
  | "unknown";

export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode;
  readonly correlationId: string | null;

  constructor(status: number, code: ApiErrorCode, message: string, correlationId: string | null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.correlationId = correlationId;
  }
}

const STATUS_CODE: Record<number, ApiErrorCode> = {
  401: "session_expired",
  403: "permission_denied",
  404: "not_found",
  409: "conflict",
  422: "validation",
  429: "rate_limited",
};

export function mapStatusToCode(status: number): ApiErrorCode {
  if (status === 0) {
    return "network";
  }
  if (STATUS_CODE[status]) {
    return STATUS_CODE[status];
  }
  if (status >= 500) {
    return "server_error";
  }
  return "unknown";
}

export function userFacingMessage(code: ApiErrorCode): string {
  switch (code) {
    case "session_expired":
      return "Your session has expired. Sign in again.";
    case "permission_denied":
      return "You do not have permission to complete this action.";
    case "not_found":
      return "The requested resource was not found.";
    case "conflict":
      return "The record changed. Refresh and try again.";
    case "validation":
      return "The request could not be processed with the current context.";
    case "rate_limited":
      return "Too many attempts. Try again later.";
    case "server_error":
      return "The service is temporarily unavailable.";
    case "network":
      return "The network request failed.";
    default:
      return "Something went wrong.";
  }
}

function looksLikeJwt(value: string): boolean {
  return value.split(".").length === 3 && value.length > 40;
}

export function sanitizeErrorText(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }
  if (looksLikeJwt(value) || /bearer\s+/i.test(value) || /authorization/i.test(value)) {
    return null;
  }
  return value;
}

interface BackendErrorBody {
  error?: {
    code?: unknown;
    message?: unknown;
    correlation_id?: unknown;
  };
}

export function parseApiError(status: number, body: unknown): ApiError {
  const code = mapStatusToCode(status);
  let correlationId: string | null = null;
  if (body && typeof body === "object") {
    const error = (body as BackendErrorBody).error;
    if (error && typeof error.correlation_id === "string") {
      correlationId = error.correlation_id;
    }
  }
  return new ApiError(status, code, userFacingMessage(code), correlationId);
}

export function shouldRetryRequest(failureCount: number, error: unknown): boolean {
  if (error instanceof Error && error.name === "AbortError") {
    return false;
  }
  if (error instanceof ApiError) {
    if ([401, 403, 404, 409, 422, 429].includes(error.status)) {
      return false;
    }
    if (error.status >= 500) {
      return failureCount < 2;
    }
    return false;
  }
  return failureCount < 2;
}
