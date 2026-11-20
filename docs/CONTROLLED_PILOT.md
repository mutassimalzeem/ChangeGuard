# Controlled construction project pilot

## Inspection and delivery

Main commit `146b7ce` included merged PRs #27–32. The onboarding page, per-file ZIP validation, hash deduplication, classification/extraction review, audited change-order workflow, weekly CSV and readiness PDF already existed. The implementation plan was to reuse these paths, bring eligible pilot findings into the queue at any severity, enforce pilot submission inputs, then connect current-access measurement to the page and exports. Implementation uses existing tables, permissions and audit events.

| Area | Files |
| --- | --- |
| Source visibility and queue category | `backend/app/policy/{project_evidence_visibility.sql,review_page.sql,review_page.py,scope.py}`, `backend/app/domain/schemas/review_workspace.py`, `frontend/src/lib/review-queue.ts` |
| Report and workflow | `backend/app/api/v1/routes/{pilot,pilot_metrics}.py`, `backend/app/domain/services/{change_orders,pilot_metrics,pilot_value}.py`, `backend/app/domain/schemas/pilot_metrics.py` |
| Operator interface | `frontend/src/app/{pilot,review-queue}/page.tsx`, `frontend/src/app/projects/[projectId]/change-orders/[orderId]/page.tsx`, `frontend/src/lib/api/{pilot,resources}.ts`, `frontend/src/components/pilot-value-report.ts` |
| Verification | `backend/tests/{conftest,test_daily_report_integration,test_pilot_integration,test_pilot_metrics,test_pilot_metrics_integration}.py`, `frontend/src/test/pilot-value.test.ts`, `.github/workflows/ci.yml` |
| Product and operations | PRD.md, ARCHITECTURE.md, DESIGN.md, SECURITY.md, TEST_PLAN.md, DECISIONS.md, MEMORY.md, this runbook and docs/PILOT_METRICS.md |

## Operator walkthrough

1. Sign in as an authorized pilot creator, open **Pilot onboarding** and create a project. Assign project members and an independent approver. Agree on measurement dates and collect a baseline if the customer wants to evaluate savings.
2. Import an approved ZIP of daily reports, RFIs, drawings and supporting evidence. Verify per-file outcomes. Import the same ZIP again and confirm duplicate rows are skipped. Inspect failed/quarantined files and processing stages.
3. Compare a completed classification and extraction with the original. Save a reason and provenance for a correction. Confirm that the source file and original prediction are retained.
4. Open the project's timeline and Review Queue. Inspect a cited finding and create an eligible draft. Check that an insufficient-evidence finding cannot be converted. Enter cost items and schedule impact. Submit with a reason and cost confirmation. A different authorized user records an approval or rejection reason. Inspect the resulting history.
5. As an owner/admin, review the sample counts, confidence distribution, failures, visible risk/decision counts, timing, missing evidence and recommended actions. Download both value exports. Repeat with a viewer and confirm financial reports are unavailable. Restrict a supporting source from a manager and refresh readiness; remove a source and refresh the value report.

## Deployment verification

Use the existing deployment checklist for database migrations, storage, Redis, worker health, secret configuration and gateway pricing. Deploy API and frontend together. Run the walkthrough first against an approved staging project. Confirm that background processing completes after closing the browser and that independent user sessions see their own authorized records. Verify CSV content type, PDF pagination and the no-store response header. This change needs no schema migration, historical backfill or new provider. Application rollback uses the preceding frontend/API versions.

The test suite uses controlled external services. Actual customer data, cold-start processing latency, provider invoices and customer savings have to be verified during the pilot. Cost means cover traced resources. Document review queue duration ends with the first recorded human pilot review. Risk review latency measures detection to first recorded reviewer action among reviewed findings. Neither duration measures active screen time. Historical date ranges reflect current visible source state. Re-exporting after a correction or revocation can change results.
