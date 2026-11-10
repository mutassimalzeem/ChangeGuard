import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";

import {
  REVIEW_CATEGORIES,
  REVIEW_CATEGORY_META,
  reviewItemSchema,
  riskDismissDecisionSchema,
  riskRequestEvidenceSchema,
  riskConvertChangeOrderSchema,
  type ReviewCategory,
} from "../lib/contracts.ts";
import { hasPermission, type Permission, type Role } from "../lib/rbac.ts";
import { reviewsApi } from "../lib/api/resources.ts";

describe("Review Queue & Approvals", () => {
  beforeEach(() => {
    reviewsApi.clearOverrides();
  });

  describe("1. Category Coverage (All Core Categories)", () => {
    it("defines all review queue categories including the 6 core required categories", () => {
      const requiredCategories: ReviewCategory[] = [
        "insufficient_evidence_risk",
        "low_confidence_extraction",
        "missing_required_field",
        "potential_duplicate",
        "conflicting_evidence",
        "high_severity_risk",
      ];

      assert.ok(REVIEW_CATEGORIES.length >= 6);
      for (const cat of requiredCategories) {
        assert.ok(REVIEW_CATEGORIES.includes(cat), `Missing expected category: ${cat}`);
        const meta = REVIEW_CATEGORY_META[cat];
        assert.ok(meta, `Missing metadata for ${cat}`);
        assert.ok(meta.label.length > 0, `Missing label for ${cat}`);
        assert.ok(meta.description.length > 0, `Missing description for ${cat}`);
        assert.ok(meta.defaultPermission.length > 0, `Missing default permission for ${cat}`);
      }
    });
  });

  describe("2. Review Item Display Fields & Validation", () => {
    it("loads items satisfying full schema and displaying all 8 mandatory fields", async () => {
      const items = await reviewsApi.list();
      assert.ok(items.length >= 6, "Should supply baseline items covering the core categories");

      // Verify that every core category is represented in baseline
      const representedCategories = new Set(items.map((i) => i.category));
      const coreCategories: ReviewCategory[] = [
        "insufficient_evidence_risk",
        "low_confidence_extraction",
        "missing_required_field",
        "potential_duplicate",
        "conflicting_evidence",
        "high_severity_risk",
      ];

      for (const cat of coreCategories) {
        assert.ok(
          representedCategories.has(cat),
          `Core category ${cat} must be represented in review queue items`
        );
      }

      for (const item of items) {
        // Validate against Zod schema
        const parsed = reviewItemSchema.safeParse(item);
        assert.ok(parsed.success, `Item ${item.id} failed schema validation: ${JSON.stringify(parsed)}`);

        // Check the 8 mandatory fields per requirements:
        // 1. title
        assert.ok(item.title && item.title.trim().length > 0, "Item must display title");
        // 2. risk type
        assert.ok(item.risk_type && item.risk_type.trim().length > 0, "Item must display risk type");
        // 3. confidence
        assert.ok(typeof item.confidence === "number" && item.confidence >= 0 && item.confidence <= 1, "Item must display confidence score");
        // 4. evidence links
        assert.ok(Array.isArray(item.evidence_links), "Item must have evidence links array");
        // 5. source quotation and page (checked on items with evidence)
        if (item.evidence_links.length > 0) {
          for (const ev of item.evidence_links) {
            assert.ok(ev.document_name, "Evidence link must have document name");
            assert.ok(ev.excerpt || ev.source_quotation, "Evidence link must have source quotation");
            assert.ok(ev.page_number !== undefined || ev.source_page !== undefined, "Evidence link must have page");
          }
        }
        // 6. link to original document
        assert.ok(item.original_document_url || item.document_id, "Item must provide link to original document");
        // 7. recommended action
        const action = item.recommended_action || item.recommended_correction;
        assert.ok(action && action.trim().length > 0, "Item must display recommended action");
        // 8. current status
        assert.ok(item.status && item.status.length > 0, "Item must display current status");

        // System found & why review needed
        assert.ok(item.system_found && item.system_found.length > 10, "Must specify what the system found");
        assert.ok(item.why_review_needed && item.why_review_needed.length > 10, "Must specify why review is needed");
        assert.ok(Array.isArray(item.audit_history), "Must have audit history array");
      }
    });

    it("filters items by category correctly", async () => {
      const cat: ReviewCategory = "conflicting_evidence";
      const filtered = await reviewsApi.list({ category: cat });
      assert.ok(filtered.length > 0, "Should return items for conflicting_evidence");
      for (const item of filtered) {
        assert.equal(item.category, cat);
      }
    });

    it("verifies insufficient-evidence item structure", async () => {
      const filtered = await reviewsApi.list({ category: "insufficient_evidence_risk" });
      assert.ok(filtered.length > 0, "Should find insufficient-evidence risk item");
      const item = filtered[0]!;
      assert.equal(item.category, "insufficient_evidence_risk");
      assert.equal(item.status, "insufficient_evidence");
      assert.equal(item.evidence_links.length, 0);
      assert.ok(item.confidence! < 0.5, "Insufficient-evidence risk should have low confidence");
    });
  });

  describe("3. Constraint: Insufficient-evidence risks CANNOT be accepted as supported evidence", () => {
    it("strictly blocks accepting insufficient-evidence risk via reviewsApi.acceptRisk", async () => {
      const items = await reviewsApi.list({ category: "insufficient_evidence_risk" });
      const item = items[0]!;
      assert.ok(item, "Must have an insufficient evidence risk item");

      await assert.rejects(
        async () => {
          await reviewsApi.acceptRisk(item, "Attempt to accept unsupported risk");
        },
        {
          message: "Insufficient-evidence risks cannot be accepted as supported evidence.",
        }
      );
    });

    it("strictly blocks accepting insufficient-evidence risk via reviewsApi.approve", async () => {
      const items = await reviewsApi.list({ category: "insufficient_evidence_risk" });
      const item = items[0]!;

      await assert.rejects(
        async () => {
          await reviewsApi.approve(item, "Attempt to approve unsupported risk");
        },
        {
          message: "Insufficient-evidence risks cannot be accepted as supported evidence.",
        }
      );
    });

    it("allows accepting risks that have supported evidence", async () => {
      const items = await reviewsApi.list({ category: "high_severity_risk" });
      const supportedItem = items[0]!;
      assert.ok(supportedItem.evidence_links.length > 0, "High-severity risk should have supported evidence");

      const accepted = await reviewsApi.acceptRisk(supportedItem, "Accepted with valid mill notice evidence", {
        name: "Commercial Lead",
        role: "commercial_manager",
      });

      assert.equal(accepted.status, "accepted");
      const latestAudit = accepted.audit_history[accepted.audit_history.length - 1]!;
      assert.equal(latestAudit.action, "risk.accepted");
      assert.equal(latestAudit.actor_name, "Commercial Lead");
      assert.equal(latestAudit.reason, "Accepted with valid mill notice evidence");
    });
  });

  describe("4. Dismissal & Override Mandatory Reason Enforcement", () => {
    it("rejects dismissal schema when reason is empty or whitespace", () => {
      const emptyResult = riskDismissDecisionSchema.safeParse({ reason: "" });
      assert.equal(emptyResult.success, false, "Schema must reject empty dismissal reason");

      const whitespaceResult = riskDismissDecisionSchema.safeParse({ reason: "   " });
      assert.equal(whitespaceResult.success, false, "Schema must reject whitespace dismissal reason");
    });

    it("requires reason when calling reviewsApi.dismissRisk", async () => {
      const items = await reviewsApi.list();
      const item = items[0]!;

      await assert.rejects(
        async () => {
          await reviewsApi.dismissRisk(item, "");
        },
        {
          message: "A justification reason is required for dismissal",
        }
      );

      await assert.rejects(
        async () => {
          await reviewsApi.dismissRisk(item, "   ");
        },
        {
          message: "A justification reason is required for dismissal",
        }
      );
    });

    it("successfully dismisses an item when a valid reason is provided, appending audit event", async () => {
      const items = await reviewsApi.list();
      const item = items[0]!;

      const reason = "Risk dismissed: duplicate notification superseded by RFQ-089";
      const dismissed = await reviewsApi.dismissRisk(item, reason, {
        name: "Auditor Lead",
        role: "commercial_manager",
      });

      assert.equal(dismissed.status, "dismissed");
      const latestAudit = dismissed.audit_history[dismissed.audit_history.length - 1]!;
      assert.equal(latestAudit.action, "risk.dismissed");
      assert.equal(latestAudit.reason, reason);
      assert.equal(latestAudit.actor_name, "Auditor Lead");
    });

    it("requires reason when calling reviewsApi.override", async () => {
      const items = await reviewsApi.list();
      const item = items[0]!;

      await assert.rejects(
        async () => {
          await reviewsApi.override(item, {
            reason: "",
            severity: "critical",
          });
        },
        {
          message: "A justification reason is required for override",
        }
      );
    });
  });

  describe("5. Request More Evidence Workflow", () => {
    it("validates request evidence schema requiring non-empty reason", () => {
      const invalid = riskRequestEvidenceSchema.safeParse({ reason: "" });
      assert.equal(invalid.success, false);

      const valid = riskRequestEvidenceSchema.safeParse({
        reason: "Requesting certified laboratory assays for hydrocarbon presence",
      });
      assert.equal(valid.success, true);
    });

    it("requires reason when calling reviewsApi.requestEvidence", async () => {
      const items = await reviewsApi.list({ category: "insufficient_evidence_risk" });
      const item = items[0]!;

      await assert.rejects(
        async () => {
          await reviewsApi.requestEvidence(item, { reason: "   " });
        },
        {
          message: "A justification reason is required to request more evidence",
        }
      );
    });

    it("successfully updates item status to evidence_requested and audits", async () => {
      const items = await reviewsApi.list({ category: "insufficient_evidence_risk" });
      const item = items[0]!;

      const reason = "Subcontractor must provide chain-of-custody soil assay from accredited testing house";
      const updated = await reviewsApi.requestEvidence(
        item,
        {
          reason,
          requested_details: "Soil chemistry assay reports for Pier 8",
        },
        {
          name: "Project Lead",
          role: "project_manager",
        }
      );

      assert.equal(updated.status, "evidence_requested");
      const latestAudit = updated.audit_history[updated.audit_history.length - 1]!;
      assert.equal(latestAudit.action, "risk.evidence_requested");
      assert.equal(latestAudit.reason, reason);
      assert.equal(latestAudit.actor_name, "Project Lead");
      assert.deepEqual(latestAudit.details, {
        requested_details: "Soil chemistry assay reports for Pier 8",
      });
    });
  });

  describe("6. Convert Risk to Change Order Workflow", () => {
    it("validates convert to change order schema requiring reference and reason", () => {
      const missingRef = riskConvertChangeOrderSchema.safeParse({
        change_order_reference: "",
        change_order_title: "New change order",
        reason: "Commercial justification",
      });
      assert.equal(missingRef.success, false);

      const missingReason = riskConvertChangeOrderSchema.safeParse({
        change_order_reference: "CO-099",
        change_order_title: "New change order",
        reason: "",
      });
      assert.equal(missingReason.success, false);

      const valid = riskConvertChangeOrderSchema.safeParse({
        change_order_reference: "CO-099",
        change_order_title: "Excavation Obstruction Dewatering",
        reason: "Contractor entitlement verified under clause 4.12",
      });
      assert.equal(valid.success, true);
    });

    it("converts risk to change order, records reference, and logs audit trail", async () => {
      const items = await reviewsApi.list({ category: "high_severity_risk" });
      const item = items[0]!;

      const payload = {
        change_order_reference: "CO-045",
        change_order_title: "Structural Steel Rolling Outage Reroute",
        reason: "Accepted secondary mill rate premium as formal variation CO-045",
        amount: "28000.00",
        time_impact_days: 7,
      };

      const converted = await reviewsApi.convertToChangeOrder(item, payload, {
        name: "Commercial Manager",
        role: "commercial_manager",
      });

      assert.equal(converted.status, "converted");
      assert.equal(converted.change_order_reference, "CO-045");
      assert.equal(converted.financial_exposure, "28000.00");
      assert.equal(converted.schedule_impact_days, 7);

      const latestAudit = converted.audit_history[converted.audit_history.length - 1]!;
      assert.equal(latestAudit.action, "risk.converted_to_change_order");
      assert.equal(latestAudit.reason, payload.reason);
      assert.equal(latestAudit.actor_name, "Commercial Manager");
      assert.deepEqual(latestAudit.details, {
        change_order_reference: "CO-045",
        change_order_title: "Structural Steel Rolling Outage Reroute",
        amount: "28000.00",
        time_impact_days: 7,
      });
    });
  });

  describe("7. RBAC Authorization Protection", () => {
    it("prevents unauthorized roles from deciding risks and approving changes", () => {
      const riskAcceptPermission: Permission = "risks.accept";
      const approvalPermission: Permission = "approvals.decide";

      // Authorized roles
      const authorizedRoles: Role[] = ["owner", "admin", "project_manager", "commercial_manager"];
      for (const role of authorizedRoles) {
        assert.ok(hasPermission(role, riskAcceptPermission), `Role ${role} should have risks.accept`);
        assert.ok(hasPermission(role, approvalPermission), `Role ${role} should have approvals.decide`);
      }

      // Unauthorized roles (MUST be prevented)
      const unauthorizedRoles: Role[] = ["site_engineer", "viewer", "auditor"];
      for (const role of unauthorizedRoles) {
        assert.equal(hasPermission(role, riskAcceptPermission), false, `Role ${role} must NOT have risks.accept`);
        assert.equal(hasPermission(role, approvalPermission), false, `Role ${role} must NOT have approvals.decide`);
      }
    });
  });

  describe("8. Mocked API Responses & Audit Invariants", () => {
    it("handles mock change order approval and rejection API responses", async () => {
      const items = await reviewsApi.list();
      const changeOrderReview = items.find((i) => i.entity_type === "change_order")!;
      assert.ok(changeOrderReview, "Should find a change order review item");

      const approved = await reviewsApi.approve(changeOrderReview, "Certified by supervising engineer", {
        name: "Elena Rostova",
        role: "commercial_manager",
      });
      assert.equal(approved.status, "approved");

      const rejected = await reviewsApi.reject(
        changeOrderReview,
        "Rejected: Subcontractor daywork sheet lacks resident engineer signature",
        {
          name: "Elena Rostova",
          role: "commercial_manager",
        }
      );
      assert.equal(rejected.status, "rejected");
      const latestAudit = rejected.audit_history[rejected.audit_history.length - 1]!;
      assert.equal(latestAudit.action, "review.rejected");
      assert.ok(latestAudit.reason?.includes("lacks resident engineer signature"));
    });

    it("verifies conflicting evidence links and telemetry citations", async () => {
      const items = await reviewsApi.list({ category: "conflicting_evidence" });
      assert.ok(items.length > 0);
      const conflictItem = items[0]!;

      assert.equal(conflictItem.evidence_links.length, 2);
      const [claimDoc, telemetryDoc] = conflictItem.evidence_links;
      assert.ok(claimDoc, "Must have claim document citation");
      assert.ok(telemetryDoc, "Must have telemetry document citation");

      assert.ok(claimDoc.document_name.includes("Claim Letter"));
      assert.ok(telemetryDoc.document_name.includes("Telemetry"));
      assert.ok((telemetryDoc.confidence ?? 0) >= 0.95);
      assert.ok(telemetryDoc.excerpt.includes("Automated rain gauge"));
    });
  });
});
