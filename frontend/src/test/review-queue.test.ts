import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";

import {
  REVIEW_CATEGORIES,
  REVIEW_CATEGORY_META,
  reviewDecisionSchema,
  reviewEditSchema,
  reviewItemSchema,
  type ReviewCategory,
} from "../lib/contracts.ts";
import { hasPermission, ROLE_PERMISSIONS, ROLES, type Permission, type Role } from "../lib/rbac.ts";
import { reviewsApi } from "../lib/api/resources.ts";

describe("Milestone 6.3 - Review Queue & Approvals", () => {
  beforeEach(() => {
    reviewsApi.clearOverrides();
  });

  describe("1. Category Coverage (7 Categories)", () => {
    it("defines all 7 mandatory review queue categories", () => {
      const expectedCategories: ReviewCategory[] = [
        "low_confidence_extraction",
        "missing_required_field",
        "potential_duplicate",
        "conflicting_evidence",
        "high_value_change",
        "high_severity_risk",
        "approval_request",
      ];

      assert.equal(REVIEW_CATEGORIES.length, 7);
      for (const cat of expectedCategories) {
        assert.ok(REVIEW_CATEGORIES.includes(cat), `Missing expected category: ${cat}`);
        const meta = REVIEW_CATEGORY_META[cat];
        assert.ok(meta, `Missing metadata for ${cat}`);
        assert.ok(meta.label.length > 0, `Missing label for ${cat}`);
        assert.ok(meta.description.length > 0, `Missing description for ${cat}`);
        assert.ok(meta.defaultPermission.length > 0, `Missing default permission for ${cat}`);
      }
    });
  });

  describe("2. Review Item Structure & Validation", () => {
    it("loads items satisfying full review schema with all required fields", async () => {
      const items = await reviewsApi.list();
      assert.ok(items.length >= 7, "Should supply baseline items across all 7 categories");

      // Verify that every category is represented in baseline
      const representedCategories = new Set(items.map((i) => i.category));
      for (const cat of REVIEW_CATEGORIES) {
        assert.ok(
          representedCategories.has(cat),
          `Category ${cat} must be represented in review queue items`
        );
      }

      for (const item of items) {
        // Validate against Zod schema
        const parsed = reviewItemSchema.safeParse(item);
        assert.ok(parsed.success, `Item ${item.id} failed schema validation: ${JSON.stringify(parsed)}`);

        // Check required fields per prompt requirements
        assert.ok(item.system_found && item.system_found.length > 10, "Must specify what the system found");
        assert.ok(item.why_review_needed && item.why_review_needed.length > 10, "Must specify why review is needed");
        assert.ok(Array.isArray(item.evidence_links), "Must provide evidence links array");
        assert.ok(item.evidence_links.length > 0, "Item should have evidence citations");

        for (const ev of item.evidence_links) {
          assert.ok(ev.document_name, "Evidence link must have document name");
          assert.ok(ev.excerpt, "Evidence link must have text excerpt");
        }

        assert.ok(item.recommended_correction && item.recommended_correction.length > 10, "Must specify recommended correction");
        assert.ok(Array.isArray(item.audit_history), "Must have audit history array");
        assert.ok(item.audit_history.length > 0, "Initial audit history event must be present");
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
  });

  describe("3. Rejection & Override Mandatory Reason Enforcement", () => {
    it("rejects review decision schema when reason is empty or whitespace", () => {
      const emptyResult = reviewDecisionSchema.safeParse({
        action: "reject",
        reason: "",
      });
      assert.equal(emptyResult.success, false, "Schema must reject empty reason");

      const whitespaceResult = reviewDecisionSchema.safeParse({
        action: "reject",
        reason: "   ",
      });
      assert.equal(whitespaceResult.success, false, "Schema must reject whitespace-only reason");
    });

    it("requires reason when calling reviewsApi.reject", async () => {
      const items = await reviewsApi.list();
      const item = items[0]!;

      await assert.rejects(
        async () => {
          await reviewsApi.reject(item, "   ");
        },
        {
          message: "A justification reason is required for rejection",
        }
      );
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

  describe("4. Approval Workflow & Backend API Call", () => {
    it("approves item and appends to audit history with actor details and timestamp", async () => {
      const items = await reviewsApi.list();
      const item = items.find((i) => i.category === "approval_request")!;
      assert.ok(item, "Must have an approval request item");

      const reason = "Signed off in commercial review meeting with Engineer approval";
      const updated = await reviewsApi.approve(item, reason, {
        name: "Marcus Aurelius",
        role: "commercial_manager",
      });

      assert.equal(updated.status, "approved");
      assert.ok(updated.audit_history.length > item.audit_history.length);

      const latestAudit = updated.audit_history[updated.audit_history.length - 1]!;
      assert.equal(latestAudit.action, "review.approved");
      assert.equal(latestAudit.actor_name, "Marcus Aurelius");
      assert.equal(latestAudit.actor_role, "commercial_manager");
      assert.equal(latestAudit.reason, reason);
      assert.ok(Date.parse(latestAudit.timestamp) > 0, "Timestamp must be valid ISO date");
    });
  });

  describe("5. Override Workflow & Audit Trail", () => {
    it("applies parameter override and records before/after state in audit history", async () => {
      const items = await reviewsApi.list();
      const riskItem = items.find((i) => i.category === "high_severity_risk")!;
      assert.ok(riskItem, "Must have high severity risk item");

      const overridePayload = {
        reason: "Secondary certified rolling mill engaged; critical path impact reduced from 42 to 7 days.",
        severity: "medium" as const,
        schedule_impact_days: 7,
        financial_exposure: "28000.00",
      };

      const updated = await reviewsApi.override(riskItem, overridePayload, {
        name: "Sarah Chen",
        role: "project_manager",
      });

      assert.equal(updated.status, "overridden");
      assert.equal(updated.severity, "medium");
      assert.equal(updated.schedule_impact_days, 7);
      assert.equal(updated.financial_exposure, "28000.00");

      const auditEvent = updated.audit_history[updated.audit_history.length - 1]!;
      assert.equal(auditEvent.action, "review.overridden");
      assert.equal(auditEvent.actor_name, "Sarah Chen");
      assert.equal(auditEvent.reason, overridePayload.reason);
      assert.deepEqual(auditEvent.details, {
        severity: "medium",
        schedule_impact_days: 7,
        financial_exposure: "28000.00",
      });
    });
  });

  describe("6. Edit Recommendation Workflow", () => {
    it("validates mandatory edit reason and amends fields with audited trail", async () => {
      const items = await reviewsApi.list();
      const item = items.find((i) => i.category === "missing_required_field")!;

      // Validation fails without reason
      const invalidEdit = reviewEditSchema.safeParse({
        title: "Amended Title",
        reason: "",
      });
      assert.equal(invalidEdit.success, false);

      const updated = await reviewsApi.edit(
        item,
        {
          title: "FIDIC 20.1 Ground Conditions Particulars Formally Requested",
          recommended_correction: "Issue 14-day compliance cure letter under clause 15.1.",
          financial_exposure: "62000.00",
          schedule_impact_days: 10,
          reason: "Clarified contractor notice timeline following preliminary geotechnical review.",
        },
        { name: "Auditor Lead", role: "commercial_manager" }
      );

      assert.equal(updated.title, "FIDIC 20.1 Ground Conditions Particulars Formally Requested");
      assert.equal(updated.recommended_correction, "Issue 14-day compliance cure letter under clause 15.1.");
      assert.equal(updated.financial_exposure, "62000.00");
      assert.equal(updated.schedule_impact_days, 10);

      const latestAudit = updated.audit_history[updated.audit_history.length - 1]!;
      assert.equal(latestAudit.action, "review.edited");
      assert.equal(latestAudit.actor_name, "Auditor Lead");
    });
  });

  describe("7. RBAC Authorization Protection", () => {
    it("prevents unauthorized roles from approving commercial decisions", () => {
      const commercialApprovalPermission: Permission = "approvals.decide";

      // Authorized roles
      const authorizedRoles: Role[] = ["owner", "admin", "project_manager", "commercial_manager"];
      for (const role of authorizedRoles) {
        assert.ok(
          hasPermission(role, commercialApprovalPermission),
          `Role '${role}' should be authorized for ${commercialApprovalPermission}`
        );
      }

      // Unauthorized roles (MUST be prevented)
      const unauthorizedRoles: Role[] = ["site_engineer", "viewer", "auditor"];
      for (const role of unauthorizedRoles) {
        assert.equal(
          hasPermission(role, commercialApprovalPermission),
          false,
          `Role '${role}' must NOT be authorized for ${commercialApprovalPermission}`
        );
      }
    });

    it("verifies risk acceptance authorization boundaries", () => {
      const riskAcceptPermission: Permission = "risks.accept";

      // Site engineers, viewers, auditors cannot accept commercial risks
      assert.equal(hasPermission("site_engineer", riskAcceptPermission), false);
      assert.equal(hasPermission("viewer", riskAcceptPermission), false);
      assert.equal(hasPermission("auditor", riskAcceptPermission), false);

      // Commercial and project managers can accept
      assert.equal(hasPermission("commercial_manager", riskAcceptPermission), true);
      assert.equal(hasPermission("project_manager", riskAcceptPermission), true);
    });

    it("confirms each defined role has a distinct, complete permission set", () => {
      for (const role of ROLES) {
        const perms = ROLE_PERMISSIONS[role];
        assert.ok(perms instanceof Set, `Role ${role} must have a permission set`);
        assert.ok(perms.size > 0, `Role ${role} must have at least one permission`);
      }
    });
  });

  describe("8. Mocked API Responses & Workflow Invariants", () => {
    it("handles mock change order approval and rejection API responses", async () => {
      const items = await reviewsApi.list();
      const changeOrderReview = items.find((i) => i.entity_type === "change_order")!;
      assert.ok(changeOrderReview, "Should find a change order review item");

      // Approve call
      const approved = await reviewsApi.approve(changeOrderReview, "Certified by supervising engineer", {
        name: "Elena Rostova",
        role: "commercial_manager",
      });
      assert.equal(approved.status, "approved");

      // Rejection with mandatory reason
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

    it("verifies financial exposure formatting and currency preservation", async () => {
      const items = await reviewsApi.list();
      const highValueItem = items.find((i) => i.category === "high_value_change")!;
      assert.ok(highValueItem, "Must have high value change item");
      assert.equal(highValueItem.currency, "USD");
      assert.equal(highValueItem.financial_exposure, "185000.00");
      assert.ok(Number(highValueItem.financial_exposure) > 100000, "Must exceed $100k signing limit");
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
