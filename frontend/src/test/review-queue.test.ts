import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { client } from "../lib/api/client.ts";
import {
  availableReviewActions,
  REVIEW_CATEGORIES,
  reviewDecisionSchema,
  reviewQueueApi,
  reviewQueueSchema,
} from "../lib/review-queue.ts";

const projectId = "11111111-1111-4111-8111-111111111111";
const risk = reviewQueueSchema.element.parse({
  id: "22222222-2222-4222-8222-222222222222",
  kind: "risk",
  categories: ["conflicting_evidence", "high_severity_risk"],
  title: "Steel delivery date conflict",
  risk_type: "conflicting_information",
  description: null,
  confidence: 0.86,
  severity: "high",
  document_id: "33333333-3333-4333-8333-333333333333",
  evidence_details: [
    {
      id: "44444444-4444-4444-8444-444444444444",
      source_type: "document",
      document_id: "33333333-3333-4333-8333-333333333333",
      document_name: "Delivery notice.pdf",
      source_page: 4,
      source_text_snippet: "Steel will arrive on Thursday.",
    },
  ],
  evidence_supported: true,
  status: "open",
  recommended_action: "Confirm delivery with the issuer.",
  reviewable: true,
  change_order_id: null,
});

describe("Review queue", () => {
  it("reads persisted findings and supports all six categories with explicit missing provenance", async () => {
    const originalAdapter = client.defaults.adapter;
    const item = {
      ...risk,
      categories: Object.keys(REVIEW_CATEGORIES),
      confidence: null,
    };
    client.defaults.adapter = async (config) => {
      assert.equal(config.url, `/projects/${projectId}/review-queue`);
      return {
        config,
        data: [item],
        headers: {},
        status: 200,
        statusText: "OK",
      };
    };
    try {
      assert.deepEqual(await reviewQueueApi.list(projectId), [item]);
    } finally {
      client.defaults.adapter = originalAdapter;
    }
  });

  it("offers risk actions only when supported and respects conversion permission", () => {
    assert.deepEqual(availableReviewActions(risk, true), [
      "accept",
      "dismiss",
      "request_evidence",
      "convert_to_change_order",
      "override",
    ]);
    assert.ok(
      !availableReviewActions(risk, false).includes("convert_to_change_order"),
    );
    assert.deepEqual(
      availableReviewActions(
        { ...risk, evidence_supported: false, status: "evidence_requested" },
        true,
      ),
      ["dismiss", "request_evidence"],
    );
    assert.deepEqual(
      availableReviewActions({ ...risk, kind: "extraction" }, true),
      ["dismiss", "request_evidence"],
    );
    assert.deepEqual(
      availableReviewActions({ ...risk, reviewable: false }, true),
      [],
    );
  });

  it("rejects blank dismissal and override reasons and requires an override severity", () => {
    assert.equal(
      reviewDecisionSchema.safeParse({ action: "dismiss", reason: "  " })
        .success,
      false,
    );
    assert.equal(
      reviewDecisionSchema.safeParse({
        action: "override",
        reason: "  ",
        severity: "critical",
      }).success,
      false,
    );
    assert.equal(
      reviewDecisionSchema.safeParse({
        action: "override",
        reason: "Verified escalation",
      }).success,
      false,
    );
  });

  it("accepts a successful decision response when the risk has no description", async () => {
    const originalAdapter = client.defaults.adapter;
    client.defaults.adapter = async (config) => ({
      config,
      data: { ...risk, status: "accepted" },
      headers: {},
      status: 200,
      statusText: "OK",
    });
    try {
      assert.equal(
        await reviewQueueApi.decide(
          projectId,
          risk,
          { action: "accept", reason: "Source confirmed" },
          true,
        ),
        null,
      );
    } finally {
      client.defaults.adapter = originalAdapter;
    }
  });

  it("uses project-scoped decision endpoints and propagates server failures", async () => {
    const originalAdapter = client.defaults.adapter;
    const routes = [
      `/projects/${projectId}/risks/${risk.id}/decisions`,
      `/projects/${projectId}/review-queue/extractions/${risk.id}/decisions`,
      `/projects/${projectId}/risks/${risk.id}/change-order-draft`,
    ];
    const serverError = new Error("Review rejected by the server");
    client.defaults.adapter = async (config) => {
      assert.equal(config.method, "post");
      assert.equal(config.url, routes.shift());
      assert.equal(JSON.parse(config.data).reason, "Verified source records");
      throw serverError;
    };
    try {
      for (const [item, action] of [
        [risk, "accept"],
        [{ ...risk, kind: "extraction" }, "dismiss"],
        [risk, "convert_to_change_order"],
      ] as const) {
        await assert.rejects(
          reviewQueueApi.decide(
            projectId,
            item,
            { action, reason: " Verified source records " },
            true,
          ),
          /Review rejected by the server/,
        );
      }
      assert.deepEqual(routes, []);
    } finally {
      client.defaults.adapter = originalAdapter;
    }
  });
});
