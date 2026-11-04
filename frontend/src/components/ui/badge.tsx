import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export const BADGE_TONES = ["neutral", "brand", "success", "warning", "danger", "info"] as const;

export type BadgeTone = (typeof BADGE_TONES)[number];

const tones: Record<BadgeTone, string> = {
  neutral: "bg-subtle text-ink-muted",
  brand: "bg-brand-soft text-brand-strong",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger",
  info: "bg-info-soft text-info",
};

export function Badge({
  tone = "neutral",
  children,
  className,
}: {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium whitespace-nowrap",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
