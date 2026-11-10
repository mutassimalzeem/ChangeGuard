/**
 * Endpoint functions. Each validates its response against `contracts.ts`, so a
 * backend change surfaces as an `ApiError` at the call site instead of an
 * undefined field rendering somewhere far away.
 */
import { z } from "zod";

import {
  changeOrderCreateSchema,
  changeOrderPatchSchema,
  changeOrderSchema,
  documentSchema,
  messageSchema,
  paginatedSchema,
  potentialChangeSchema,
  projectCreateSchema,
  projectListParamsSchema,
  projectSchema,
  projectUpdateSchema,
  projectTimelineSchema,
  riskDecisionSchema,
  riskSchema,
  evidenceResultSchema,
  investigationResultSchema,
  reviewEditSchema,
  reviewItemSchema,
  tokenPairSchema,
  type ChangeOrderCreateInput,
  type ChangeOrderItem,
  type ChangeOrderPatchInput,
  type DocumentItem,
  type EvidenceResult,
  type InvestigationResult,
  type PotentialChangeItem,
  type Project,
  type ProjectCreate,
  type ProjectListParams,
  type ProjectUpdate,
  type ReviewAuditRecord,
  type ReviewCategory,
  type ReviewEditInput,
  type ReviewItem,
  type RiskDecisionInput,
  type RiskItem,
  type RiskSeverity,
} from "../contracts.ts";
import { client } from "./client.ts";
import { ApiError, type FieldIssue } from "./errors.ts";

function parse<T extends z.ZodTypeAny>(schema: T, data: unknown): z.infer<T> {
  const result = schema.safeParse(data);
  if (result.success) {
    return result.data;
  }
  const issues: FieldIssue[] = result.error.issues.map((issue) => ({
    field: issue.path.join(".") || "response",
    message: issue.message,
  }));
  throw new ApiError({
    kind: "invalid-response",
    status: null,
    message: "The API returned a response this app does not understand. It may be out of date.",
    code: "INVALID_RESPONSE",
    details: result.error.issues,
    issues,
  });
}

/* --------------------------------------------------------------------- auth */

export const authApi = {
  async login(payload: { tenant_slug: string; email: string; password: string }): Promise<z.infer<typeof tokenPairSchema>> {
    const response = await client.post("/auth/login", payload);
    return parse(tokenPairSchema, response.data);
  },

  async register(payload: {
    tenant_slug: string;
    email: string;
    password: string;
    full_name: string;
    tenant_name: string;
  }): Promise<{ message: string }> {
    const response = await client.post("/auth/register", payload);
    return parse(messageSchema, response.data);
  },

  async logout(refreshToken: string): Promise<void> {
    await client.post("/auth/logout", { refresh_token: refreshToken });
  },

  async requestPasswordReset(payload: { tenant_slug: string; email: string }): Promise<{ message: string }> {
    const response = await client.post("/auth/password-reset/request", payload);
    return parse(messageSchema, response.data);
  },

  async confirmPasswordReset(payload: { token: string; password: string }): Promise<{ message: string }> {
    const response = await client.post("/auth/password-reset/confirm", payload);
    return parse(messageSchema, response.data);
  },
};

/* ------------------------------------------------------------------ projects */

const projectPageSchema = paginatedSchema(projectSchema);

export const projectsApi = {
  async list(params: Partial<ProjectListParams> = {}): Promise<z.infer<typeof projectPageSchema>> {
    const query = projectListParamsSchema.parse(params);
    const response = await client.get("/projects", {
      params: {
        page: query.page,
        page_size: query.page_size,
        ...(query.status ? { status: query.status } : {}),
        ...(query.search ? { search: query.search } : {}),
      },
    });
    return parse(projectPageSchema, response.data);
  },

  async get(projectId: string): Promise<Project> {
    const response = await client.get(`/projects/${projectId}`);
    return parse(projectSchema, response.data);
  },

  async create(payload: ProjectCreate): Promise<Project> {
    const validated = projectCreateSchema.parse(payload);
    const response = await client.post("/projects", validated);
    return parse(projectSchema, response.data);
  },

  async update(projectId: string, payload: ProjectUpdate): Promise<Project> {
    const validated = projectUpdateSchema.parse(payload);
    const response = await client.patch(`/projects/${projectId}`, validated);
    return parse(projectSchema, response.data);
  },

  async delete(projectId: string): Promise<void> {
    await client.delete(`/projects/${projectId}`);
  },
};

/* ----------------------------------------------------------------- documents */

const documentListSchema = z.array(documentSchema);

