/**
 * A single error type for the whole data layer.
 *
 * The API replies with `{ detail: ... }` for `HTTPException` (a string, or a
 * list of Pydantic issues) and with `{ error: { code, message, details } }` for
 * `ChangeGuardException`. Both shapes collapse here so components only need to
 * branch on `status` and read `message`.
 */

export type ApiErrorKind =
  | "http"
  | "network"
  | "timeout"
  | "cancelled"
  | "invalid-response";

export interface FieldIssue {
  /** Dotted location of the offending value, e.g. `contract_value`. */
  readonly field: string;
  readonly message: string;
}

export interface ApiErrorInit {
  kind: ApiErrorKind;
  status: number | null;
  message: string;
  code?: string | null;
  details?: unknown;
  issues?: readonly FieldIssue[];
  requestId?: string | null;
}

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly code: string | null;
  readonly details: unknown;
  readonly issues: readonly FieldIssue[];
  readonly requestId: string | null;

  constructor(init: ApiErrorInit) {
    super(init.message);
    this.name = "ApiError";
    this.kind = init.kind;
    this.status = init.status;
    this.code = init.code ?? null;
    this.details = init.details ?? null;
    this.issues = init.issues ?? [];
    this.requestId = init.requestId ?? null;
  }

  /** The session is gone or the credentials were rejected. */
  get isAuthError(): boolean {
    return this.status === 401;
  }

  /** Authenticated, but the role does not grant the action. */
  get isForbidden(): boolean {
    return this.status === 403;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }

  /** The API is unreachable, slow, or broken: retrying is reasonable. */
  get isTransient(): boolean {
    return this.kind === "network" || this.kind === "timeout" || (this.status ?? 0) >= 500;
  }
}

export function isApiError(value: unknown): value is ApiError {
  return value instanceof ApiError;
}

/** Message suitable for an error state, never an empty string. */
export function errorMessage(error: unknown, fallback = "Something went wrong."): string {
  if (isApiError(error) && error.message.trim().length > 0) {
    return error.message;
  }
  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }
  return fallback;
}
