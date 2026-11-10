/**
 * Wire contracts, mirrored from the FastAPI backend.
 *
 * Source of truth (backend/app):
 *   domain/schemas/auth.py            Identity, Login, Register, TokenPair, Message
 *   domain/schemas/project.py         ProjectRead, PaginatedProjectResponse, ProjectCreate, ProjectUpdate
 *   domain/schemas/document.py        DocumentRead, ProcessingStatus
 *   domain/services/risks.py          read(): the risk detail dict, RiskDecision
 *   domain/services/change_orders.py  read(): the change-order detail dict, actions
 *   domain/services/potential_changes.py read_event(): potential change dict
 *   api/pagination.py                 PageMetadata
 *   core/security.py                  access-token claims
 */
import { z } from "zod";

/* ------------------------------------------------------------------ shared */

export const uuidSchema = z.string().uuid();

/** `api/pagination.py::PageMetadata` */
export const pageMetadataSchema = z.object({
  page: z.number().int().min(1),
  page_size: z.number().int().min(1),
  total_items: z.number().int().min(0),
  total_pages: z.number().int().min(0),
  has_next: z.boolean(),
  has_previous: z.boolean(),
});

export type PageMetadata = z.infer<typeof pageMetadataSchema>;

/** `{ items, metadata }` envelope returned by every paginated list endpoint. */
export function paginatedSchema<T extends z.ZodTypeAny>(item: T) {
  return z.object({ items: z.array(item), metadata: pageMetadataSchema });
}

/** Pydantic serialises `datetime` as ISO-8601; the string is kept as received. */
export const isoDateTimeSchema = z.string().min(1);

/** Pydantic serialises `date` as `YYYY-MM-DD`. */
export const isoDateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);

/** `Decimal` values are serialised as strings, never as floats. */
export const decimalStringSchema = z.string();

/* --------------------------------------------------------------------- auth */

const tenantSlugSchema = z
  .string()
  .min(1)
  .max(100)
  .regex(/^[a-z0-9][a-z0-9-]*$/, "Use lowercase letters, digits and dashes");

const emailSchema = z.string().email("Enter a valid email address");

/** `schemas/auth.py::Identity` */
export const identitySchema = z.object({ tenant_slug: tenantSlugSchema, email: emailSchema });

/** `schemas/auth.py::Login` */
export const loginSchema = identitySchema.extend({
  password: z.string().min(1, "Enter your password").max(1024),
});

/** `schemas/auth.py::Register` */
export const registerSchema = identitySchema.extend({
  password: z.string().min(12, "Use at least 12 characters").max(1024),
  full_name: z.string().min(1, "Enter your full name").max(255),
  tenant_name: z.string().min(1, "Enter your company or organization name").max(255),
});

/** `schemas/auth.py::TokenPair` */
export const tokenPairSchema = z.object({
  access_token: z.string().min(1),
  refresh_token: z.string().min(1),
  token_type: z.string(),
  expires_in: z.number().int().positive(),
});

export type Login = z.infer<typeof loginSchema>;
export type Register = z.infer<typeof registerSchema>;
export type TokenPair = z.infer<typeof tokenPairSchema>;

/** `schemas/auth.py::Message` */
export const messageSchema = z.object({ message: z.string() });

/* ------------------------------------------------------------------ project */

export const PROJECT_STATUSES = ["active", "on_hold", "completed", "cancelled", "archived"] as const;
export const projectStatusSchema = z.enum(PROJECT_STATUSES);
export type ProjectStatus = z.infer<typeof projectStatusSchema>;

/** `schemas/project.py::ProjectRead` */
export const projectSchema = z.object({
  id: uuidSchema,
  code: z.string().min(1).max(64),
  tenant_id: uuidSchema,
  name: z.string().min(1),
  client_name: z.string().min(1),
  description: z.string().nullable().default(null),
  contract_value: z.string().nullable().default(null),
  currency: z.string().length(3),
  start_date: isoDateSchema.nullable().default(null),
  expected_end_date: isoDateSchema.nullable().default(null),
  status: projectStatusSchema,
  stakeholders: z.array(z.string()).nullable().default(null),
  created_at: isoDateTimeSchema,
  updated_at: isoDateTimeSchema,
});

