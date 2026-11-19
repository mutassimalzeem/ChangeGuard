import assert from "node:assert/strict";
import { it } from "node:test";
import { createElement as h } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import {
  FilterSelect,
  ReviewActionButtons,
  SourceQuotation,
} from "../components/review-controls.ts";
import { states, type WorkspaceItem } from "../lib/review-workspace.ts";

const risk: WorkspaceItem = {
  id: "23ba97b8-eefd-43a1-9dfb-d598fd739ed1",
  kind: "risk",
  categories: ["high_severity_risk"],
  title: "Delay",
  risk_type: "delay",
  description: null,
  confidence: null,
  severity: "high",
  document_id: null,
  evidence_details: [],
  evidence_supported: true,
  recommended_action: null,
  status: "open",
  reviewable: true,
  change_order_id: null,
  created_at: "2026-01-01",
  owner_id: null,
  deadline: null,
  review_state: "review_required",
  history: [],
  can_decide: false,
  amount: null,
  currency: null,
};
it("renders labelled state filters with the active filter selected", () => {
  const html = render(
    h(FilterSelect, {
      field: "status",
      label: "Review state",
      value: "dismissed",
      options: states,
      onChange() {},
    }),
  );
  assert.match(html, /<label[^>]*>Review state<select/);
  assert.match(html, /value="dismissed" selected="">Dismissed/);
});
it("discloses only supplied source text and records unavailable pages", () => {
  const source = {
    id: risk.id,
    source_type: "document",
    document_id: null,
    document_name: null,
    source_page: 2,
    source_text_snippet: "Delay <confirmed>",
  };
  const html = render(h(SourceQuotation, { source }));
  assert.match(html, /Page 2/);
  assert.match(html, /Delay &lt;confirmed&gt;/);
  assert.match(
    render(
      h(SourceQuotation, {
        source: { ...source, source_page: null, source_text_snippet: null },
      }),
    ),
    /Page unavailable.*Quotation unavailable/,
  );
});
it("renders only permitted actions for supported, unsupported, closed and approval items", () => {
  const buttons = (item: WorkspaceItem, canConvert = false) =>
    render(h(ReviewActionButtons, { item, canConvert, onAction() {} }));
  assert.doesNotMatch(buttons(risk), /Create change-order draft/);
  assert.match(buttons(risk, true), /Create change-order draft/);
  assert.doesNotMatch(
    buttons({ ...risk, evidence_supported: false }, true),
    /Accept risk|Create change-order draft|Override severity/,
  );
  assert.doesNotMatch(buttons({ ...risk, reviewable: false }), /<button/);
  assert.doesNotMatch(
    buttons({ ...risk, kind: "approval" }),
    /Approve change order/,
  );
  assert.match(
    buttons({ ...risk, kind: "approval", can_decide: true }),
    /Approve change order/,
  );
});
