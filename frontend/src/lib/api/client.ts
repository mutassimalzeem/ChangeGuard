/**
 * The guarded HTTP client: every API call goes through here.
 *
 * Responsibilities, in order of importance:
 *   1. Attach `Authorization: Bearer <access token>` to outgoing calls.
 *   2. On a 401, refresh once and replay the original request. Concurrent 401s
 *      share a single refresh call so a token rotation never burns two tokens
 *      (the backend treats a reused refresh token as theft and revokes the
 *      whole session family). Replaying is bounded so a broken session cannot loop.
 *   3. Translate every failure into an `ApiError` with a human-readable message.
 *
 * Tokens live in memory with tab-scoped sessionStorage sync so page refreshes
 * don't lose the active session while keeping cross-origin protection.
 */
import axios, {
  AxiosError,
  type AxiosInstance,
  type AxiosRequestConfig,
  type AxiosResponse,
  type InternalAxiosRequestConfig,
} from "axios";
import { z } from "zod";

import { config } from "@/lib/config";
import { ApiError, type FieldIssue } from "./errors";

interface RetriableConfig extends InternalAxiosRequestConfig {
  /** Set once a request has been replayed, so it is never replayed again. */
  __isRetry?: boolean;
}

export interface TokenPair {
  readonly accessToken: string;
  readonly refreshToken: string | null;
}

const STORAGE_KEY = "cg_session_tokens";

/**
 * In-memory token holder, shared by the axios client and the auth provider.
 * `clear` notifies subscribers so the provider can send the user to /login.
 */
export class TokenStore {
  private accessToken: string | null = null;
  private refreshToken: string | null = null;
  private readonly listeners = new Set<() => void>();

  constructor() {
    if (typeof window !== "undefined") {
      try {
        const stored = window.sessionStorage.getItem(STORAGE_KEY);
        if (stored) {
          const parsed = JSON.parse(stored) as { accessToken?: string; refreshToken?: string | null };
          if (parsed && typeof parsed.accessToken === "string") {
            this.accessToken = parsed.accessToken;
            this.refreshToken = parsed.refreshToken ?? null;
          }
        }
      } catch {
        // sessionStorage can throw in private browsing modes
      }
    }
  }

  getAccessToken(): string | null {
    return this.accessToken;
  }

  getRefreshToken(): string | null {
    return this.refreshToken;
  }

  setTokens(pair: TokenPair): void {
    this.accessToken = pair.accessToken;
    this.refreshToken = pair.refreshToken;
    if (typeof window !== "undefined") {
      try {
        window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(pair));
      } catch {
        // ignore
      }
    }
  }

  clear(): void {
    this.accessToken = null;
    this.refreshToken = null;
    if (typeof window !== "undefined") {
      try {
        window.sessionStorage.removeItem(STORAGE_KEY);
      } catch {
        // ignore
      }
    }
    for (const listener of this.listeners) {
      listener();
    }
  }

  /** Returns an unsubscribe function. */
  subscribe(onClear: () => void): () => void {
    this.listeners.add(onClear);
    return () => {
      this.listeners.delete(onClear);
    };
  }
}

/** Shared by the client and the auth provider so both see the same session. */
export const tokenStore = new TokenStore();

/* ----------------------------------------------------------- error parsing */

const pydanticIssueSchema = z.object({
  loc: z.array(z.union([z.string(), z.number()])).optional(),
  msg: z.string().optional(),
});

const errorEnvelopeSchema = z.object({
  error: z.object({
    code: z.string().optional(),
    message: z.string().optional(),
    details: z.unknown().optional(),
  }),
});

const detailEnvelopeSchema = z.object({
  detail: z.union([
    z.string(),
    z.array(pydanticIssueSchema),
    z.record(z.string(), z.unknown()),
  ]),
});

const requestIdSchema = z.object({ request_id: z.string().optional() });

interface NormalisedError {
  message: string;
  code: string | null;
  details: unknown;
  issues: FieldIssue[];
  requestId: string | null;
}

function toFieldIssues(detail: readonly z.infer<typeof pydanticIssueSchema>[]): FieldIssue[] {
  return detail.map((issue) => {
    const location = issue.loc ?? [];
    for (let index = location.length - 1; index >= 0; index -= 1) {
      const part = location[index];
      if (typeof part === "string" && part !== "body" && part !== "query" && part !== "path") {
        return { field: part, message: issue.msg ?? "Invalid value." };
      }
    }
    return { field: "request", message: issue.msg ?? "Invalid value." };
  });
}

/**
 * Reads whatever the API returned. A non-JSON body (a gateway HTML page, an
 * empty 500) must fall back rather than throw, or the real status code is lost.
 */