export type Project = z.infer<typeof projectSchema>;

/** `schemas/project.py::PaginatedProjectResponse` */
export const projectListParamsSchema = z.object({
  page: z.number().int().min(1).default(1),
  page_size: z.number().int().min(1).max(100).default(20),
  status: projectStatusSchema.nullable().default(null),
  search: z.string().min(1).max(255).nullable().default(null),
});

export type ProjectListParams = z.input<typeof projectListParamsSchema>;

/** `schemas/project.py::ProjectCreate` */
export const projectCreateSchema = z.object({
  code: z
    .string()
    .min(1, "Project code is required")
    .max(64)
    .regex(/^[A-Z0-9_-]+$/, "Uppercase letters, digits, underscores and dashes only"),
  name: z.string().min(1, "Project name is required").max(255),
  client_name: z.string().min(1, "Client name is required").max(255),
  description: z.string().max(5000).nullable().default(null),
  contract_value: z
    .string()
    .regex(/^\d+(\.\d{1,2})?$/, "Use a positive amount with up to two decimals")
    .nullable()
    .default(null),
  currency: z.string().length(3).regex(/^[A-Z]{3}$/, "Three uppercase letters").default("USD"),
  start_date: isoDateSchema.nullable().default(null),
  expected_end_date: isoDateSchema.nullable().default(null),
  status: projectStatusSchema.default("active"),
  stakeholders: z.array(z.string().min(1)).max(20).nullable().default(null),
});

export type ProjectCreate = z.infer<typeof projectCreateSchema>;

/** `schemas/project.py::ProjectUpdate` */
export const projectUpdateSchema = projectCreateSchema.partial();
export type ProjectUpdate = z.infer<typeof projectUpdateSchema>;

/* ------------------------------------------------------------------ documents */

export const DOCUMENT_STATUSES = [
  "received",
  "validating",
  "stored",
  "queued",
  "processing",
  "extracted",
  "classified",
  "indexed",
  "linked",
  "review_required",
  "completed",
  "failed",
  "quarantined",
] as const;

export const documentSchema = z
  .object({
    document_id: z.string().optional(),
    id: z.string().optional(),
    tenant_id: z.string().optional(),
    project_id: z.string().optional(),
    file_name: z.string().optional(),
    filename: z.string().optional(),
    original_file_key: z.string().optional(),
    storage_key: z.string().optional(),
    file_type: z.string().optional(),
    mime_type: z.string().optional(),
    file_size: z.number().int().optional(),
    size_bytes: z.number().int().optional(),
    source: z.string().default("upload"),
    processing_status: z.string().default("received"),
    status: z.string().default("received"),
    document_type: z.string().nullable().default(null),
    uploaded_at: z.string().optional(),
    created_at: z.string().optional(),
    access_level: z.string().default("project"),
    extraction_confidence: z.number().nullable().optional(),
    error_message: z.string().nullable().optional(),
  })
  .passthrough();

export type DocumentItem = z.infer<typeof documentSchema>;

/* ------------------------------------------------------------------ risks */

export const RISK_SEVERITIES = ["low", "medium", "high", "critical"] as const;
export type RiskSeverity = (typeof RISK_SEVERITIES)[number];

export const riskSchema = z
  .object({
    id: z.string(),
    risk_type: z.string().optional(),
    severity: z.string().default("medium"),
    title: z.string(),
    description: z.string().default(""),
    financial_exposure: z.string().nullable().default(null),
    currency: z.string().nullable().default("USD"),
    schedule_impact_days: z.number().int().nullable().default(null),
    responsible_party: z.string().nullable().default(null),
    evidence_links: z.array(z.string()).default([]),
    recommended_action: z.string().nullable().default(null),
    confidence: z.number().nullable().default(null),
    status: z.string().default("detected"),
  })
  .passthrough();

export type RiskItem = z.infer<typeof riskSchema>;

