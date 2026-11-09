import assert from "node:assert/strict";
import { test } from "node:test";
import { pilotDocumentSchema, readinessSchema } from "../lib/api/pilot.ts";

test("pilot progress rejects invalid versions and missing extraction visibility", () => {
  assert.equal(
    pilotDocumentSchema.safeParse({ document_id: "bad", status: "queued" })
      .success,
    false,
  );
});

test("readiness preserves unknown accuracy and separate currency amounts", () => {
  const report = readinessSchema.parse({
    project_name: "Pilot",
    generated_at: "2026-11-09",
    documents_total: 0,
    documents_processed: 0,
    classification_reviewed: 0,
    classification_accuracy: null,
    extraction_confidence: null,
    risks_detected: 0,
    missing_evidence: ["contract"],
    overdue_approvals: 0,
    pending_exposure: { USD: "12.30", BDT: "900" },
    unknown_exposure_count: 1,
    notes: "Human review required",
  });
  assert.equal(report.classification_accuracy, null);
  assert.deepEqual(report.pending_exposure, { USD: "12.30", BDT: "900" });
});
