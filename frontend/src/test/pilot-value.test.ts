import assert from "node:assert/strict";
import { test } from "node:test";
import { createElement as h } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import {
  PilotValueReport,
  PilotFileStatus,
  PilotImportResults,
} from "../components/pilot-value-report.ts";

test("pilot displays each import outcome and the latest processing stage", () => {
  const html = render(
    h(PilotImportResults, {
      items: [
        { file_name: "log.pdf", status: 201 },
        { file_name: "copy.pdf", status: 409 },
        { file_name: "bad.pdf", status: 422 },
      ],
    }),
  );
  for (const label of ["log.pdf", "Queued", "Duplicate", "Quarantined"])
    assert.ok(html.includes(label));
  assert.match(
    render(
      h(PilotFileStatus, {
        doc: {
          status: "queued",
          processing_status: "retry_pending",
          document_type: null,
          reviewed: false,
        },
      }),
    ),
    /retry pending/,
  );
});
test("pilot measurements preserve unknown results and provide both export formats", () => {
  const html = render(
    h(PilotValueReport, {
      rows: [{ label: "Classification accuracy", value: "Unmeasured (0/0)" }],
      exporting: true,
      onExport() {},
    }),
  );
  for (const text of [
    "Unmeasured (0/0)",
    "Classification accuracy",
    "Export PDF",
    "Export CSV",
    "disabled",
  ])
    assert.ok(html.includes(text));
});
