"use client";

/**
 * Authentication context and session manager.
 *
 * Tokens live in memory with tab-scoped sync (see `api/client.ts`).
 * During initial hydration, any active token is validated and decoded
 * so user does not experience a reload bounce.
 */
import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { authApi } from "@/lib/api/resources";
import { decodeSession, isExpired, type Session } from "@/lib/api/session";
import { tokenStore } from "@/lib/api/client";
import { isApiError } from "@/lib/api/errors";

export type AuthStatus = "loading" | "authenticated" | "anonymous";

export interface AuthResult {
  readonly ok: boolean;
  readonly message?: string;
}

export interface AuthContextValue {
  readonly status: AuthStatus;
  readonly session: Session | null;
  readonly signIn: (input: { tenant_slug: string; email: string; password: string }) => Promise<AuthResult>;
  readonly signOut: () => Promise<void>;
  readonly clearSession: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");
  const mounted = useRef(true);

  const clearSession = useCallback(() => {
    tokenStore.clear();
    setSession(null);
    setStatus("anonymous");
  }, []);

  // Listen for refresh failures or logout calls that clear tokenStore
  useEffect(() => {
    mounted.current = true;
    return tokenStore.subscribe(() => {
      if (mounted.current) {
        setSession(null);
        setStatus("anonymous");
      }
    });
  }, []);

  useEffect(
    () => () => {
      mounted.current = false;
    },
    [],
  );

  // Restore stored session if present on mount
  useEffect(() => {
    const existing = tokenStore.getAccessToken();
    if (existing) {
      const decoded = decodeSession(existing);
      if (decoded && !isExpired(decoded)) {
        setSession(decoded);
        setStatus("authenticated");
        return;
      }
    }
    setStatus("anonymous");
  }, []);

  const signIn = useCallback<AuthContextValue["signIn"]>(
    async (input) => {
      try {
        const pair = await authApi.login(input);
        tokenStore.setTokens({ accessToken: pair.access_token, refreshToken: pair.refresh_token });
        const next = decodeSession(pair.access_token);
        if (next === null) {
          tokenStore.clear();
          return { ok: false, message: "The server issued a token this app cannot read. Contact support." };
        }
        setSession(next);
        setStatus("authenticated");
        return { ok: true };
      } catch (error) {
        if (isApiError(error) && error.status === 429) {
          return { ok: false, message: "Too many attempts. Wait a few minutes before trying again." };
        }
        if (isApiError(error)) {
          return {
            ok: false,
            message:
              error.status === 401
                ? "That email, password or workspace does not match an account."
                : error.message,
          };
        }
        return { ok: false, message: "Sign-in failed. Check your connection and try again." };
      }
    },
    [],
  );

  const signOut = useCallback(async () => {
    const refreshToken = tokenStore.getRefreshToken();
    if (refreshToken) {
      await authApi.logout(refreshToken).catch(() => undefined);
    }
    tokenStore.clear();
    setSession(null);
    setStatus("anonymous");
    router.replace("/login");
  }, [router]);

  const value = useMemo<AuthContextValue>(
    () => ({ status, session, signIn, signOut, clearSession }),
    [status, session, signIn, signOut, clearSession],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error("useAuth must be used inside <AuthProvider>.");
  }
  return context;
}

/** The primary role this UI is showing, or null when signed out. */
export function useRole() {
  const { session } = useAuth();
  return session?.roles[0] ?? null;
}
