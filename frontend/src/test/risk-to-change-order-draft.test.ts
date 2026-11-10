import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";

import {
  changeOrderDraftFromRiskSchema,
  changeOrderSchema,
  projectTimelineItemSchema,
  type ChangeOrderItem,
} from "../lib/contracts.ts";
import { hasPermission, type Role } from "../lib/rbac.ts";
import { reviewsApi } from "../lib/api/resources.ts";

describe("Evidence-Backed Delay Risk to Change Order Draft Conversion", () => {
  beforeEach(() => {
    reviewsApi.clearOverrides();
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
      assert.equal(valid.reason, "Contractor confirmed 14-day delay due to mill stoppage");

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
        description: "Delay event documented in daily report: Granite bedrock encountered.\n\nResponsible party: Groundworks LLC",
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
      assert.equal(parsed.time_impact_days, null, "Schedule field must remain null");
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

  describe("2. Flow: Conversion from Delay Risk into Draft Change Order", () => {
    it("converts evidence-backed delay risk to a draft change order with null financial/schedule fields", async () => {
      const items = await reviewsApi.list({ category: "high_severity_risk" });
      const delayRisk = items[0]!;
      assert.ok(delayRisk, "Must have a delay risk item");
      assert.ok(delayRisk.evidence_links.length > 0, "Delay risk must have linked evidence");

      const conversion = await reviewsApi.createDraftFromRisk(
        delayRisk,
        {
          change_order_reference: "CO-DR-STEEL-01",
          change_order_title: "Mitigation: " + delayRisk.title,
          reason: "Critical delay substantiated by fabricator notice and mill certificate",
        },
        { name: "Commercial Director", role: "commercial_manager" }
      );

      // 1. Initial status is 'drafted'
      assert.equal(conversion.changeOrder.status, "drafted");
      assert.equal(conversion.changeOrder.reference, "CO-DR-STEEL-01");

      // 2. Financial and schedule fields remain null until human enters them
      assert.equal(conversion.changeOrder.amount, null);
      assert.equal(conversion.changeOrder.time_impact_days, null);
      assert.equal(conversion.changeOrder.cost_items, null);

      // 3. Original risk remains linked
      assert.equal(conversion.item.status, "converted");
      assert.equal(conversion.item.change_order_reference, "CO-DR-STEEL-01");

      // 4. Evidence package is linked / cited
      assert.ok(conversion.changeOrder.evidence_links.length > 0);

      // 5. Transition is audited
      const lastAudit = conversion.item.audit_history.at(-1);
      assert.ok(lastAudit);
      assert.equal(lastAudit.action, "risk.converted_to_change_order");
      assert.equal(lastAudit.reason, "Critical delay substantiated by fabricator notice and mill certificate");
    });

    it("rejects draft conversion for insufficient-evidence risks (Constraint: Every draft must cite evidence)", async () => {
      const items = await reviewsApi.list({ category: "insufficient_evidence_risk" });
      const insufficientRisk = items[0]!;
      assert.ok(insufficientRisk);

      await assert.rejects(
        async () => {
          await reviewsApi.createDraftFromRisk(
            insufficientRisk,
            {
              change_order_reference: "CO-FAIL",
              reason: "Attempting conversion without evidence",
            },
            { name: "PM", role: "project_manager" }
          );
        },
        (err: Error) => {
          assert.match(err.message, /Cannot create change-order draft without supporting evidence/);
          return true;
        }
      );
    });

    it("rejects draft conversion when justification reason is empty", async () => {
      const items = await reviewsApi.list({ category: "high_severity_risk" });
      const delayRisk = items[0]!;

      await assert.rejects(
        async () => {
          await reviewsApi.createDraftFromRisk(
            delayRisk,
            {
              change_order_reference: "CO-TEST",
              reason: "   \t\n  ",
            },
            { name: "PM", role: "project_manager" }
          );
        },
        (err: Error) => {
          assert.match(err.message, /reason is mandatory/i);
          return true;
        }
      );
    });
  });

  describe("3. Flow: Editing, Submitting, and Approving the Draft", () => {
    it("allows human user to edit the draft, entering cost items and schedule impact", () => {
      // Human updates the change order draft
      const draftCO: ChangeOrderItem = {
        id: "co-101",
        project_id: "proj-1",
        reference: "CO-DR-001",
        title: "Rock Mitigation",
        description: "Excavation bedrock encountered.",
        status: "drafted",
        amount: null,
        currency: "USD",
        cost_items: null,
        time_impact_days: null,
        draft: { sources: { E1: { text: "Rock formation" } } },
        source_event_id: "ev-1",
        responsible_party: "Excavator Sub",
        evidence_links: ["ev-1"],
        approval_history: [],
      };

      // Human enters cost items ($15,000) and schedule impact (10 days)
      const edited: ChangeOrderItem = {
        ...draftCO,
        amount: "15000.00",
        time_impact_days: 10,
        cost_items: [
          { description: "Rock breaker machinery rental", amount: "10000.00" },
          { description: "Additional excavator operator crew", amount: "5000.00" },
        ],
      };

      const parsed = changeOrderSchema.parse(edited);
      assert.equal(parsed.amount, "15000.00");
      assert.equal(parsed.time_impact_days, 10);
      assert.equal(parsed.status, "drafted");
      assert.ok(parsed.draft?.sources);
    });

    it("submits the draft change order for approval (drafted -> submitted)", () => {
      const draftCO: ChangeOrderItem = {
        id: "co-101",
        project_id: "proj-1",
        reference: "CO-DR-001",
        title: "Rock Mitigation",
        description: "Excavation bedrock encountered.",
        status: "drafted",
        amount: "15000.00",
        currency: "USD",
        cost_items: [{ description: "Rock breaker machinery rental", amount: "15000.00" }],
        time_impact_days: 10,
        draft: { sources: { E1: { text: "Rock formation" } } },
        source_event_id: "ev-1",
        responsible_party: "Excavator Sub",
        evidence_links: ["ev-1"],
        approval_history: [],
      };

      // Submit for approval
      const submitted: ChangeOrderItem = {
        ...draftCO,
        status: "submitted",
        approval_history: [
          {
            status: "submitted",
            reason: "Cost confirmed by commercial manager; ready for formal sign-off",
            decided_by_id: null,
            decided_at: null,
            submitted_at: new Date().toISOString(),
          },
        ],
      };

      const parsed = changeOrderSchema.parse(submitted);
      assert.equal(parsed.status, "submitted");
      assert.equal(parsed.approval_history.length, 1);
      assert.equal(parsed.approval_history[0]!.status, "submitted");
    });

    it("approves or rejects the submitted change order with human decision and mandatory reason", () => {
      const submittedCO: ChangeOrderItem = {
        id: "co-101",
        project_id: "proj-1",
        reference: "CO-DR-001",
        title: "Rock Mitigation",
        description: "Excavation bedrock encountered.",
        status: "submitted",
        amount: "15000.00",
        currency: "USD",
        cost_items: [{ description: "Rock breaker machinery rental", amount: "15000.00" }],
        time_impact_days: 10,
        draft: { sources: { E1: { text: "Rock formation" } } },
        source_event_id: "ev-1",
        responsible_party: "Excavator Sub",
        evidence_links: ["ev-1"],
        approval_history: [
          {
            status: "submitted",
            reason: "Cost confirmed",
            decided_by_id: null,
            decided_at: null,
            submitted_at: new Date().toISOString(),
          },
        ],
      };

      // 1. Approval
      const approved: ChangeOrderItem = {
        ...submittedCO,
        status: "approved",
        approval_history: [
          ...submittedCO.approval_history,
          {
            status: "approved",
            reason: "Verified against site geotechnical borehole log B4",
            decided_by_id: "user-pm-2",
            decided_at: new Date().toISOString(),
            submitted_at: submittedCO.approval_history[0]!.submitted_at,
          },
        ],
      };
      const parsedApproved = changeOrderSchema.parse(approved);
      assert.equal(parsedApproved.status, "approved");
      assert.equal(parsedApproved.approval_history[1]!.reason, "Verified against site geotechnical borehole log B4");

      // 2. Rejection
      const rejected: ChangeOrderItem = {
        ...submittedCO,
        status: "rejected",
        approval_history: [
          ...submittedCO.approval_history,
          {
            status: "rejected",
            reason: "Risk deemed within contractor baseline ground investigation allowance",
            decided_by_id: "user-pm-2",
            decided_at: new Date().toISOString(),
            submitted_at: submittedCO.approval_history[0]!.submitted_at,
          },
        ],
      };
      const parsedRejected = changeOrderSchema.parse(rejected);
      assert.equal(parsedRejected.status, "rejected");
      assert.equal(parsedRejected.approval_history[1]!.reason, "Risk deemed within contractor baseline ground investigation allowance");
    });
  });

  describe("4. Role-Based Access Control (RBAC)", () => {
    it("enforces that only commercial/project manager roles have permission to decide risks", () => {
      const authorizedRoles: Role[] = ["owner", "admin", "project_manager", "commercial_manager"];
      const unauthorizedRoles: Role[] = ["site_engineer", "viewer", "auditor"];

      for (const role of authorizedRoles) {
        assert.ok(hasPermission(role, "risks.accept"), `${role} should have risks.accept permission`);
        assert.ok(hasPermission(role, "change_orders.write"), `${role} should have change_orders.write permission`);
      }

      for (const role of unauthorizedRoles) {
        assert.equal(hasPermission(role, "risks.accept"), false, `${role} must NOT have risks.accept permission`);
      }
    });
  });
});
