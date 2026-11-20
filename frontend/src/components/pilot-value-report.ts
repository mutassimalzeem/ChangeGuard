import { createElement as h } from "react";

export function PilotValueReport({
  rows,
  exporting,
  onExport,
}: {
  rows: { label: string; value: string }[];
  exporting: boolean;
  onExport: (format: "pdf" | "csv") => void;
}) {
  return h(
    "div",
    null,
    h(
      "div",
      { className: "my-3 flex gap-4" },
      ...(["csv", "pdf"] as const).map((format) =>
        h(
          "button",
          {
            key: format,
            type: "button",
            className: "text-brand underline",
            disabled: exporting,
            onClick: () => onExport(format),
          },
          "Export " + format.toUpperCase(),
        ),
      ),
    ),
    h(
      "table",
      { className: "w-full text-left text-sm" },
      h("caption", { className: "sr-only" }, "Measured project outcomes"),
      h(
        "thead",
        null,
        h("tr", null, h("th", null, "Measure"), h("th", null, "Observation")),
      ),
      h(
        "tbody",
        null,
        ...rows.map((row, i) =>
          h(
            "tr",
            { key: i, className: "border-t border-border align-top" },
            h(
              "th",
              { scope: "row", className: "py-2 pr-4 font-medium" },
              row.label,
            ),
            h("td", { className: "py-2" }, row.value),
          ),
        ),
      ),
    ),
  );
}

export function PilotFileStatus({
  doc,
}: {
  doc: {
    status: string;
    processing_status?: string;
    document_type: string | null;
    reviewed: boolean;
  };
}) {
  const status = (doc.processing_status || doc.status).replaceAll("_", " ");
  return h(
    "span",
    null,
    [
      status,
      doc.document_type || "Awaiting classification",
      doc.reviewed && "Reviewed",
    ]
      .filter(Boolean)
      .join(" · "),
  );
}

export function PilotImportResults({
  items,
}: {
  items: { file_name: string; status: number; error?: string }[];
}) {
  return h(
    "ul",
    { className: "mt-3", "aria-label": "ZIP import results" },
    items.map((item, index) =>
      h(
        "li",
        { key: index },
        item.file_name,
        " · ",
        item.status === 201
          ? "Queued"
          : item.status === 409
            ? "Duplicate — skipped"
            : item.error || "Quarantined",
      ),
    ),
  );
}
