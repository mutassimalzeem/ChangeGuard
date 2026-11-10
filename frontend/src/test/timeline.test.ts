import assert from "node:assert/strict";
import test from "node:test";
import { projectTimelineSchema } from "../lib/contracts.ts";

const id = "12345678-1234-4234-8234-123456789012";
const page = {
  offset: 0, limit: 50, has_more: false,
  items: [{ id, kind: "risk", occurred_at: "2026-11-10T00:00:00Z",
    title: "Unlinked report delay", description: "Delay recorded.",
    event_type: "daily_report_delay_without_link", status: "open", confidence: "0.95",
    severity: "medium", evidence_status: "supported",
    evidence: [{ evidence_link_id: id, source_type: "document", source_id: id,
      source_page: 2, source_text_snippet: "Work was delayed." }],
  }],
};

test("timeline preserves source quotations, pages and numeric confidence", () => {
  const result = projectTimelineSchema.parse(page);
  const item = result.items[0];
  assert.ok(item);
  const source = item.evidence[0];
  assert.ok(source);
  assert.equal(item.confidence, 0.95);
  assert.equal(source.source_page, 2);
  assert.equal(source.source_text_snippet, "Work was delayed.");
});

test("timeline accepts insufficient evidence without invented quotations", () => {
  const input = structuredClone(page);
  const item = input.items[0];
  assert.ok(item);
  item.status = "insufficient_evidence";
  item.evidence_status = "insufficient_evidence";
  item.evidence = [];
  assert.deepEqual(projectTimelineSchema.parse(input).items.at(0)?.evidence, []);
});

test("timeline rejects missing evidence contract and invalid pages", () => {
  assert.equal(projectTimelineSchema.safeParse({ ...page, items: [{}] }).success, false);
  const input = structuredClone(page);
  const source = input.items.at(0)?.evidence.at(0);
  assert.ok(source);
  source.source_page = 0;
  assert.equal(projectTimelineSchema.safeParse(input).success, false);
});
