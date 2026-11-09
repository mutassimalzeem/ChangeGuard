import { z } from "zod";
import { client } from "./client.ts";

export const pilotDocumentSchema = z.object({
  document_id: z.string().uuid(),
  file_name: z.string(),
  status: z.string(),
  document_type: z.string().nullable(),
  version: z.number().int(),
  extraction: z.record(z.string(), z.unknown()).nullable(),
  reviewed: z.boolean(),
  error: z.string().nullable(),
});
export const readinessSchema = z.object({
  project_name: z.string(),
  generated_at: z.string(),
  documents_total: z.number(),
  documents_processed: z.number(),
  classification_reviewed: z.number(),
  classification_accuracy: z.number().nullable(),
  extraction_confidence: z.number().nullable(),
  risks_detected: z.number(),
  missing_evidence: z.array(z.string()),
  overdue_approvals: z.number(),
  pending_exposure: z.record(z.string(), z.string()),
  unknown_exposure_count: z.number(),
  notes: z.string(),
});
export type PilotDocument = z.infer<typeof pilotDocumentSchema>;
const checklistSchema = z.object({
  steps: z.record(z.string(), z.string()),
  completed: z.array(z.string()),
});
const root = (id: string) => `/pilot/projects/${encodeURIComponent(id)}`;
export const pilotApi = {
  async list() {
    return z
      .array(z.object({ project_id: z.string().uuid(), name: z.string() }))
      .parse((await client.get("/pilot/projects")).data);
  },
  async create(name: string, currency: string) {
    return z
      .object({ project_id: z.string().uuid() })
      .parse(
        (
          await client.post("/pilot/projects", {
            name,
            currency,
            template: "construction-v1",
          })
        ).data,
      );
  },
  async documents(id: string) {
    return z
      .array(pilotDocumentSchema)
      .parse((await client.get(`${root(id)}/documents`)).data);
  },
  async checklist(id: string) {
    return checklistSchema.parse(
      (await client.get(`${root(id)}/checklist`)).data,
    );
  },
  async saveChecklist(id: string, completed: string[]) {
    await client.put(`${root(id)}/checklist`, { completed });
  },
  async report(id: string) {
    return readinessSchema.parse(
      (await client.get(`${root(id)}/readiness`)).data,
    );
  },
  async upload(id: string, file: File) {
    const form = new FormData();
    form.append("file", file);
    return z
      .object({
        items: z.array(
          z.object({
            file_name: z.string(),
            status: z.number(),
            error: z.string().optional(),
          }),
        ),
      })
      .parse(
        (await client.post(`${root(id)}/zip`, form, { timeout: 300000 })).data,
      );
  },
  async review(
    doc: PilotDocument,
    type: string,
    fields: unknown,
    reason: string,
  ) {
    await client.patch(`/pilot/documents/${doc.document_id}/review`, {
      document_type: type || undefined,
      fields,
      reason,
      version: doc.version,
    });
  },
  async pdf(id: string) {
    const response = await client.get(`${root(id)}/readiness.pdf`, {
      responseType: "blob",
    });
    const url = URL.createObjectURL(response.data);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "pilot-readiness.pdf";
    anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};
