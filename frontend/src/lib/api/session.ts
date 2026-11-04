/**
 * Reads the claims the UI needs out of an access token.
 *
 * The token is decoded, never verified: the signature is checked by the API on
 * every request, which is the only place it matters. Using the payload here
 * just avoids an extra round-trip to learn the role, and `ver`/`exp` let the
 * client notice a stale or expired session before a request fails. A forged
 * payload therefore buys nothing: it cannot make the API accept a call.
 */
import { z } from "zod";

import { isRole, type Role } from "@/lib/rbac";

/** `core/security.py::create_access_token` payload. */
const claimsSchema = z.object({
  sub: z.string().min(1),
  tenant_id: z.string().min(1).optional(),
  roles: z.array(z.string()).default([]),
  /** Token purpose; access tokens carry `access`. */
  type: z.string().optional(),
  ver: z.number().int().optional(),
  exp: z.number().int().optional(),
});

export interface Session {
  readonly userId: string;
  readonly tenantId: string | null;
  /** Roles the UI recognises; a server role this build does not know is dropped. */
  readonly roles: readonly Role[];
  /** Milliseconds since the epoch, or null when the token carries no `exp`. */
  readonly expiresAt: number | null;
}

/** Decodes a base64url segment without relying on `atob` padding quirks. */
function decodeSegment(segment: string): string {
  const normalised = segment.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalised.padEnd(normalised.length + ((4 - (normalised.length % 4)) % 4), "=");
  const binary = atob(padded);
  const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

/** Returns null for anything that is not a readable access token. */
export function decodeSession(token: string | null | undefined): Session | null {
  if (typeof token !== "string" || token.length === 0) {
    return null;
  }
  const parts = token.split(".");
  const payload = parts[1];
  if (payload === undefined || payload.length === 0) {
    return null;
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(decodeSegment(payload));
  } catch {
    return null;
  }

  const result = claimsSchema.safeParse(parsed);
  if (!result.success) {
    return null;
  }
  const claims = result.data;

  return {
    userId: claims.sub,
    tenantId: claims.tenant_id ?? null,
    roles: claims.roles.filter(isRole),
    expiresAt: typeof claims.exp === "number" ? claims.exp * 1000 : null,
  };
}

/** True when `expiresAt` is missing or already inside `skewMs` of the present. */
export function isExpired(session: Session | null, skewMs = 30_000, now = Date.now()): boolean {
  if (session === null || session.expiresAt === null) return false;
  return session.expiresAt - skewMs <= now;
}

export function primaryRole(session: Session | null): Role | null {
  return session?.roles[0] ?? null;
}
