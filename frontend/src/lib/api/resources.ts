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
  riskDecisionSchema,
  riskSchema,
  evidenceResultSchema,
  investigationResultSchema,
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
  type RiskDecisionInput,
  type RiskItem,
} from "@/lib/contracts";
import { client } from "./client";
import { ApiError, type FieldIssue } from "./errors";

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

  async approve(orderId: string, comments = "Approved"): Promise<ChangeOrderItem> {
    const response = await client.post(`/change-orders/${orderId}/approve`, {
      comments,
    });
    return parse(changeOrderSchema, response.data);
  },

  async reject(orderId: string, comments = "Rejected"): Promise<ChangeOrderItem> {
    const response = await client.post(`/change-orders/${orderId}/reject`, {
      comments,
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
