"use client";

import { use, useState, type FormEvent } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ProtectedRoute } from "@/components/protected-route";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/form";
import { ErrorState, LoadingSkeleton } from "@/components/ui/states";
import { changeOrdersApi, documentsApi } from "@/lib/api/resources";
import { errorMessage } from "@/lib/api/errors";
import { useAuth, useRole } from "@/lib/auth";
import { changeOrderPatchSchema, type ChangeOrderItem } from "@/lib/contracts";
import { hasPermission } from "@/lib/rbac";

const emptyCost = { description: "", quantity: "", unit_rate: "" };
type CostRow = typeof emptyCost;

function DraftEditor({
  order,
  save,
}: {
  order: ChangeOrderItem;
  save: (order: ChangeOrderItem) => void;
}) {
  const [title, setTitle] = useState(order.title);
  const [description, setDescription] = useState(order.description);
  const [days, setDays] = useState(order.time_impact_days?.toString() ?? "");
  const [error, setError] = useState("");
  const [costsEdited, setCostsEdited] = useState(false);
  const [costs, setCosts] = useState<{ id: number; value: CostRow }[]>(() => {
    const result = changeOrderPatchSchema.shape.cost_items.safeParse(
      order.cost_items ?? [],
    );
    return result.success
      ? (result.data ?? []).map((value, id) => ({ id, value }))
      : [];
  });
  const [nextId, setNextId] = useState(costs.length);
  const mutation = useMutation({
    mutationFn: (payload: Parameters<typeof changeOrdersApi.patch>[1]) =>
      changeOrdersApi.patch(order.id, payload),
    onSuccess: save,
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    const parsed = changeOrderPatchSchema.safeParse({
      title: title.trim(),
      description:
        description === order.description
          ? undefined
          : description.trim() || null,
      time_impact_days: days === "" ? null : Number(days),
      cost_items: costsEdited ? costs.map(({ value }) => value) : undefined,
    });
    if (!parsed.success) {
      setError(
        "Check the title, schedule days, and cost items. Enter a description, positive quantity, and rate for each item.",
      );
      return;
    }
    setError("");
    mutation.mutate(parsed.data);
  }

  return (
    <form className="space-y-4" onSubmit={submit}>
      <h2 className="font-semibold">Edit draft</h2>
      <Field id="draft-edit-title" label="Title" required>
        <Input
          id="draft-edit-title"
          required
          maxLength={255}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
        />
      </Field>
      <Field id="draft-edit-description" label="Description">
        <textarea
          id="draft-edit-description"
          maxLength={10000}
          rows={5}
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          className="w-full rounded-lg border border-border px-3 py-2"
        />
      </Field>
      <Field
        id="draft-edit-days"
        label="Schedule impact (days)"
        className="max-w-xs"
      >
        <Input
          id="draft-edit-days"
          type="number"
          min={0}
          max={36500}
          value={days}
          onChange={(event) => setDays(event.target.value)}
        />
      </Field>
      <fieldset className="space-y-3">
        <legend className="font-medium">Cost items ({order.currency})</legend>
        {costs.map(({ id, value }) => (
          <div
            key={id}
            className="grid gap-2 rounded-lg border border-border p-3 sm:grid-cols-4"
          >
            {(["description", "quantity", "unit_rate"] as const).map((key) => (
              <Field
                key={key}
                id={`cost-${id}-${key}`}
                label={
                  {
                    description: "Description",
                    quantity: "Quantity",
                    unit_rate: "Unit rate",
                  }[key]
                }
                required
              >
                <Input
                  id={`cost-${id}-${key}`}
                  required
                  inputMode={key === "description" ? "text" : "decimal"}
                  value={value[key]}
                  onChange={(event) => {
                    const input = event.target.value;
                    setCostsEdited(true);
                    setCosts((rows) =>
                      rows.map((row) =>
                        row.id === id
                          ? { id, value: { ...row.value, [key]: input } }
                          : row,
                      ),
                    );
                  }}
                />
              </Field>
            ))}
            <Button
              className="self-end"
              variant="ghost"
              onClick={() => {
                setCostsEdited(true);
                setCosts((rows) => rows.filter((row) => row.id !== id));
              }}
            >
              Remove
            </Button>
          </div>
        ))}
        <Button
          variant="secondary"
          disabled={costs.length >= 100}
          onClick={() => {
            setCostsEdited(true);
            setCosts((rows) => [...rows, { id: nextId, value: emptyCost }]);
            setNextId(nextId + 1);
          }}
        >
          Add cost item
        </Button>
      </fieldset>
      {(error || mutation.isError) && (
        <ErrorState message={error || errorMessage(mutation.error)} />
      )}
      <Button type="submit" loading={mutation.isPending}>
        Save draft
      </Button>
    </form>
  );
}

function Workflow({
  order,
  update,
}: {
  order: ChangeOrderItem;
  update: (order: ChangeOrderItem) => void;
}) {
  const role = useRole() ?? "";
  const [editing, setEditing] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState("");
  const transition = useMutation({
    mutationFn: (action: "submit" | "approve" | "reject") => {
      if (action === "submit") return changeOrdersApi.submit(order.id, true, reason);
      return changeOrdersApi[action](order.id, reason);
    },
    onSuccess: (result) => {
      update(result);
      setNotice(`Change order ${result.status}.`);
    },
  });
  const sources = order.draft?.sources;
  const citations =
    sources && typeof sources === "object" ? Object.entries(sources) : [];
  const download = useMutation({
    mutationFn: documentsApi.downloadUrl,
    onSuccess: (url) => window.location.assign(url),
  });

  return (
    <Card>
      <CardBody className="space-y-5">
        <p className="text-sm capitalize">
          {order.reference} · {order.status.replaceAll("_", " ")}
        </p>
        <h1 className="text-xl font-semibold">{order.title}</h1>
        <p className="whitespace-pre-wrap text-sm">{order.description}</p>
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-ink-muted">Responsible party</dt>
            <dd>{order.responsible_party ?? "Unassigned"}</dd>
          </div>
          <div>
            <dt className="text-ink-muted">Source event</dt>
            <dd>{order.source_event_id ?? "Unavailable"}</dd>
          </div>
          <div>
            <dt className="text-ink-muted">Cost</dt>
            <dd>
              {order.amount === null
                ? "Pending assessment"
                : `${order.currency} ${order.amount}`}
            </dd>
          </div>
          <div>
            <dt className="text-ink-muted">Schedule impact</dt>
            <dd>
              {order.time_impact_days === null
                ? "Pending assessment"
                : `${order.time_impact_days} days`}
            </dd>
          </div>
        </dl>
        <section className="space-y-2 border-t border-border pt-4">
          <h2 className="font-semibold">Evidence package</h2>
          {citations.map(([label, source]) => {
            const documentId = source.document_id;
            return (
              <div key={label} className="text-sm">
                <p>
                  {label}
                  {source.page == null
                    ? " · Page unavailable"
                    : ` · Page ${source.page}`}
                </p>
                <blockquote className="border-l-2 border-border pl-3">
                  {source.text}
                </blockquote>
                {documentId &&
                  (source.source_type !== "document_chunk" ||
                    documentId !== source.source_id) && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => download.mutate(documentId)}
                    >
                      Open original
                    </Button>
                  )}
              </div>
            );
          })}
          {download.isError && (
            <ErrorState message={errorMessage(download.error)} />
          )}
        </section>
        {editing ? (
          <DraftEditor
            order={order}
            save={(result) => {
              update(result);
              setEditing(false);
              setConfirmed(false);
              setNotice("Draft saved.");
            }}
          />
        ) : (
          order.status === "drafted" && (
            <div className="space-y-4 border-t border-border pt-4">
              {order.draft?.converted_from_risk_id &&
              hasPermission(role, "change_orders.write") ? (
                <Button variant="secondary" onClick={() => setEditing(true)}>
                  Edit draft
                </Button>
              ) : null}
              {hasPermission(role, "change_orders.submit") &&
                order.amount !== null &&
                order.draft && (
                  <div className="flex flex-wrap items-center gap-3">
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={confirmed}
                        onChange={(event) => setConfirmed(event.target.checked)}
                      />{" "}
                      I confirm the reviewed cost items
                    </label>
                    <label>Submission reason
                      <Input value={reason} maxLength={2000} onChange={(event) => setReason(event.target.value)} />
                    </label>
                    <Button
                      disabled={!confirmed || !reason.trim()}
                      loading={transition.isPending}
                      onClick={() => transition.mutate("submit")}
                    >
                      Submit for approval
                    </Button>
                  </div>
                )}
            </div>
          )
        )}
        {order.status === "submitted" &&
          hasPermission(role, "approvals.decide") && (
            <div className="space-y-3">
              <Field
                id="order-decision-reason"
                label="Decision reason"
                required
              >
                <Input
                  id="order-decision-reason"
                  maxLength={2000}
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                />
              </Field>
              <div className="flex gap-2">
                <Button
                  disabled={!reason.trim()}
                  loading={transition.isPending}
                  onClick={() => transition.mutate("approve")}
                >
                  Approve
                </Button>
                <Button
                  variant="danger"
                  disabled={!reason.trim()}
                  loading={transition.isPending}
                  onClick={() => transition.mutate("reject")}
                >
                  Reject
                </Button>
              </div>
            </div>
          )}
        {order.approval_history.some((event) => event.reason) && (
          <section className="space-y-2">
            <h2 className="font-semibold">Approval history</h2>
            {order.approval_history.map(
              (event, index) =>
                event.reason && (
                  <p className="text-sm capitalize" key={index}>
                    {event.status} · {event.reason}
                  </p>
                ),
            )}
          </section>
        )}
        {notice && (
          <p role="status" className="text-sm">
            {notice}
          </p>
        )}
        {transition.isError && (
          <ErrorState message={errorMessage(transition.error)} />
        )}
      </CardBody>
    </Card>
  );
}

