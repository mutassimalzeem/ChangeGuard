"use client";

/**
 * A single QueryClient for the tab, created lazily.
 *
 * `useState` rather than a module-level constant: a module constant is shared
 * by every request during SSR, so one visitor's cached data could leak into
 * another's render. The retry policy also refuses to retry auth/permission
 * failures, which retrying can never fix.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { config } from "@/lib/config";
import { ApiError } from "@/lib/api/errors";

function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: config.queryStaleTimeMs,
        gcTime: 5 * 60 * 1000,
        refetchOnWindowFocus: false,
        retry: (failureCount, error) => {
          if (error instanceof ApiError) {
            // 4xx answers will not change on a retry; only transient faults might.
            if (error.status !== null && error.status >= 400 && error.status < 500) return false;
            if (!error.isTransient) return false;
          }
          return failureCount < 2;
        },
      },
      mutations: { retry: false },
    },
  });
}

export function QueryProvider({ children }: { children: ReactNode }) {
  const [queryClient] = useState(createQueryClient);
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
