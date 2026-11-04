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
