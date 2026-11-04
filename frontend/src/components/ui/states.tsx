import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** A single shimmering placeholder bar. */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-pulse rounded-md bg-subtle", className)} />;
}

/**
 * Loading placeholder for a page. It mirrors the card/table shape of what is
 * coming, so the layout does not jump when data arrives, and announces itself
 * once instead of leaving screen readers silent.
 */
export function LoadingSkeleton({ rows = 4, variant = "table" }: { rows?: number; variant?: "table" | "cards" }) {
  return (
    <div role="status" aria-live="polite" aria-label="Loading" className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <Skeleton className="h-7 w-56" />
        <Skeleton className="h-4 w-80" />
      </div>
      {variant === "cards" ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: rows }, (_, index) => (
            <div key={index} className="rounded-[--radius-card] border border-border bg-surface p-5 shadow-card">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="mt-3 h-5 w-40" />
              <Skeleton className="mt-2 h-4 w-32" />
            </div>
          ))}
        </div>
      ) : (
        <div className="overflow-hidden rounded-[--radius-card] border border-border bg-surface">
          <div className="border-b border-border bg-subtle px-5 py-3">
            <Skeleton className="h-4 w-full" />
          </div>
          {Array.from({ length: rows }, (_, index) => (
            <div key={index} className="border-b border-border px-5 py-4 last:border-b-0">
              <Skeleton className="h-4 w-full" />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** Deliberately empty, with the next sensible action offered. */
export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-[--radius-card] border border-dashed border-border-strong bg-surface px-6 py-12 text-center">
      <p className="text-sm font-semibold text-ink">{title}</p>
      {description ? <p className="max-w-md text-sm text-ink-muted">{description}</p> : null}
      {action ? <div className="mt-2">{action}</div> : null}
    </div>
  );
}

/**
 * A failed load (or an action that failed). The message is shown as-is: the API
 * client has already turned the response into a sentence a contractor can act
 * on, so no raw status code or stack trace surfaces here.
 */
export function ErrorState({
  title = "Something went wrong",
  message,
  detail,
  onRetry,
}: {
  title?: string;
  message: string;
  detail?: ReactNode;
  onRetry?: () => void;
}) {
  return (
    <div role="alert" className="flex flex-col items-start gap-2 rounded-[--radius-card] border border-danger/30 bg-danger-soft px-5 py-4">
      <p className="text-sm font-semibold text-danger">{title}</p>
      <p className="text-sm text-ink">{message}</p>
      {detail ? <div className="text-xs text-ink-muted">{detail}</div> : null}
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-1 rounded-lg border border-danger/40 bg-surface px-3 py-1.5 text-xs font-medium text-danger hover:bg-danger-soft"
        >
          Try again
        </button>
      ) : null}
    </div>
  );
}