export function normaliseErrorBody(body: unknown, fallback: string): NormalisedError {
  const envelope = errorEnvelopeSchema.safeParse(body);
  if (envelope.success) {
    return {
      message: envelope.data.error.message?.trim() || fallback,
      code: envelope.data.error.code ?? null,
      details: envelope.data.error.details ?? null,
      issues: [],
      requestId: null,
    };
  }

  const detailEnvelope = detailEnvelopeSchema.safeParse(body);
  if (detailEnvelope.success) {
    const detail = detailEnvelope.data.detail;
    if (typeof detail === "string") {
      return { message: detail.trim() || fallback, code: null, details: null, issues: [], requestId: null };
    }
    if (Array.isArray(detail)) {
      return {
        message: fallback,
        code: "VALIDATION_ERROR",
        details: detail,
        issues: toFieldIssues(detail),
        requestId: null,
      };
    }
    const record = detail;
    return {
      message: typeof record.message === "string" ? record.message : fallback,
      code: typeof record.code === "string" ? record.code : null,
      details: detail,
      issues: [],
      requestId: null,
    };
  }

  const requestId = requestIdSchema.safeParse(body);
  return {
    message: fallback,
    code: null,
    details: body,
    issues: [],
    requestId: requestId.success ? (requestId.data.request_id ?? null) : null,
  };
}

function statusFallback(status: number | undefined): string {
  switch (status) {
    case 400:
    case 422:
      return "The server rejected the request. Check the values and try again.";
    case 401:
      return "Your session has expired. Sign in again to continue.";
    case 403:
      return "You do not have permission for this action.";
    case 404:
      return "That record no longer exists, or you cannot access it.";
    case 409:
      return "Conflicting record. It may already exist or was modified by another user.";
    case 413:
      return "That file is too large to upload.";
    case 429:
      return "Too many attempts. Wait a moment and try again.";
    default:
      return (status ?? 0) >= 500
        ? "The server could not complete the request. Try again shortly."
        : "The request could not be completed.";
  }
}

/** Pure `AxiosError` to `ApiError` mapping, so it is unit-testable without a network. */
export function toApiError(error: AxiosError): ApiError {
  const status = error.response?.status ?? null;
  const body = error.response?.data;
  const isJson = typeof body === "object" && body !== null;

  if (axios.isCancel(error) || error.code === AxiosError.ERR_CANCELED) {
    return new ApiError({ kind: "cancelled", status, message: "The request was cancelled." });
  }

  const parsed = normaliseErrorBody(body, statusFallback(status ?? undefined));

  if (!error.response) {
    const timedOut = error.code === AxiosError.ECONNABORTED || error.code === AxiosError.ETIMEDOUT;
    return new ApiError({
      kind: timedOut ? "timeout" : "network",
      status: null,
      message: timedOut
        ? "The server took too long to respond. Try again."
        : "Cannot reach the ChangeGuard API. Check your connection and try again.",
      code: timedOut ? "TIMEOUT" : "NETWORK_ERROR",
    });
  }

  return new ApiError({
    kind: isJson ? "http" : "invalid-response",
    status,
    message: parsed.message,
    code: parsed.code,
    details: parsed.details,
    issues: parsed.issues,
    requestId: parsed.requestId,
  });
}

/* -------------------------------------------------------------- client setup */

const baseConfig = {
  baseURL: config.apiBaseUrl,
  timeout: config.requestTimeoutMs,
  withCredentials: false,
  headers: { Accept: "application/json" },
} satisfies AxiosRequestConfig;

/**
 * The session-recovery client. A 401 here means the session is over, so it must
 * never trigger (and thus never recurse into) the refresh below.
 */
const authClient: AxiosInstance = axios.create(baseConfig);

/** The guarded client every call site uses. */
const client: AxiosInstance = axios.create(baseConfig);

client.interceptors.request.use((request) => {
  const token = tokenStore.getAccessToken();
  if (token) {
    request.headers.set("Authorization", `Bearer ${token}`);
  }
  return request;
});

/* ---------------------------------------------------------- token rotation */

const REFRESH_PATH = "/auth/refresh";

async function requestTokenRefresh(): Promise<TokenPair | null> {
  const refreshToken = tokenStore.getRefreshToken();
  if (!refreshToken) {
    tokenStore.clear();
    return null;
  }
  try {
    const { data } = await authClient.post<unknown>(REFRESH_PATH, { refresh_token: refreshToken });
    if (typeof data !== "object" || data === null) {
      tokenStore.clear();
      return null;
    }
    const record = data as Record<string, unknown>;
    const accessToken = record.access_token;
    const rotated = record.refresh_token;
    if (typeof accessToken !== "string" || accessToken.length === 0) {
      tokenStore.clear();
      return null;
    }
    const pair: TokenPair = {
      accessToken,
      refreshToken: typeof rotated === "string" && rotated.length > 0 ? rotated : refreshToken,
    };
    tokenStore.setTokens(pair);
    return pair;
  } catch {
    tokenStore.clear();
    return null;
  }
}

let inFlight: Promise<TokenPair | null> | null = null;

function refreshOnce(): Promise<TokenPair | null> {
  if (inFlight === null) {
    inFlight = requestTokenRefresh().finally(() => {
      inFlight = null;
    });
  }
  return inFlight;
}

client.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error: unknown) => {
    if (!(error instanceof AxiosError)) {
      throw error;
    }
    const status = error.response?.status;
    const request = error.config as RetriableConfig | undefined;
    const canRetry =
      status === 401 &&
      request !== undefined &&
      request.__isRetry !== true &&
      request.url?.endsWith(REFRESH_PATH) !== true;

    if (!canRetry) {
      throw toApiError(error);
    }

    const pair = await refreshOnce();
    if (pair === null) {
      throw toApiError(error);
    }

    request.__isRetry = true;
    request.headers.set("Authorization", `Bearer ${pair.accessToken}`);
    return client.request(request);
  },
);

export { client };
