import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { client } from "../lib/api/client.ts";
import { changeOrdersApi } from "../lib/api/resources.ts";

import {
  changeOrderDraftFromRiskSchema,
  changeOrderSchema,
  projectTimelineItemSchema,
} from "../lib/contracts.ts";

describe("Evidence-Backed Delay Risk to Change Order Draft Conversion", () => {
  it("sends human edits, confirmation, and decision reasons in the API's input format", async () => {
    const adapter = client.defaults.adapter;
    const requests: unknown[] = [];
    client.defaults.adapter = async (config) => {
      requests.push([config.method, config.url, JSON.parse(config.data)]);
      return {
        config,
        status: 200,
        statusText: "OK",
        headers: {},
        data: {
          id: "order",
          project_id: "project",
          reference: "CO-1",
          title: "Delivery recovery",
        },
      };
    };
    try {
      const costs = [
        { description: "Expedite delivery", quantity: "1", unit_rate: "125" },
      ];
      await changeOrdersApi.patch("order", {
        cost_items: costs,
        time_impact_days: null,
      });
      await changeOrdersApi.submit("order", true);
      await assert.rejects(changeOrdersApi.approve("order", " "));
      await changeOrdersApi.approve("order", " Verified delivery evidence ");
      await changeOrdersApi.reject("order", "Missing commercial entitlement");
      assert.deepEqual(requests, [
        [
          "patch",
          "/change-orders/order",
          { cost_items: costs, time_impact_days: null },
        ],
        ["post", "/change-orders/order/submit", { cost_confirmed: true }],
        [
          "post",
          "/change-orders/order/approve",
          { reason: "Verified delivery evidence" },
        ],
        [
          "post",
          "/change-orders/order/reject",
          { reason: "Missing commercial entitlement" },
        ],
      ]);
    } finally {
      client.defaults.adapter = adapter;
    }
  });

  describe("1. Schema & Contract Validation", () => {
    it("validates changeOrderDraftFromRiskSchema with optional ref/title and reason", () => {
      const valid = changeOrderDraftFromRiskSchema.parse({
        reference: "CO-DR-001",
        title: "Delay Mitigation: Steel Delivery",
        reason: "Contractor confirmed 14-day delay due to mill stoppage",
      });
      assert.equal(valid.reference, "CO-DR-001");
      assert.equal(valid.title, "Delay Mitigation: Steel Delivery");
      assert.equal(
        valid.reason,
        "Contractor confirmed 14-day delay due to mill stoppage",
      );

      // Empty input is valid (defaults applied on backend)
      const empty = changeOrderDraftFromRiskSchema.parse({});
      assert.equal(empty.reference, undefined);
    });

    it("verifies changeOrderSchema supports drafted status with null financials and schedule", () => {
      const draftCO = {
        id: "co-test-123",
        project_id: "proj-1",
        reference: "CO-DR-A1B2C3D4",
        title: "Delay Mitigation: Foundation Obstruction",
        description:
          "Delay event documented in daily report: Granite bedrock encountered.\n\nResponsible party: Groundworks LLC",
        status: "drafted",
        amount: null,
        currency: "USD",
        cost_items: null,
        time_impact_days: null,
        draft: {
          sources: {
            E1: {
              evidence_link_id: "link-1",
              text: "Granite bedrock encountered at grid B4",
            },
          },
        },
        source_event_id: "event-001",
        responsible_party: "Groundworks LLC",
        evidence_links: ["link-1"],
        approval_history: [],
      };

      const parsed = changeOrderSchema.parse(draftCO);
      assert.equal(parsed.status, "drafted");
      assert.equal(parsed.amount, null, "Financial field must remain null");
      assert.equal(
        parsed.time_impact_days,
        null,
        "Schedule field must remain null",
      );
      assert.equal(parsed.responsible_party, "Groundworks LLC");
      assert.ok(parsed.draft?.sources);
    });

    it("verifies projectTimelineItemSchema supports change_order_id and responsible_party", () => {
      const item = {
        id: "12345678-1234-4234-8234-123456789012",
        kind: "risk" as const,
        occurred_at: "2026-11-10T00:00:00Z",
        title: "Subsurface Rock Delay Risk",
        description: "Hard rock formation delaying pile driving",
        event_type: "delay_risk",
        status: "converted",
        confidence: 0.95,
        severity: "high",
        evidence_status: "supported" as const,
        evidence: [
          {
            evidence_link_id: "12345678-1234-4234-8234-123456789013",
            source_type: "document",
            source_id: "12345678-1234-4234-8234-123456789014",
            source_page: 3,
            source_text_snippet: "Piling rig encountered bedrock",
          },
        ],
        change_order_id: "co-dr-001",
        responsible_party: "Deep Foundations Corp",
        risk_type: "geotechnical_delay",
      };

      const parsed = projectTimelineItemSchema.parse(item);
      assert.equal(parsed.change_order_id, "co-dr-001");
      assert.equal(parsed.responsible_party, "Deep Foundations Corp");
      assert.equal(parsed.status, "converted");
    });
  });
});
