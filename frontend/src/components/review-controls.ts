import { createElement as h } from "react";
import {
  actionsFor,
  labels,
  type WorkspaceAction,
  type WorkspaceItem,
} from "../lib/review-workspace.ts";

export function FilterSelect({
  field,
  label,
  value,
  options,
  onChange,
}: {
  field: string;
  label: string;
  value: string;
  options: Record<string, string>;
  onChange: (value: string) => void;
}) {
  return h(
    "label",
    { className: "grid gap-1 text-sm font-medium" },
    label,
    h(
      "select",
      {
        id: "filter-" + field,
        className: "rounded-lg border border-border bg-surface p-2",
        value,
        onChange: (e: React.ChangeEvent<HTMLSelectElement>) =>
          onChange(e.target.value),
      },
      Object.entries(options).map(([v, text]) =>
        h("option", { key: v, value: v }, text),
      ),
    ),
  );
}

export function ReviewActionButtons({
  item,
  canConvert,
  onAction,
}: {
  item: WorkspaceItem;
  canConvert: boolean;
  onAction: (action: WorkspaceAction) => void;
}) {
  return h(
    "div",
    { className: "flex flex-wrap gap-2" },
    actionsFor(item, canConvert).map((action) =>
      h(
        "button",
        {
          type: "button",
          key: action,
          className:
            "rounded-lg border border-border px-3 py-2 text-sm font-medium hover:bg-surface-muted",
          onClick: () => onAction(action),
        },
        item.kind === "extraction" && action === "dismiss"
          ? "Dismiss review item"
          : labels[action],
      ),
    ),
  );
}

export function SourceQuotation({
  source,
}: {
  source: WorkspaceItem["evidence_details"][number];
}) {
  return h(
    "div",
    {},
    h(
      "p",
      { className: "text-ink-muted" },
      source.source_page === null
        ? "Page unavailable"
        : `Page ${source.source_page}`,
    ),
    source.source_text_snippet
      ? h("blockquote", {}, `“${source.source_text_snippet}”`)
      : h("p", {}, "Quotation unavailable"),
  );
}
