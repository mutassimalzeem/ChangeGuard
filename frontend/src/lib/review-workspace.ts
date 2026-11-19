import { z } from "zod";
import { client } from "./api/client.ts";
import {
  availableReviewActions,
  reviewQueueSchema,
  REVIEW_ACTIONS,
} from "./review-queue.ts";

const itemSchema = reviewQueueSchema.element.extend({
  created_at: z.string(),
  owner_id: z.uuid().nullable(),
  deadline: z.string().nullable(),
  review_state: z.string(),
  can_decide: z.boolean(),
  amount: z.string().nullable(),
  currency: z.string().nullable(),
  history: z.array(
    z.object({
      action: z.string(),
      actor_id: z.uuid().nullable(),
      at: z.string(),
      reason: z.string().nullable(),
      owner_id: z.uuid().nullable(),
    }),
  ),
});
export type WorkspaceItem = z.infer<typeof itemSchema>;
export const states = {
  actionable: "Actionable",
  all: "All states",
  review_required: "Review required",
  insufficient_evidence: "Insufficient evidence",
  evidence_requested: "Evidence requested",
  accepted: "Accepted",
  dismissed: "Dismissed",
  converted_to_change_order: "Converted to change order",
  resolved: "Resolved",
};
export const labels = {
  ...REVIEW_ACTIONS,
  assign_owner: "Assign owner",
  add_note: "Add review note",
  approve: "Approve change order",
  reject: "Reject change order",
};
export type WorkspaceAction = keyof typeof labels;
export function actionsFor(
  item: WorkspaceItem,
  canConvert: boolean,
): WorkspaceAction[] {
  if (!item.reviewable) return [];
  const actions: WorkspaceAction[] = availableReviewActions(
    item,
    canConvert,
  ).filter(
    (action) =>
      action !== "request_evidence" || item.status !== "evidence_requested",
  );
  if (item.can_decide) actions.push("approve", "reject");
  return [...actions, "assign_owner", "add_note"];
}
export const workspaceApi = {
  async page(project: string, filters: Record<string, string | number>) {
    const params = Object.fromEntries(
      Object.entries(filters).filter(([, value]) => value !== ""),
    );
    const { data } = await client.get(
      `/projects/${project}/review-queue/workspace`,
      { params },
    );
    return z
      .object({
        items: z.array(itemSchema),
        total: z.number().int().nonnegative(),
      })
      .parse(data);
  },
  async reviewers(project: string) {
    const { data } = await client.get(
      `/projects/${project}/review-queue/reviewers`,
    );
    return z
      .array(z.object({ id: z.uuid(), full_name: z.string() }))
      .parse(data);
  },
  async notes(
    project: string,
    targets: WorkspaceItem[],
    reason: string,
    key: string,
  ) {
    await client.post(`/projects/${project}/review-queue/notes`, {
      key,
      reason,
      targets: targets.map(({ kind, id }) => ({ kind, id })),
    });
  },
  async command(
    project: string,
    item: WorkspaceItem,
    payload: {
      key: string;
      action: WorkspaceAction;
      reason: string;
      owner_id?: string;
      severity?: string;
    },
  ) {
    const { data } = await client.post(
      `/projects/${project}/review-queue/${item.kind}/${item.id}/commands`,
      payload,
    );
    return z.object({ change_order_id: z.uuid().nullable() }).parse(data);
  },
};