export const riskDecisionSchema = z.object({
  action: z.enum(["accept", "dismiss", "override"]),
  reason: z.string().min(1, "Reason is mandatory").max(2000),
  severity: z.enum(RISK_SEVERITIES).optional(),
  schedule_impact_days: z.number().int().min(0).max(36500).optional(),
});

export type RiskDecisionInput = z.infer<typeof riskDecisionSchema>;

/* ----------------------------------------------------------- potential changes */

export const potentialChangeSchema = z
  .object({
    id: z.string(),
    title: z.string(),
    description: z.string().default(""),
    detected_date: z.string().nullable().default(null),
    event_type: z.string().default("variance"),
    evidence_links: z.array(z.string()).default([]),
    confidence: z.number().nullable().default(null),
    suggested_owner: z.string().nullable().default(null),
    suggested_cost_impact: z.string().nullable().default(null),
    suggested_currency: z.string().nullable().default("USD"),
    suggested_schedule_impact: z.number().int().nullable().default(null),
    status: z.string().default("detected"),
    human_review_required: z.boolean().default(true),
  })
  .passthrough();

export type PotentialChangeItem = z.infer<typeof potentialChangeSchema>;

/* ------------------------------------------------------------- change orders */

export const CHANGE_ORDER_STATUSES = [
  "draft",
  "submitted",
  "approved",
  "rejected",
  "cancelled",
] as const;

export const approvalRecordSchema = z
  .object({
    status: z.string(),
    reason: z.string().nullable().default(null),
    decided_by_id: z.string().nullable().default(null),
    decided_at: z.string().nullable().default(null),
    submitted_at: z.string().nullable().default(null),
  })
  .passthrough();

export const changeOrderSchema = z
  .object({
    id: z.string(),
    project_id: z.string(),
    reference: z.string(),
    title: z.string(),
    description: z.string().default(""),
    status: z.string().default("draft"),
    amount: z.string().nullable().default(null),
    currency: z.string().default("USD"),
    cost_items: z.record(z.string(), z.unknown()).nullable().default(null),
    time_impact_days: z.number().int().nullable().default(null),
    draft: z.record(z.string(), z.unknown()).nullable().default(null),
    source_event_id: z.string().nullable().default(null),
    evidence_links: z.array(z.string()).default([]),
    approval_history: z.array(approvalRecordSchema).default([]),
  })
  .passthrough();

export type ChangeOrderItem = z.infer<typeof changeOrderSchema>;

export const changeOrderCreateSchema = z.object({
  reference: z.string().min(1, "Reference is required").max(64),
  title: z.string().min(1, "Title is required").max(255),
  description: z.string().default(""),
  amount: z.string().regex(/^\d+(\.\d{1,2})?$/, "Valid currency amount").nullable().default(null),
  currency: z.string().length(3).default("USD"),
  time_impact_days: z.number().int().min(0).nullable().default(null),
  contract_id: z.string().uuid().nullable().optional(),
  rfi_id: z.string().uuid().nullable().optional(),
  evidence: z.array(z.string().uuid()).default([]),
});

export type ChangeOrderCreateInput = z.infer<typeof changeOrderCreateSchema>;

export const changeOrderPatchSchema = z.object({
  title: z.string().min(1).max(255).optional(),
  description: z.string().optional(),
  amount: z.string().regex(/^\d+(\.\d{1,2})?$/).nullable().optional(),
  time_impact_days: z.number().int().min(0).nullable().optional(),
});

export type ChangeOrderPatchInput = z.infer<typeof changeOrderPatchSchema>;

/* ----------------------------------------------------------------- timeline */

export const timelineEventSchema = z
  .object({
    id: z.string(),
    project_id: z.string().optional(),
    title: z.string(),
    description: z.string().default(""),
    occurred_at: z.string(),
    event_type: z.string().default("event"),
    evidence_links: z.array(z.string()).default([]),
    source_type: z.string().nullable().optional(),
    source_id: z.string().nullable().optional(),
  })
  .passthrough();

