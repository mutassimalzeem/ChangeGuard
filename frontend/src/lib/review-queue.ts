import { z } from "zod";

import { client } from "./api/client.ts";
import { risksApi } from "./api/resources.ts";
import { RISK_SEVERITIES } from "./contracts.ts";

export const REVIEW_CATEGORIES = {
  insufficient_evidence_risk: "Insufficient evidence",
  low_confidence_extraction: "Low-confidence extraction",
  missing_required_field: "Missing required fields",
  potential_duplicate: "Potential duplicate",
  conflicting_evidence: "Conflicting evidence",
  high_severity_risk: "High-severity risk",
} as const;

export type ReviewCategory = keyof typeof REVIEW_CATEGORIES;
export const REVIEW_ACTIONS = {
  accept: "Accept risk",
  dismiss: "Dismiss risk",
  request_evidence: "Request more evidence",
  convert_to_change_order: "Create change-order draft",
  override: "Override severity",
} as const;

export type ReviewAction = keyof typeof REVIEW_ACTIONS;
export const reviewQueueSchema = z.array(
  z.object({
    id: z.uuid(),
    kind: z.enum(["risk", "extraction"]),
    categories: z
      .array(
        z.custom<ReviewCategory>(
          (value) =>
            typeof value === "string" &&
            Object.hasOwn(REVIEW_CATEGORIES, value),
        ),
      )
      .min(1),
    title: z.string(),
    risk_type: z.string(),
    description: z.string().nullable(),
    confidence: z.number().min(0).max(1).nullable(),
    severity: z.enum(RISK_SEVERITIES).nullish(),
    document_id: z.uuid().nullable(),
    evidence_details: z.array(
      z.object({
        id: z.uuid(),
        source_type: z.string(),
        document_id: z.uuid().nullable(),
        document_name: z.string().nullable(),
        source_page: z.number().int().nullable(),
        source_text_snippet: z.string().nullable(),
      }),
    ),
    evidence_supported: z.boolean(),
    recommended_action: z.string().nullable(),
    status: z.string(),
    reviewable: z.boolean(),
    change_order_id: z.uuid().nullable(),
  }),
);

export type ReviewItem = z.infer<typeof reviewQueueSchema>[number];

export const reviewDecisionSchema = z
  .object({
    action: z.enum([
      "accept",
      "dismiss",
      "request_evidence",
      "convert_to_change_order",
      "override",
    ]),
    reason: z.string().trim().min(1, "Enter a reason.").max(2000),
    severity: z.enum(RISK_SEVERITIES).optional(),
  })
  .refine(
    ({ action, severity }) => action !== "override" || severity !== undefined,
    {
      message: "Select a severity.",
    },
  );

export function availableReviewActions(
  item: ReviewItem,
  canConvert: boolean,
): ReviewAction[] {
  if (!item.reviewable) return [];
  const actions: ReviewAction[] = ["dismiss", "request_evidence"];
  if (item.kind === "risk" && item.evidence_supported) {
    if (item.status !== "accepted") actions.unshift("accept");
    if (canConvert) actions.push("convert_to_change_order");
    actions.push("override");
  }
  return actions;
}

export const reviewQueueApi = {
  async list(projectId: string): Promise<ReviewItem[]> {
    const { data } = await client.get(`/projects/${projectId}/review-queue`);
    return reviewQueueSchema.parse(data);
  },

  async decide(
    projectId: string,
    item: ReviewItem,
    decision: z.input<typeof reviewDecisionSchema>,
    canConvert: boolean,
  ) {
    const payload = reviewDecisionSchema.parse(decision);
    if (!availableReviewActions(item, canConvert).includes(payload.action)) {
      throw new Error("This action is unavailable for the selected item.");
    }
    if (payload.action === "convert_to_change_order") {
      return risksApi.createChangeOrderDraft(projectId, item.id, {
        reason: payload.reason,
      });
    }
    if (item.kind === "risk") {
      await risksApi.decide(projectId, item.id, payload);
    } else {
      await client.post(
        `/projects/${projectId}/review-queue/extractions/${item.id}/decisions`,
        payload,
      );
    }
    return null;
  },
};