function OrderDetail({
  projectId,
  orderId,
}: {
  projectId: string;
  orderId: string;
}) {
  const queryClient = useQueryClient();
  const { session } = useAuth();
  const key = [
    "change-order",
    projectId,
    orderId,
    session?.tenantId,
    session?.userId,
    session?.roles[0],
  ];
  const order = useQuery({
    queryKey: key,
    queryFn: async () => {
      const result = await changeOrdersApi.get(orderId);
      if (result.project_id !== projectId)
        throw new Error("Change order is unavailable in this project.");
      return result;
    },
  });
  return (
    <main className="mx-auto max-w-4xl space-y-4 px-4 py-8">
      <Link
        className="text-sm text-brand underline"
        href={`/projects/${projectId}`}
      >
        Back to project
      </Link>
      {order.isPending ? (
        <LoadingSkeleton rows={3} />
      ) : order.isError ? (
        <ErrorState
          title="Could not load change order"
          message={errorMessage(order.error)}
          onRetry={() => void order.refetch()}
        />
      ) : (
        <Workflow
          key={orderId}
          order={order.data}
          update={(result) => {
            queryClient.setQueryData(key, result);
            void queryClient.invalidateQueries({
              queryKey: ["project-change-orders", projectId],
            });
          }}
        />
      )}
    </main>
  );
}

export default function ChangeOrderDetailPage({
  params,
}: {
  params: Promise<{ projectId: string; orderId: string }>;
}) {
  const { projectId, orderId } = use(params);
  return (
    <ProtectedRoute requiredPermission="financial.read">
      <OrderDetail projectId={projectId} orderId={orderId} />
    </ProtectedRoute>
  );
}