export type TimelineEvent = z.infer<typeof timelineEventSchema>;

export const timelineSourceSchema = z.object({
  evidence_link_id: z.string().uuid(),
  source_type: z.string(),
  source_id: z.string().uuid(),
  source_page: z.number().int().positive().nullable(),
  source_text_snippet: z.string().nullable(),
});

export const projectTimelineItemSchema = z.object({
  id: z.string().uuid(),
  kind: z.enum(["event", "risk"]),
  occurred_at: z.string(),
  title: z.string(),
  description: z.string().nullable(),
  event_type: z.string(),
  status: z.string(),
  confidence: z.coerce.number().min(0).max(1).nullable(),
  severity: z.string().nullable(),
  evidence_status: z.enum(["supported", "insufficient_evidence"]),
  evidence: z.array(timelineSourceSchema),
});

export const projectTimelineSchema = z.object({
  items: z.array(projectTimelineItemSchema),
  offset: z.number().int().nonnegative(),
  limit: z.number().int().positive(),
  has_more: z.boolean(),
});

/* ----------------------------------------------------------------- evidence */

export const evidenceItemSchema = z
  .object({
    id: z.string().optional(),
    project_id: z.string().optional(),
    subject_type: z.string().optional(),
    subject_id: z.string().optional(),
    source_type: z.string(),
    source_id: z.string(),
    page_number: z.number().int().nullable().optional(),
    excerpt: z.string(),
    created_at: z.string().optional(),
  })
  .passthrough();

export type EvidenceItem = z.infer<typeof evidenceItemSchema>;

export const evidenceResultSchema = z
  .object({
    subject_type: z.string(),
    subject_id: z.string(),
    items: z.array(evidenceItemSchema).default([]),
    total: z.number().int().default(0),
  })
  .passthrough();

export type EvidenceResult = z.infer<typeof evidenceResultSchema>;

/* ----------------------------------------------------------- investigations */

export const citationSchema = z
  .object({
    evidence_id: z.string(),
    quote: z.string(),
    source_type: z.string().optional(),
    source_id: z.string().optional(),
  })
  .passthrough();

export type Citation = z.infer<typeof citationSchema>;

export const conclusionSchema = z
  .object({
    kind: z.enum(["supported", "conflict", "insufficient_evidence"]).default("supported"),
    citations: z.array(citationSchema).default([]),
    recommended_action: z.enum(["no_action", "request_human_review"]).default("no_action"),
    confidence: z.number().min(0).max(1).default(0.85),
    summary: z.string().optional(),
  })
  .passthrough();

export type Conclusion = z.infer<typeof conclusionSchema>;

export const investigationResultSchema = z
  .object({
    run_id: z.string(),
    status: z.string(),
    conclusions: z.array(conclusionSchema).default([]),
    action: z.unknown().nullable().optional(),
    tool_calls: z.number().int().default(0),
    human_review_required: z.boolean().default(false),
    trace: z.array(z.record(z.string(), z.unknown())).default([]),
  })
  .passthrough();

export type InvestigationResult = z.infer<typeof investigationResultSchema>;

/* ------------------------------------------------------------- review queue */

export const REVIEW_CATEGORIES = [
  "low_confidence_extraction",
  "missing_required_field",
  "potential_duplicate",
  "conflicting_evidence",
  "high_value_change",
  "high_severity_risk",
  "approval_request",
] as const;

export type ReviewCategory = (typeof REVIEW_CATEGORIES)[number];

export const reviewCategorySchema = z.enum(REVIEW_CATEGORIES);

export const reviewAuditRecordSchema = z.object({
  id: z.string(),
  timestamp: isoDateTimeSchema,
  actor_name: z.string(),
  actor_role: z.string(),
  action: z.string(),
  reason: z.string().nullable().default(null),
  details: z.record(z.string(), z.unknown()).optional(),
});

export type ReviewAuditRecord = z.infer<typeof reviewAuditRecordSchema>;