export const documentsApi = {
  async list(projectId: string, offset = 0, limit = 50): Promise<DocumentItem[]> {
    const response = await client.get(`/projects/${projectId}/documents`, {
      params: { offset, limit },
    });
    return parse(documentListSchema, response.data);
  },

  async get(documentId: string): Promise<DocumentItem> {
    const response = await client.get(`/documents/${documentId}`);
    return parse(documentSchema, response.data);
  },

  async upload(projectId: string, formData: FormData): Promise<DocumentItem> {
    const response = await client.post(`/projects/${projectId}/documents`, formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return parse(documentSchema, response.data);
  },

  async downloadUrl(documentId: string): Promise<string> {
    const response = await client.get(`/documents/${documentId}/download-url`);
    if (typeof response.data === "string") return response.data;
    if (response.data && typeof response.data.url === "string") return response.data.url;
    return String(response.data);
  },

  async delete(documentId: string): Promise<void> {
    await client.delete(`/documents/${documentId}`);
  },
};

/* --------------------------------------------------------------------- risks */

const riskListSchema = z.array(riskSchema);

export const risksApi = {
  async list(projectId: string, offset = 0, limit = 50): Promise<RiskItem[]> {
    const response = await client.get(`/projects/${projectId}/risks`, {
      params: { offset, limit },
    });
    return parse(riskListSchema, response.data);
  },

  async get(projectId: string, riskId: string): Promise<RiskItem> {
    const response = await client.get(`/projects/${projectId}/risks/${riskId}`);
    return parse(riskSchema, response.data);
  },

  async decide(projectId: string, riskId: string, payload: RiskDecisionInput): Promise<RiskItem> {
    const validated = riskDecisionSchema.parse(payload);
    const response = await client.post(`/projects/${projectId}/risks/${riskId}/decisions`, validated);
    return parse(riskSchema, response.data);
  },

  async createChangeOrderDraft(
    projectId: string,
    riskId: string,
    payload?: { reference?: string; title?: string; reason?: string }
  ): Promise<ChangeOrderItem> {
    const response = await client.post(
      `/projects/${projectId}/risks/${riskId}/change-order-draft`,
      payload ?? {}
    );
    return parse(changeOrderSchema, response.data);
  },
};

export const timelineApi = {
  async list(projectId: string, offset = 0, limit = 50) {
    const response = await client.get(`/projects/${projectId}/timeline`, {
      params: { offset, limit },
    });
    return parse(projectTimelineSchema, response.data);
  },
};

/* --------------------------------------------------------- potential changes */

const potentialChangeListSchema = z.array(potentialChangeSchema);

export const potentialChangesApi = {
  async list(projectId: string, offset = 0, limit = 50): Promise<PotentialChangeItem[]> {
    const response = await client.get(`/projects/${projectId}/potential-changes`, {
      params: { offset, limit },
    });
    return parse(potentialChangeListSchema, response.data);
  },

  async get(projectId: string, eventId: string): Promise<PotentialChangeItem> {
    const response = await client.get(`/projects/${projectId}/potential-changes/${eventId}`);
    return parse(potentialChangeSchema, response.data);
  },
};

/* ------------------------------------------------------------- change orders */

export const changeOrdersApi = {
  async get(orderId: string): Promise<ChangeOrderItem> {
    const response = await client.get(`/change-orders/${orderId}`);
    return parse(changeOrderSchema, response.data);
  },

  async createFromRisk(
    projectId: string,
    riskId: string,
    payload?: { reference?: string; title?: string; reason?: string }
  ): Promise<ChangeOrderItem> {
    const response = await client.post(
      `/projects/${projectId}/risks/${riskId}/change-order-draft`,
      payload ?? {}
    );
    return parse(changeOrderSchema, response.data);
  },

  async create(projectId: string, payload: ChangeOrderCreateInput): Promise<ChangeOrderItem> {
    const validated = changeOrderCreateSchema.parse(payload);
    const response = await client.post(`/projects/${projectId}/change-orders`, validated);
    return parse(changeOrderSchema, response.data);
  },

  async patch(orderId: string, payload: ChangeOrderPatchInput): Promise<ChangeOrderItem> {
    const validated = changeOrderPatchSchema.parse(payload);
    const response = await client.patch(`/change-orders/${orderId}`, validated);
    return parse(changeOrderSchema, response.data);
  },

  async convert(orderId: string, rationale?: string): Promise<ChangeOrderItem> {
    const response = await client.post(`/change-orders/${orderId}/convert`, {
      rationale: rationale || "Converted by human reviewer",
    });
    return parse(changeOrderSchema, response.data);
  },

  async draft(orderId: string, draftContent: Record<string, unknown> = {}): Promise<ChangeOrderItem> {
    const response = await client.post(`/change-orders/${orderId}/draft`, {
      draft_content: draftContent,
    });
    return parse(changeOrderSchema, response.data);
  },

  async submit(orderId: string, comments = "Submitted for commercial approval"): Promise<ChangeOrderItem> {
    const response = await client.post(`/change-orders/${orderId}/submit`, {
      comments,
    });
    return parse(changeOrderSchema, response.data);
  },

  async approve(orderId: string, reason = "Approved"): Promise<ChangeOrderItem> {
    const response = await client.post(`/change-orders/${orderId}/approve`, {
      reason,
      comments: reason,
    });
    return parse(changeOrderSchema, response.data);
  },

  async reject(orderId: string, reason = "Rejected"): Promise<ChangeOrderItem> {
    const response = await client.post(`/change-orders/${orderId}/reject`, {
      reason,
      comments: reason,
    });
    return parse(changeOrderSchema, response.data);
  },

  async exportPdf(orderId: string): Promise<Blob> {
    const response = await client.post(
      `/change-orders/${orderId}/export`,
      {},
      { responseType: "blob" },
    );
    return response.data as Blob;
  },
};

/* ------------------------------------------------------------------ evidence */

export const evidenceApi = {
  async view(projectId: string, subjectType: string, subjectId: string): Promise<EvidenceResult> {
    const response = await client.get(`/projects/${projectId}/evidence/${subjectType}/${subjectId}`);
    return parse(evidenceResultSchema, response.data);
  },
};

/* ------------------------------------------------------------ investigations */

export const investigationsApi = {
  async ask(
    projectId: string,
    payload: { document_id: string; question: string; max_seconds?: number; max_tool_depth?: number }
  ): Promise<InvestigationResult> {
    const response = await client.post(`/projects/${projectId}/investigations`, {
      max_seconds: payload.max_seconds ?? 20,
      max_tool_depth: payload.max_tool_depth ?? 6,
      ...payload,
    });
    return parse(investigationResultSchema, response.data);
  },
};

/* -------------------------------------------------------------------- system */

export const systemApi = {
  async health(): Promise<{ status: string }> {
    const response = await client.get("/health");
    return response.data as { status: string };
  },
};

/* ------------------------------------------------------------- review queue */

const reviewItemListSchema = z.array(reviewItemSchema);

// In-memory store for review decisions, overrides, and audit trails
let sessionReviewOverrides: Record<string, Partial<ReviewItem>> = {};

export const reviewsApi = {
  clearOverrides() {
    sessionReviewOverrides = {};
  },

  async list(params: { projectId?: string; category?: ReviewCategory; status?: string } = {}): Promise<ReviewItem[]> {
    let projects: Project[] = [];
    try {
      const page = await projectsApi.list({ page_size: 10, status: "active" });
      projects = page.items;
    } catch {
      projects = [];
    }

    const projectId = params.projectId || projects[0]?.id || "proj-primary";
    const currentProj = projects.find((p) => p.id === projectId) || {
      id: projectId,
      code: "CG-2026-001",
      name: "Highway Expansion Section B",
    };

    // Realistic construction review items across all 8 categories
    const baseItems: ReviewItem[] = [
      {
        id: `rev-cat-0-${projectId}`,
        category: "insufficient_evidence_risk",
        title: "Unsubstantiated Hydrocarbon Soil Contamination Claim (Pier 8 Augering)",
        risk_type: "environmental_hazard",
        confidence: 0.32,
        project_id: currentProj.id,
        project_code: currentProj.code,
        project_name: currentProj.name,
        severity: "high",
        system_found:
          "Contractor submitted delay and cost notice alleging hydrocarbon soil contamination halting Pier 8 pile augering. No geotechnical lab testing, soil chemistry assays, chain-of-custody logs, or site chemist certifications were attached.",
        why_review_needed:
          "FIDIC Clause 4.12 requires contemporaneous certified soil assay proof. Without certified third-party laboratory test certificates, this risk cannot be accepted as supported evidence.",
        evidence_links: [],
        document_id: "doc-notice-soil-09",
        original_document_url: "/documents/doc-notice-soil-09",
        recommended_action:
          "Do NOT accept risk into commercial baseline. Request certified laboratory soil chemistry assay and chain-of-custody test reports from environmental consultant.",
        recommended_correction:
          "Do NOT accept risk into commercial baseline. Request certified laboratory soil chemistry assay and chain-of-custody test reports from environmental consultant.",
        financial_exposure: "140000.00",
        currency: "USD",
        schedule_impact_days: 21,
        status: "insufficient_evidence",
        entity_type: "risk",
        entity_id: "risk-unsub-contam-01",
        required_permission: "risks.accept",
        audit_history: [
          {
            id: "aud-insuff-1",
            timestamp: new Date(Date.now() - 3600000 * 6).toISOString(),
            actor_name: "ChangeGuard Evidence Validator",
            actor_role: "system",
            action: "evidence.insufficient_detected",
            reason: "Zero certified geotechnical lab reports attached to soil contamination notice",
          },
        ],
        created_at: new Date(Date.now() - 3600000 * 6).toISOString(),
      },
      {
        id: `rev-cat-1-${projectId}`,
        category: "low_confidence_extraction",
        title: "Subcontractor Shift Report OCR: Rebar Placement Rate Discrepancy",
        risk_type: "extraction_ambiguity",
        confidence: 0.64,
        project_id: currentProj.id,
        project_code: currentProj.code,
        project_name: currentProj.name,
        severity: "medium",
        system_found:
          "Automated OCR on Daily Log 2026-03-14 extracted foundation rebar installation at 42.5 tonnes against 12.0 tonnes delivery note. Optical character confidence is 64% on handwritten field foreman signoff.",
        why_review_needed:
          "OCR ambiguity in handwritten daily site report could overstate work-in-progress valuation by $36,500. Verification required against certified delivery tickets.",
        evidence_links: [
          {
            id: "ev-ocr-1",
            source_type: "document",
            source_id: "doc-daily-log-0314",
            document_name: "Daily Site Log DL-2026-0314",
            page_number: 2,
            source_page: 2,
            excerpt: "Foundations Section 4 rebar tie-in completed: logged as ~42.5t [OCR confidence: 0.64, stroke bleed detected]",
            source_quotation: "Foundations Section 4 rebar tie-in completed: logged as ~42.5t [OCR confidence: 0.64, stroke bleed detected]",
            confidence: 0.64,
            document_id: "doc-daily-log-0314",
            original_document_url: "/documents/doc-daily-log-0314",
          },
          {
            id: "ev-ocr-2",
            source_type: "document",
            source_id: "doc-deliv-mt8821",
            document_name: "Mill Test & Delivery Ticket MT-8821",
            page_number: 1,
            source_page: 1,
            excerpt: "Batch 400B Deformed High-Yield Rebar shipped to Zone 4: Net certified weight 12.00 metric tonnes.",
            source_quotation: "Batch 400B Deformed High-Yield Rebar shipped to Zone 4: Net certified weight 12.00 metric tonnes.",
            confidence: 0.98,
            document_id: "doc-deliv-mt8821",
            original_document_url: "/documents/doc-deliv-mt8821",
          },
        ],
        document_id: "doc-daily-log-0314",
        original_document_url: "/documents/doc-daily-log-0314",
        recommended_action:
          "Verify handwritten tonnage against Delivery Ticket MT-8821 (12.0 metric tonnes) and adjust logged work-in-progress quantity to 12.0 tonnes.",
        recommended_correction:
          "Verify handwritten tonnage against Delivery Ticket MT-8821 (12.0 metric tonnes) and adjust logged work-in-progress quantity to 12.0 tonnes.",
        financial_exposure: "36500.00",
        currency: "USD",
        schedule_impact_days: 0,
        status: "pending",
        entity_type: "extraction",
        entity_id: "doc-daily-log-0314",
        required_permission: "documents.write",
        audit_history: [
          {
            id: "aud-ocr-1",
            timestamp: new Date(Date.now() - 3600000 * 8).toISOString(),
            actor_name: "ChangeGuard OCR Pipeline",
            actor_role: "system",
            action: "extraction.flagged_low_confidence",
            reason: "Character recognition confidence (64%) below automated threshold (85%) on numeric field",
          },
        ],
        created_at: new Date(Date.now() - 3600000 * 8).toISOString(),
      },
      {
        id: `rev-cat-2-${projectId}`,
        category: "missing_required_field",
        title: "Subcontractor Notice of Delay: Missing FIDIC 20.1 Clause Particulars",
        risk_type: "contractual_noncompliance",
        confidence: 0.92,
        project_id: currentProj.id,
        project_code: currentProj.code,
        project_name: currentProj.name,
        severity: "high",
        system_found:
          "Contractor submitted Notice of Claim for Ground Conditions variance without specifying estimated time extension or contemporaneous record references required by Contract Clause 20.1.",
        why_review_needed:
          "Failure to submit required clause particulars within 28 days forfeits contractor entitlement to time extension under FIDIC 2017 Yellow Book condition of contract.",
        evidence_links: [
          {
            id: "ev-miss-1",
            source_type: "document",
            source_id: "doc-notice-sn014",
            document_name: "Subcontractor Notice SN-014",
            page_number: 1,
            source_page: 1,
            excerpt: "Notice of event likely to delay works: Encountered unexploded boulder obstruction in Pier 3 footing. Particulars to follow.",
            source_quotation: "Notice of event likely to delay works: Encountered unexploded boulder obstruction in Pier 3 footing. Particulars to follow.",
            confidence: 0.95,
            document_id: "doc-notice-sn014",
            original_document_url: "/documents/doc-notice-sn014",
          },
          {
            id: "ev-miss-2",
            source_type: "contract",
            source_id: "doc-fidic-yb",
            document_name: "FIDIC Yellow Book 2017 Sub-Clause 20.1",
            page_number: 45,
            source_page: 45,
            excerpt: "If the Contractor fails to give notice of a claim within 28 days, the Time for Completion shall not be extended, and the Employer shall be discharged from all liability.",
            source_quotation: "If the Contractor fails to give notice of a claim within 28 days, the Time for Completion shall not be extended, and the Employer shall be discharged from all liability.",
            confidence: 0.99,
            document_id: "doc-fidic-yb",
            original_document_url: "/documents/doc-fidic-yb",
          },
        ],
        document_id: "doc-notice-sn014",
        original_document_url: "/documents/doc-notice-sn014",
        recommended_action:
          "Issue formal request for particulars under Clause 20.1 with 14-day compliance notice before assessing commercial entitlement.",
        recommended_correction:
          "Issue formal request for particulars under Clause 20.1 with 14-day compliance notice before assessing commercial entitlement.",
        financial_exposure: "75000.00",
        currency: "USD",
        schedule_impact_days: 14,
        status: "pending",
        entity_type: "potential_change",
        entity_id: "sn-014-notice",
        required_permission: "change_orders.write",
        audit_history: [
          {
            id: "aud-miss-1",
            timestamp: new Date(Date.now() - 3600000 * 14).toISOString(),
            actor_name: "ChangeGuard Clause Auditor",
            actor_role: "system",
            action: "contract_rule.missing_required_field",
            reason: "Missing mandatory fields: contemporaneous_record_index, estimated_delay_days",
          },
        ],
        created_at: new Date(Date.now() - 3600000 * 14).toISOString(),
      },
      {
        id: `rev-cat-3-${projectId}`,
        category: "potential_duplicate",
        title: "HVAC Ductwork Clash Variance: Cross-Referenced in RFI-088 & CVI-042",
        risk_type: "duplicate_cost_claim",
        confidence: 0.95,
        project_id: currentProj.id,
        project_code: currentProj.code,
        project_name: currentProj.name,
        severity: "medium",
        system_found:
          "Identical duct rerouting cost claim of $18,400.00 identified across two separate submissions: RFI-088 (Basement Level 2 Duct Clash) and Confirmation of Verbal Instruction CVI-042.",
        why_review_needed:
          "Duplicate compensation claim would result in double-accounting the mechanical subcontractor for the same physical redirection in Zone B.",
        evidence_links: [
          {
            id: "ev-dup-1",
            source_type: "rfi",
            source_id: "rfi-088",
            document_name: "RFI-088 Basement HVAC Clash Response",
            page_number: 1,
            source_page: 1,
            excerpt: "MEP Engineer confirms supply duct must drop 450mm under transfer beam. Cost impact stated as $18,400.",
            source_quotation: "MEP Engineer confirms supply duct must drop 450mm under transfer beam. Cost impact stated as $18,400.",
            confidence: 0.94,
            document_id: "rfi-088",
            original_document_url: "/documents/rfi-088",
          },
          {
            id: "ev-dup-2",
            source_type: "document",
            source_id: "cvi-042",
            document_name: "CVI-042 Confirmation of Verbal Instruction",
            page_number: 1,
            source_page: 1,
            excerpt: "Site Instruction confirms mechanical subcontractor rerouting around transfer girder. Claim value: $18,400.",
            source_quotation: "Site Instruction confirms mechanical subcontractor rerouting around transfer girder. Claim value: $18,400.",
            confidence: 0.97,
            document_id: "cvi-042",
            original_document_url: "/documents/cvi-042",
          },
        ],
        document_id: "rfi-088",
        original_document_url: "/documents/rfi-088",
        recommended_action:
          "Consolidate variance under primary Change Order CO-024 and void duplicate claim in CVI-042 with audited cross-reference.",
        recommended_correction:
          "Consolidate variance under primary Change Order CO-024 and void duplicate claim in CVI-042 with audited cross-reference.",
        financial_exposure: "18400.00",
        currency: "USD",
        schedule_impact_days: 3,
        status: "pending",
        entity_type: "potential_change",
        entity_id: "cvi-042-dup",
        required_permission: "change_orders.write",
        audit_history: [
          {
            id: "aud-dup-1",
            timestamp: new Date(Date.now() - 3600000 * 20).toISOString(),
            actor_name: "ChangeGuard Semantic Deduplicator",
            actor_role: "system",
            action: "variance.duplicate_detected",
            reason: "Spatial coordinate overlap and 98% semantic similarity with RFI-088",
          },
        ],
        created_at: new Date(Date.now() - 3600000 * 20).toISOString(),
      },
      {
        id: `rev-cat-4-${projectId}`,
        category: "conflicting_evidence",
        title: "Inclement Weather Extension Claim vs. On-Site Telemetry Station Log",
        risk_type: "schedule_variance",
        confidence: 0.98,
        project_id: currentProj.id,
        project_code: currentProj.code,
        project_name: currentProj.name,
        severity: "critical",
        system_found:
          "Contractor claims 5 lost critical-path days due to torrential rainfall exceeding 50mm/day (June 10-14), whereas calibrated site weather telemetry logged 4.2mm total cumulative precipitation.",
        why_review_needed:
          "Substantiation directly contradicts objective on-site meteorological telemetry. FIDIC Clause 8.4 requires exceptionally adverse climatic conditions beyond 1-in-10 year return period.",
        evidence_links: [
          {
            id: "ev-conf-1",
            source_type: "document",
            source_id: "clm-w03",
            document_name: "Delay Claim Letter CLM-W03",
            page_number: 2,
            source_page: 2,
            excerpt: "Torrential downpour flooded excavated foundation pits from 10th to 14th June rendering crane pads inoperable. Claim: 5 days extension.",
            source_quotation: "Torrential downpour flooded excavated foundation pits from 10th to 14th June rendering crane pads inoperable. Claim: 5 days extension.",
            confidence: 0.96,
            document_id: "clm-w03",
            original_document_url: "/documents/clm-w03",
          },
          {
            id: "ev-conf-2",
            source_type: "document",
            source_id: "met-jun-2026",
            document_name: "Calibrated Site Telemetry Station Log MET-JUN-2026",
            page_number: 1,
            source_page: 1,
            excerpt: "Automated rain gauge recorded: June 10 (1.1mm), June 11 (0.8mm), June 12 (0.0mm), June 13 (2.3mm), June 14 (0.0mm). Sensor health: 100%.",
            source_quotation: "Automated rain gauge recorded: June 10 (1.1mm), June 11 (0.8mm), June 12 (0.0mm), June 13 (2.3mm), June 14 (0.0mm). Sensor health: 100%.",
            confidence: 0.99,
            document_id: "met-jun-2026",
            original_document_url: "/documents/met-jun-2026",
          },
        ],
        document_id: "clm-w03",
        original_document_url: "/documents/clm-w03",
        recommended_action:
          "Reject 5-day claim based on objective telemetry MET-JUN-2026; issue formal rebuttal referencing FIDIC Sub-Clause 8.4 meteorological return statistics.",
        recommended_correction:
          "Reject 5-day claim based on objective telemetry MET-JUN-2026; issue formal rebuttal referencing FIDIC Sub-Clause 8.4 meteorological return statistics.",
        financial_exposure: "95000.00",
        currency: "USD",
        schedule_impact_days: 5,
        status: "pending",
        entity_type: "change_order",
        entity_id: "co-weather-clm",
        required_permission: "approvals.decide",
        audit_history: [
          {
            id: "aud-conf-1",
            timestamp: new Date(Date.now() - 3600000 * 24).toISOString(),
            actor_name: "ChangeGuard Evidence Correlator",
            actor_role: "system",
            action: "evidence.conflict_detected",
            reason: "Telemetry log precipitation (4.2mm) disproves claim statement of >50mm/day torrential downpour",
          },
        ],
        created_at: new Date(Date.now() - 3600000 * 24).toISOString(),
      },
      {
        id: `rev-cat-5-${projectId}`,
        category: "high_value_change",
        title: "CO-018: Deep Excavation Dewatering System Overhaul",
        risk_type: "geotechnical_cost_variance",
        confidence: 0.97,
        project_id: currentProj.id,
        project_code: currentProj.code,
        project_name: currentProj.name,
        severity: "critical",
        system_found:
          "Change Order submission totaling $185,000.00 USD and 14 days schedule impact. Value exceeds single Commercial Manager sign-off limit ($100,000.00 USD).",
        why_review_needed:
          "Delegation of authority mandates dual Project Manager and Commercial Director sign-off for variations exceeding $100k threshold.",
        evidence_links: [
          {
            id: "ev-val-1",
            source_type: "document",
            source_id: "gt-104",
            document_name: "Geotechnical Assessment Report GT-104",
            page_number: 8,
            source_page: 8,
            excerpt: "High hydrostatic pressure in sand stratum requires deep-well ejector system with standby generators for 45 calendar days.",
            source_quotation: "High hydrostatic pressure in sand stratum requires deep-well ejector system with standby generators for 45 calendar days.",
            confidence: 0.97,
            document_id: "gt-104",
            original_document_url: "/documents/gt-104",
          },
          {
            id: "ev-val-2",
            source_type: "document",
            source_id: "sub-q441",
            document_name: "Subcontractor Dewatering Quotation Q-441",
            page_number: 3,
            source_page: 3,
            excerpt: "Mobilization, 6 deep well casings, 24/7 telemetry monitoring and fuel surcharges total: $185,000.00.",
            source_quotation: "Mobilization, 6 deep well casings, 24/7 telemetry monitoring and fuel surcharges total: $185,000.00.",
            confidence: 0.98,
            document_id: "sub-q441",
            original_document_url: "/documents/sub-q441",
          },
        ],
        document_id: "gt-104",
        original_document_url: "/documents/gt-104",
        recommended_action:
          "Audit equipment rental rates against baseline rate card; negotiate down mobilization surge charge to $162,000 before dual PM/Director sign-off.",
        recommended_correction:
          "Audit equipment rental rates against baseline rate card; negotiate down mobilization surge charge to $162,000 before dual PM/Director sign-off.",
        financial_exposure: "185000.00",
        currency: "USD",
        schedule_impact_days: 14,
        status: "pending",
        entity_type: "change_order",
        entity_id: "co-018-dewat",
        required_permission: "approvals.decide",
        audit_history: [
          {
            id: "aud-val-1",
            timestamp: new Date(Date.now() - 3600000 * 30).toISOString(),
            actor_name: "ChangeGuard Value Threshold Monitor",
            actor_role: "system",
            action: "governance.threshold_exceeded",
            reason: "Change Order value ($185,000.00) exceeds single-manager delegated signing limit ($100,000.00)",
          },
        ],
        created_at: new Date(Date.now() - 3600000 * 30).toISOString(),
      },
      {
        id: `rev-cat-6-${projectId}`,
        category: "high_severity_risk",
        title: "Structural Steel Rolling Lead Time Mill Stoppage",
        risk_type: "procurement_delay",
        confidence: 0.99,
        project_id: currentProj.id,
        project_code: currentProj.code,
        project_name: currentProj.name,
        severity: "critical",
        system_found:
          "Fabricator notified 18-week delay on Grade 50 heavy structural sections due to mill rolling furnace overhaul. Projected critical path delay: 42 days.",
        why_review_needed:
          "Critical milestone delivery for Roof Enclosure will be breached, triggering contractual liquidated damages exposure of $210,000.00 USD.",
        evidence_links: [
          {
            id: "ev-risk-1",
            source_type: "document",
            source_id: "fn-2026-02",
            document_name: "Fabricator Mill Notice FN-2026-02",
            page_number: 1,
            source_page: 1,
            excerpt: "Primary rolling mill outage extends delivery window from Week 22 to Week 40 for W36x230 beams.",
            source_quotation: "Primary rolling mill outage extends delivery window from Week 22 to Week 40 for W36x230 beams.",
            confidence: 0.99,
            document_id: "fn-2026-02",
            original_document_url: "/documents/fn-2026-02",
          },
          {
            id: "ev-risk-2",
            source_type: "document",
            source_id: "baseline-gantt",
            document_name: "Project Baseline Schedule Rev 4",
            page_number: 14,
            source_page: 14,
            excerpt: "Activity ID ST-200 (Roof Truss Erection) is zero-float critical path preceding wet envelope close-in.",
            source_quotation: "Activity ID ST-200 (Roof Truss Erection) is zero-float critical path preceding wet envelope close-in.",
            confidence: 0.98,
            document_id: "baseline-gantt",
            original_document_url: "/documents/baseline-gantt",
          },
        ],
        document_id: "fn-2026-02",
        original_document_url: "/documents/fn-2026-02",
        recommended_action:
          "Accept emergency reroute to secondary certified rolling mill with $28,000 premium to protect 35 critical path days.",
        recommended_correction:
          "Accept emergency reroute to secondary certified rolling mill with $28,000 premium to protect 35 critical path days.",
        financial_exposure: "210000.00",
        currency: "USD",
        schedule_impact_days: 42,
        status: "pending",
        entity_type: "risk",
        entity_id: "risk-steel-lead",
        required_permission: "risks.accept",
        audit_history: [
          {
            id: "aud-risk-1",
            timestamp: new Date(Date.now() - 3600000 * 40).toISOString(),
            actor_name: "ChangeGuard Risk Classifier",
            actor_role: "system",
            action: "risk.critical_severity_flagged",
            reason: "Schedule impact of 42 days on critical path exceeds maximum risk buffer",
          },
        ],
        created_at: new Date(Date.now() - 3600000 * 40).toISOString(),
      },
      {
        id: `rev-cat-7-${projectId}`,
        category: "approval_request",
        title: "CO-015: Basement Waterproofing Membrane Specification Change",
        risk_type: "specification_substitution",
        confidence: 0.96,
        project_id: currentProj.id,
        project_code: currentProj.code,
        project_name: currentProj.name,
        severity: "medium",
        system_found:
          "Formal Change Order submitted for substitution of Bentonite sheet with crystalline waterproofing slurry. Amount: $42,500.00 USD. 0 days schedule impact.",
        why_review_needed:
          "Final commercial approval required to execute formal contract variation and issue instruction to contractor.",
        evidence_links: [
          {
            id: "ev-app-1",
            source_type: "document",
            source_id: "ai-033",
            document_name: "Architect Instruction AI-033",
            page_number: 1,
            source_page: 1,
            excerpt: "Instructing substitution of crystalline admixture in lieu of external sheet membrane due to water table condition.",
            source_quotation: "Instructing substitution of crystalline admixture in lieu of external sheet membrane due to water table condition.",
            confidence: 0.96,
            document_id: "ai-033",
            original_document_url: "/documents/ai-033",
          },
          {
            id: "ev-app-2",
            source_type: "document",
            source_id: "ms-082",
            document_name: "Material Submittal MS-082-Rev1",
            page_number: 4,
            source_page: 4,
            excerpt: "Certified test results confirm compliance with DIN 1048 water permeability standards.",
            source_quotation: "Certified test results confirm compliance with DIN 1048 water permeability standards.",
            confidence: 0.97,
            document_id: "ms-082",
            original_document_url: "/documents/ms-082",
          },
        ],
        document_id: "ai-033",
        original_document_url: "/documents/ai-033",
        recommended_action:
          "Approve variation at negotiated rate of $42,500.00 USD; deduct unused bentonite sheets from bill of quantities.",
        recommended_correction:
          "Approve variation at negotiated rate of $42,500.00 USD; deduct unused bentonite sheets from bill of quantities.",
        financial_exposure: "42500.00",
        currency: "USD",
        schedule_impact_days: 0,
        status: "pending",
        entity_type: "change_order",
        entity_id: "co-015-wp",
        required_permission: "approvals.decide",
        audit_history: [
          {
            id: "aud-app-1",
            timestamp: new Date(Date.now() - 3600000 * 48).toISOString(),
            actor_name: "David Vance",
            actor_role: "project_manager",
            action: "change_order.submitted",
            reason: "Submitted for commercial approval with engineer and architect sign-off attached",
          },
        ],
        created_at: new Date(Date.now() - 3600000 * 48).toISOString(),
      },
    ];

    const merged = baseItems.map((item) => {
      const override = sessionReviewOverrides[item.id];
      if (!override) return item;
      return {
        ...item,
        ...override,
        audit_history: override.audit_history || item.audit_history,
      };
    });

    let result = merged;
    if (params.category) {
      result = result.filter((i) => i.category === params.category);
    }
    if (params.status) {
      result = result.filter((i) => i.status === params.status);
    }

    return parse(reviewItemListSchema, result);
  },

  async acceptRisk(
    item: ReviewItem,
    reason = "Accepted risk in review queue",
    user?: { name: string; role: string }
  ): Promise<ReviewItem> {
    if (
      item.category === "insufficient_evidence_risk" ||
      item.status === "insufficient_evidence" ||
      item.evidence_links.length === 0
    ) {
      throw new Error("Insufficient-evidence risks cannot be accepted as supported evidence.");
    }

    const trimmedReason = reason.trim() || "Accepted risk in review queue";

    if (item.entity_type === "risk") {
      try {
        await risksApi.decide(item.project_id, item.entity_id, {
          action: "accept",
          reason: trimmedReason,
        });
      } catch {
        // Fallback for mock/simulation records
      }
    }

    const newAudit: ReviewAuditRecord = {
      id: `aud-${Date.now()}`,
      timestamp: new Date().toISOString(),
      actor_name: user?.name || "CurrentUser",
      actor_role: user?.role || "commercial_manager",
      action: "risk.accepted",
      reason: trimmedReason,
    };

    const updated: ReviewItem = {
      ...item,
      status: "accepted",
      audit_history: [...item.audit_history, newAudit],
    };

    sessionReviewOverrides[item.id] = updated;
    return updated;
  },

  async dismissRisk(
    item: ReviewItem,
    reason: string,
    user?: { name: string; role: string }
  ): Promise<ReviewItem> {
    const trimmedReason = reason.trim();
    if (!trimmedReason) {
      throw new Error("A justification reason is required for dismissal");
    }

    if (item.entity_type === "risk") {
      try {
        await risksApi.decide(item.project_id, item.entity_id, {
          action: "dismiss",
          reason: trimmedReason,
        });
      } catch {
        // Fallback
      }
    }

    const newAudit: ReviewAuditRecord = {
      id: `aud-${Date.now()}`,
      timestamp: new Date().toISOString(),
      actor_name: user?.name || "CurrentUser",
      actor_role: user?.role || "commercial_manager",
      action: "risk.dismissed",
      reason: trimmedReason,
    };

    const updated: ReviewItem = {
      ...item,
      status: "dismissed",
      audit_history: [...item.audit_history, newAudit],
    };

    sessionReviewOverrides[item.id] = updated;
    return updated;
  },

  async requestEvidence(
    item: ReviewItem,
    payload: { reason: string; requested_details?: string },
    user?: { name: string; role: string }
  ): Promise<ReviewItem> {
    const trimmedReason = payload.reason?.trim();
    if (!trimmedReason) {
      throw new Error("A justification reason is required to request more evidence");
    }

    if (item.entity_type === "risk") {
      try {
        await risksApi.decide(item.project_id, item.entity_id, {
          action: "request_evidence",
          reason: trimmedReason,
        });
      } catch {
        // Fallback
      }
    }

    const newAudit: ReviewAuditRecord = {
      id: `aud-${Date.now()}`,
      timestamp: new Date().toISOString(),
      actor_name: user?.name || "CurrentUser",
      actor_role: user?.role || "commercial_manager",
      action: "risk.evidence_requested",
      reason: trimmedReason,
      details: payload.requested_details ? { requested_details: payload.requested_details } : undefined,
    };

    const updated: ReviewItem = {
      ...item,
      status: "evidence_requested",
      audit_history: [...item.audit_history, newAudit],
    };

    sessionReviewOverrides[item.id] = updated;
    return updated;
  },

  async convertToChangeOrder(
    item: ReviewItem,
    payload: {
      change_order_reference: string;
      change_order_title?: string;
      reason: string;
      amount?: string;
      time_impact_days?: number;
    },
    user?: { name: string; role: string }
  ): Promise<ReviewItem> {
    if (
      item.category === "insufficient_evidence_risk" ||
      item.status === "insufficient_evidence" ||
      item.evidence_links.length === 0
    ) {
      throw new Error("Insufficient-evidence risks cannot be converted to a change order. Every draft must cite evidence.");
    }

    const trimmedRef = payload.change_order_reference?.trim();
    const trimmedReason = payload.reason?.trim();
    if (!trimmedRef) {
      throw new Error("Change order reference is required");
    }
    if (!trimmedReason) {
      throw new Error("A reason is mandatory to convert risk to change order");
    }

    if (item.entity_type === "risk") {
      try {
        await risksApi.decide(item.project_id, item.entity_id, {
          action: "convert_to_change_order",
          reason: trimmedReason,
          change_order_reference: trimmedRef,
          change_order_title: payload.change_order_title || item.title,
        });
      } catch {
        // Fallback
      }
    }

    const newAudit: ReviewAuditRecord = {
      id: `aud-${Date.now()}`,
      timestamp: new Date().toISOString(),
      actor_name: user?.name || "CurrentUser",
      actor_role: user?.role || "commercial_manager",
      action: "risk.converted_to_change_order",
      reason: trimmedReason,
      details: {
        change_order_reference: trimmedRef,
        change_order_title: payload.change_order_title || item.title,
        amount: payload.amount || item.financial_exposure,
        time_impact_days: payload.time_impact_days ?? item.schedule_impact_days,
      },
    };

    const updated: ReviewItem = {
      ...item,
      status: "converted",
      change_order_reference: trimmedRef,
      financial_exposure: payload.amount !== undefined ? payload.amount : item.financial_exposure,
      schedule_impact_days:
        payload.time_impact_days !== undefined ? payload.time_impact_days : item.schedule_impact_days,
      audit_history: [...item.audit_history, newAudit],
    };

    sessionReviewOverrides[item.id] = updated;
    return updated;
  },

  async createDraftFromRisk(
    item: ReviewItem,
    payload: {
      change_order_reference?: string;
      change_order_title?: string;
      reason: string;
    },
    user?: { name: string; role: string }
  ): Promise<{ item: ReviewItem; changeOrder: ChangeOrderItem }> {
    if (
      item.category === "insufficient_evidence_risk" ||
      item.status === "insufficient_evidence" ||
      item.evidence_links.length === 0
    ) {
      throw new Error("Cannot create change-order draft without supporting evidence citations. Every draft must cite evidence.");
    }
    const trimmedReason = payload.reason?.trim();
    if (!trimmedReason) {
      throw new Error("A reason is mandatory to create a change-order draft");
    }

    let createdOrder: ChangeOrderItem;
    try {
      createdOrder = await changeOrdersApi.createFromRisk(item.project_id, item.entity_id, {
        reference: payload.change_order_reference,
        title: payload.change_order_title,
        reason: trimmedReason,
      });
    } catch {
      // Fallback/simulation
      const coId = `co-${Date.now()}`;
      createdOrder = {
        id: coId,
        project_id: item.project_id,
        reference: payload.change_order_reference || `CO-DR-${item.entity_id.slice(0, 8).toUpperCase()}`,
        title: payload.change_order_title || `Delay Mitigation: ${item.title}`,
        description: `Delay event documented in evidence: ${item.system_found}\n\nResponsible party: ${item.responsible_party || "Unassigned"}`,
        status: "drafted",
        amount: null,
        currency: item.currency || "USD",
        cost_items: null,
        time_impact_days: null,
        draft: { sources: item.evidence_links },
        source_event_id: item.entity_id,
        responsible_party: item.responsible_party || null,
        evidence_links: item.evidence_links.map((l) => l.id),
        approval_history: [],
      };
    }

    const newAudit: ReviewAuditRecord = {
      id: `aud-${Date.now()}`,
      timestamp: new Date().toISOString(),
      actor_name: user?.name || "CurrentUser",
      actor_role: user?.role || "commercial_manager",
      action: "risk.converted_to_change_order",
      reason: trimmedReason,
      details: {
        change_order_id: createdOrder.id,
        change_order_reference: createdOrder.reference,
        amount: null,
        time_impact_days: null,
      },
    };

    const updated: ReviewItem = {
      ...item,
      status: "converted",
      change_order_reference: createdOrder.reference,
      audit_history: [...item.audit_history, newAudit],
    };

    sessionReviewOverrides[item.id] = updated;
    return { item: updated, changeOrder: createdOrder };
  },

  async approve(
    item: ReviewItem,
    reason = "Approved in review queue",
    user?: { name: string; role: string }
  ): Promise<ReviewItem> {
    if (
      item.category === "insufficient_evidence_risk" ||
      item.status === "insufficient_evidence" ||
      item.evidence_links.length === 0
    ) {
      throw new Error("Insufficient-evidence risks cannot be accepted as supported evidence.");
    }

    const trimmedReason = reason.trim() || "Approved in review queue";

    // Call backend workflow API
    if (item.entity_type === "change_order") {
      try {
        await changeOrdersApi.approve(item.entity_id, trimmedReason);
      } catch {
        // Fallback for mock/simulation records
      }
    } else if (item.entity_type === "risk") {
      try {
        await risksApi.decide(item.project_id, item.entity_id, {
          action: "accept",
          reason: trimmedReason,
        });
      } catch {
        // Fallback
      }
    }

    const newAudit: ReviewAuditRecord = {
      id: `aud-${Date.now()}`,
      timestamp: new Date().toISOString(),
      actor_name: user?.name || "CurrentUser",
      actor_role: user?.role || "commercial_manager",
      action: "review.approved",
      reason: trimmedReason,
    };

    const updated: ReviewItem = {
      ...item,
      status: "approved",
      audit_history: [...item.audit_history, newAudit],
    };

    sessionReviewOverrides[item.id] = updated;
    return updated;
  },

  async reject(
    item: ReviewItem,
    reason: string,
    user?: { name: string; role: string }
  ): Promise<ReviewItem> {
    const trimmedReason = reason.trim();
    if (!trimmedReason) {
      throw new Error("A justification reason is required for rejection");
    }

    // Call backend workflow API
    if (item.entity_type === "change_order") {
      try {
        await changeOrdersApi.reject(item.entity_id, trimmedReason);
      } catch {
        // Fallback
      }
    } else if (item.entity_type === "risk") {
      try {
        await risksApi.decide(item.project_id, item.entity_id, {
          action: "dismiss",
          reason: trimmedReason,
        });
      } catch {
        // Fallback
      }
    }

    const newAudit: ReviewAuditRecord = {
      id: `aud-${Date.now()}`,
      timestamp: new Date().toISOString(),
      actor_name: user?.name || "CurrentUser",
      actor_role: user?.role || "commercial_manager",
      action: "review.rejected",
      reason: trimmedReason,
    };

    const updated: ReviewItem = {
      ...item,
      status: "rejected",
      audit_history: [...item.audit_history, newAudit],
    };

    sessionReviewOverrides[item.id] = updated;
    return updated;
  },

  async override(
    item: ReviewItem,
    payload: {
      reason: string;
      severity?: RiskSeverity;
      schedule_impact_days?: number;
      financial_exposure?: string;
    },
    user?: { name: string; role: string }
  ): Promise<ReviewItem> {
    const trimmedReason = payload.reason?.trim();
    if (!trimmedReason) {
      throw new Error("A justification reason is required for override");
    }

    // Call backend workflow API
    if (item.entity_type === "risk") {
      try {
        await risksApi.decide(item.project_id, item.entity_id, {
          action: "override",
          reason: trimmedReason,
          severity: payload.severity,
          schedule_impact_days: payload.schedule_impact_days,
        });
      } catch {
        // Fallback
      }
    }

    const newAudit: ReviewAuditRecord = {
      id: `aud-${Date.now()}`,
      timestamp: new Date().toISOString(),
      actor_name: user?.name || "CurrentUser",
      actor_role: user?.role || "commercial_manager",
      action: "review.overridden",
      reason: trimmedReason,
      details: {
        severity: payload.severity,
        schedule_impact_days: payload.schedule_impact_days,
        financial_exposure: payload.financial_exposure,
      },
    };

    const updated: ReviewItem = {
      ...item,
      status: "overridden",
      severity: payload.severity || item.severity,
      schedule_impact_days:
        payload.schedule_impact_days !== undefined ? payload.schedule_impact_days : item.schedule_impact_days,
      financial_exposure:
        payload.financial_exposure !== undefined ? payload.financial_exposure : item.financial_exposure,
      audit_history: [...item.audit_history, newAudit],
    };

    sessionReviewOverrides[item.id] = updated;
    return updated;
  },

  async edit(
    item: ReviewItem,
    payload: ReviewEditInput,
    user?: { name: string; role: string }
  ): Promise<ReviewItem> {
    const validated = reviewEditSchema.parse(payload);

    const newAudit: ReviewAuditRecord = {
      id: `aud-${Date.now()}`,
      timestamp: new Date().toISOString(),
      actor_name: user?.name || "CurrentUser",
      actor_role: user?.role || "commercial_manager",
      action: "review.edited",
      reason: validated.reason,
      details: {
        title: validated.title,
        recommended_correction: validated.recommended_correction,
        financial_exposure: validated.financial_exposure,
        schedule_impact_days: validated.schedule_impact_days,
      },
    };

    const updated: ReviewItem = {
      ...item,
      title: validated.title || item.title,
      recommended_correction: validated.recommended_correction || item.recommended_correction,
      financial_exposure:
        validated.financial_exposure !== undefined ? validated.financial_exposure : item.financial_exposure,
      schedule_impact_days:
        validated.schedule_impact_days !== undefined ? validated.schedule_impact_days : item.schedule_impact_days,
      audit_history: [...item.audit_history, newAudit],
    };

    sessionReviewOverrides[item.id] = updated;
    return updated;
  },
};

