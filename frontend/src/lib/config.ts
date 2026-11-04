/**
 * Client configuration, read once from environment variables.
 *
 * Only `NEXT_PUBLIC_*` variables are readable in the browser: they are inlined
 * at build time, so their values are public. Nothing secret belongs here.
 */

const DEFAULT_API_BASE_URL = "http://localhost:8000/api/v1";
const DEFAULT_QUERY_STALE_TIME_MS = 30000;
const DEFAULT_REQUEST_TIMEOUT_MS = 20000;

/** Environment passed to Next.js (or a hand-built object in tests). */
export type ClientEnv = Readonly<Record<string, string | undefined>>;

export class ConfigError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ConfigError";
  }
}

export interface AppConfig {
  /** Absolute API root, e.g. http://localhost:8000/api/v1. Never ends with a slash. */
  readonly apiBaseUrl: string;
  /** How long fetched data stays fresh before it is refetched. */
  readonly queryStaleTimeMs: number;
  /** Per-request ceiling before axios aborts with a timeout error. */
  readonly requestTimeoutMs: number;
}

export function parseApiBaseUrl(value: string): URL {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new ConfigError(["NEXT_PUBLIC_API_BASE_URL must be an absolute URL, received", value].join(" "));
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new ConfigError(["NEXT_PUBLIC_API_BASE_URL must use http or https, received", value].join(" "));
  }
  if (url.search || url.hash) {
    throw new ConfigError("NEXT_PUBLIC_API_BASE_URL must not contain a query string or fragment.");
  }
  return url;
}

function parseStaleTimeMs(value: string | undefined): number {
  const text = value?.trim();
  if (typeof text !== "string" || !text) return DEFAULT_QUERY_STALE_TIME_MS;
  const parsed = Number(text);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : DEFAULT_QUERY_STALE_TIME_MS;
}

export function loadConfig(env: ClientEnv): AppConfig {
  const rawBaseUrl = env.NEXT_PUBLIC_API_BASE_URL?.trim() || DEFAULT_API_BASE_URL;
  return {
    apiBaseUrl: parseApiBaseUrl(rawBaseUrl).toString().replace(/\/+$/, ""),
    queryStaleTimeMs: parseStaleTimeMs(env.NEXT_PUBLIC_QUERY_STALE_TIME_MS),
    requestTimeoutMs: DEFAULT_REQUEST_TIMEOUT_MS,
  };
}

export const config: AppConfig = loadConfig({
  NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL,
  NEXT_PUBLIC_QUERY_STALE_TIME_MS: process.env.NEXT_PUBLIC_QUERY_STALE_TIME_MS,
});

