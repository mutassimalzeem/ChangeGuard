"use client";

import { useId, type KeyboardEvent } from "react";

import { cn } from "@/lib/utils";

export interface TabItem {
  readonly id: string;
  readonly label: string;
  /** Optional count shown as a badge, e.g. member counts or open items. */
  readonly count?: number;
  readonly disabled?: boolean;
}

/**
 * Accessible tabs component supporting horizontal keyboard navigation.
 */
export function Tabs({
  items,
  value,
  onChange,
  className,
}: {
  items: readonly TabItem[];
  value: string;
  onChange: (id: string) => void;
  className?: string;
}) {
  const idPrefix = useId();

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const enabledItems = items.filter((item) => !item.disabled);
    const currentIndex = enabledItems.findIndex((item) => item.id === value);
    if (currentIndex === -1) return;

    let nextIndex = currentIndex;
    if (event.key === "ArrowRight") {
      nextIndex = (currentIndex + 1) % enabledItems.length;
      event.preventDefault();
    } else if (event.key === "ArrowLeft") {
      nextIndex = (currentIndex - 1 + enabledItems.length) % enabledItems.length;
      event.preventDefault();
    } else if (event.key === "Home") {
      nextIndex = 0;
      event.preventDefault();
    } else if (event.key === "End") {
      nextIndex = enabledItems.length - 1;
      event.preventDefault();
    }

    const nextItem = enabledItems[nextIndex];
    if (nextItem && nextIndex !== currentIndex) {
      onChange(nextItem.id);
      const button = document.getElementById(`${idPrefix}-tab-${nextItem.id}`);
      button?.focus();
    }
  };

  return (
    <div
      role="tablist"
      aria-orientation="horizontal"
      onKeyDown={handleKeyDown}
      className={cn(
        "flex items-center gap-1 border-b border-border overflow-x-auto",
        className,
      )}
    >
      {items.map((tab) => {
        const isSelected = tab.id === value;
        return (
          <button
            key={tab.id}
            id={`${idPrefix}-tab-${tab.id}`}
            role="tab"
            type="button"
            aria-selected={isSelected}
            aria-controls={`${idPrefix}-panel-${tab.id}`}
            tabIndex={isSelected ? 0 : -1}
            disabled={tab.disabled}
            onClick={() => onChange(tab.id)}
            className={cn(
              "group relative inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-40",
              isSelected
                ? "text-brand font-semibold"
                : "text-ink-muted hover:text-ink",
            )}
          >
            <span>{tab.label}</span>
            {tab.count !== undefined ? (
              <span
                className={cn(
                  "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium tabular",
                  isSelected
                    ? "bg-brand-soft text-brand-strong"
                    : "bg-subtle text-ink-muted group-hover:text-ink",
                )}
              >
                {tab.count}
              </span>
            ) : null}
            {isSelected ? (
              <span
                aria-hidden
                className="absolute inset-x-0 bottom-0 h-0.5 bg-brand"
              />
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