export const reviewEvidenceLinkSchema = z.object({
  id: z.string(),
  source_type: z.string(),
  source_id: z.string(),
  document_name: z.string(),
  page_number: z.number().int().nullable().optional(),
  excerpt: z.string(),
  confidence: z.number().min(0).max(1).optional(),
});

export type ReviewEvidenceLink = z.infer<typeof reviewEvidenceLinkSchema>;

export const reviewItemSchema = z.object({
  id: z.string(),
  category: reviewCategorySchema,
  title: z.string().min(1),
  project_id: z.string(),
  project_code: z.string(),
  project_name: z.string(),
  severity: z.enum(["low", "medium", "high", "critical"]).default("medium"),
  system_found: z.string(),
  why_review_needed: z.string(),
  evidence_links: z.array(reviewEvidenceLinkSchema).default([]),
  recommended_correction: z.string(),
  financial_exposure: z.string().nullable().default(null),
  currency: z.string().default("USD"),
  schedule_impact_days: z.number().int().nullable().default(null),
  status: z.enum(["pending", "approved", "rejected", "overridden"]).default("pending"),
  entity_type: z.enum(["change_order", "risk", "document", "potential_change", "extraction"]),
  entity_id: z.string(),
  required_permission: z.string().default("approvals.decide"),
  audit_history: z.array(reviewAuditRecordSchema).default([]),
  created_at: isoDateTimeSchema,
  updated_at: isoDateTimeSchema.optional(),
});

export type ReviewItem = z.infer<typeof reviewItemSchema>;

export const reviewDecisionSchema = z.object({
  action: z.enum(["approve", "reject", "override"]),
  reason: z.string().trim().min(1, "A justification reason is required for audited compliance"),
  override_severity: z.enum(["low", "medium", "high", "critical"]).optional(),
  override_schedule_impact_days: z.number().int().min(0).optional(),
  override_financial_exposure: z.string().optional(),
});

export type ReviewDecisionInput = z.infer<typeof reviewDecisionSchema>;

export const reviewEditSchema = z.object({
  title: z.string().trim().min(1, "Title is required").optional(),
  recommended_correction: z.string().trim().min(1, "Correction details are required").optional(),
  financial_exposure: z.string().nullable().optional(),
  schedule_impact_days: z.number().int().min(0).nullable().optional(),
  reason: z.string().trim().min(1, "An audited change note is required"),
});

export type ReviewEditInput = z.infer<typeof reviewEditSchema>;

export const REVIEW_CATEGORY_META: Record<
  ReviewCategory,
  {
    label: string;
    description: string;
    defaultPermission: string;
    tone: "neutral" | "brand" | "success" | "warning" | "danger";
  }
> = {
  low_confidence_extraction: {
    label: "Low-confidence extraction",
    description: "Automated OCR or model extraction fell below confidence threshold and requires manual verification.",
    defaultPermission: "documents.write",
    tone: "warning",
  },
  missing_required_field: {
    label: "Missing required field",
    description: "Subcontractor or supplier notice lacks mandatory statutory, temporal, or clause particulars.",
    defaultPermission: "change_orders.write",
    tone: "warning",
  },
  potential_duplicate: {
    label: "Potential duplicate",
    description: "Identical scope variance or notice has already been captured under an active instruction.",
    defaultPermission: "change_orders.write",
    tone: "neutral",
  },
  conflicting_evidence: {
    label: "Conflicting evidence",
    description: "Contemporaneous site records or weather logs contradict submitted claims.",
    defaultPermission: "approvals.decide",
    tone: "danger",
  },
  high_value_change: {
    label: "High-value change",
    description: "Financial exposure exceeds single-signoff delegated commercial authority.",
    defaultPermission: "approvals.decide",
    tone: "danger",
  },
  high_severity_risk: {
    label: "High-severity risk",
    description: "Critical risk exceeds schedule or cost tolerance and mandates commercial decision.",
    defaultPermission: "risks.accept",
    tone: "danger",
  },
  approval_request: {
    label: "Approval request",
    description: "Formal change order submitted for commercial approval workflow sign-off.",
    defaultPermission: "approvals.decide",
    tone: "brand",
  },
};


