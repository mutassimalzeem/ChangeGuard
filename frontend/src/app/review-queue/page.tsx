"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ProtectedRoute } from "@/components/protected-route";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Field, Select } from "@/components/ui/form";
import { Modal } from "@/components/ui/modal";
import {
  EmptyState,
  ErrorState,
  LoadingSkeleton,
} from "@/components/ui/states";
import { errorMessage, isApiError } from "@/lib/api/errors";
import { documentsApi, projectsApi } from "@/lib/api/resources";
import { useAuth } from "@/lib/auth";
import { RISK_SEVERITIES } from "@/lib/contracts";
import { hasPermission } from "@/lib/rbac";
import { REVIEW_CATEGORIES } from "@/lib/review-queue";
import {
  FilterSelect,
  ReviewActionButtons,
  SourceQuotation,
} from "@/components/review-controls";
import {
  labels,
  states,
  workspaceApi,
  type WorkspaceItem,
  type WorkspaceAction,
} from "@/lib/review-workspace";

function LoadError({ error, retry }: { error: unknown; retry: () => void }) {
  if (isApiError(error) && (error.isForbidden || error.isNotFound)) {
    return (
      <ErrorState
        title="Permission denied"
        message="You do not have access to this project’s review queue."
      />
    );
  }
  return (
    <ErrorState
      title="Could not load the review queue"
      message={errorMessage(error)}
      onRetry={retry}
    />
  );
}

function DocumentLink({ id, label }: { id: string; label: string }) {
  const download = useMutation({
    mutationFn: () => documentsApi.downloadUrl(id),
    onSuccess: (url) => window.location.assign(url),
  });
  return (
    <span className="flex flex-col items-start gap-1">
      <button
        type="button"
        className="text-sm font-medium text-brand underline underline-offset-2"
        disabled={download.isPending}
        onClick={() => download.mutate()}
      >
        {download.isPending ? "Opening document…" : label}
      </button>
      {download.isError && (
        <span role="alert" className="text-sm text-danger">
          {errorMessage(download.error)}
        </span>
      )}
    </span>
  );
}

function ReviewCard({
  item,
  owner,
  canConvert,
  onAction,
}: {
  item: WorkspaceItem;
  owner: string;
  canConvert: boolean;
  onAction: (action: WorkspaceAction) => void;
}) {
  return (
    <Card>
      <CardBody className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-2">
            <h2 className="text-lg font-semibold text-ink">{item.title}</h2>
            <div className="flex flex-wrap gap-2">
              {item.categories.map((category) => (
                <Badge key={category}>{REVIEW_CATEGORIES[category]}</Badge>
              ))}
            </div>
          </div>
          <Badge className="capitalize">
            {item.status.replaceAll("_", " ")}
          </Badge>
        </div>
        <dl className="grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-ink-muted">Finding</dt>
            <dd>{item.risk_type.replaceAll("_", " ")}</dd>
          </div>
          <div>
            <dt className="text-ink-muted">Confidence</dt>
            <dd>
              {item.confidence === null
                ? "Unavailable"
                : `${Math.round(item.confidence * 100)}%`}
            </dd>
          </div>
          {Object.entries({
            "Review state": states[item.review_state as keyof typeof states],
            Severity: item.severity ?? "Unavailable",
            Owner: owner,
            Created: new Date(item.created_at).toLocaleString(),
            Deadline: item.deadline
              ? new Date(item.deadline).toLocaleString()
              : "None",
          }).map(([label, value]) => (
            <div key={label}>
              <dt className="text-ink-muted">{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
        <details>
          <summary>Audit history ({item.history.length})</summary>
          {item.history.length === 0 && <p>No review actions recorded.</p>}
          <ol>
            {item.history.map((event, index) => (
              <li key={index}>
                {new Date(event.at).toLocaleString()} · {event.action} ·{" "}
                {event.actor_id ?? "System"}{" "}
                {event.owner_id && <> · Assigned to {event.owner_id}</>}{" "}
                {event.reason && <p>{event.reason}</p>}
              </li>
            ))}
          </ol>
        </details>
        {item.amount && (
          <p>
            Recorded amount: {item.currency} {item.amount}
          </p>
        )}
        {item.description && (
          <p className="text-sm text-ink-muted">{item.description}</p>
        )}
        <section className="space-y-2 rounded-lg border border-border px-4 py-3 text-sm">
          <h3 className="font-semibold text-ink">Evidence</h3>
          {item.evidence_details.length === 0 && (
            <p className="text-ink-muted">
              No source quotations are available.
            </p>
          )}
          {item.evidence_details.map((source) => (
            <div
              key={source.id}
              className="space-y-1 border-l-2 border-border pl-3"
            >
              {source.document_id ? (
                <DocumentLink
                  id={source.document_id}
                  label={source.document_name ?? "Open evidence document"}
                />
              ) : (
                <p className="capitalize">
                  {source.source_type.replaceAll("_", " ")}
                </p>
              )}
              <SourceQuotation source={source} />
            </div>
          ))}
          {item.document_id && (
            <DocumentLink
              id={item.document_id}
              label="Open original document"
            />
          )}
        </section>
        <div className="text-sm">
          <h3 className="font-semibold text-ink">Recommended action</h3>
          <p>
            {item.recommended_action ??
              (item.evidence_supported
                ? "Review the linked sources."
                : "Request supporting evidence.")}
          </p>
          {item.kind === "risk" && !item.evidence_supported && (
            <p className="mt-2 text-ink-muted">
              Acceptance and conversion require supporting evidence.
            </p>
          )}
        </div>
        <ReviewActionButtons
          item={item}
          canConvert={canConvert}
          onAction={onAction}
        />
      </CardBody>
    </Card>
  );
}

type Reviewer = { id: string; full_name: string };
type Selection = { items: WorkspaceItem[]; action: WorkspaceAction };
function CommandDialog({
  projectId,
  selection,
  reviewers,
  close,
  saved,
}: {
  projectId: string;
  selection: Selection;
  reviewers: Reviewer[];
  close: () => void;
  saved: (draft: string | null) => Promise<void>;
}) {
  const { items, action } = selection;
  const [reason, setReason] = useState("");
  const [owner, setOwner] = useState("");
  const [severity, setSeverity] = useState("");
  const [key] = useState(() => crypto.randomUUID());
  const decision = useMutation({
    mutationFn: async () => {
      if (items.length > 1) {
        await workspaceApi.notes(projectId, items, reason.trim(), key);
        return null;
      }
      const item = items[0];
      if (!item) throw new Error("Select a review item.");
      const response = await workspaceApi.command(projectId, item, {
        key,
        action,
        reason: reason.trim(),
        owner_id: action === "assign_owner" ? owner : undefined,
        severity: action === "override" ? severity : undefined,
      });
      return response.change_order_id;
    },
    onSuccess: saved,
  });
  return (
    <Modal
      open
      title={labels[action]}
      onClose={() => {
        if (!decision.isPending) close();
      }}
    >
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          decision.mutate();
        }}
      >
        <p>
          {items.length === 1
            ? items[0]?.title
            : `${items.length} selected reviews`}
        </p>
        <fieldset
          disabled={
            decision.isPending ||
            (isApiError(decision.error) && decision.error.isTransient)
          }
          className="space-y-3"
        >
          {action === "assign_owner" && (
            <Field label="Reviewer" id="assignee">
              <Select
                required
                id="assignee"
                value={owner}
                onChange={(e) => setOwner(e.target.value)}
              >
                <option value="">Select reviewer</option>
                {reviewers.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.full_name}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          {action === "override" && (
            <Field label="New severity" id="severity">
              <Select
                id="severity"
                value={severity}
                onChange={(e) => setSeverity(e.target.value)}
              >
                <option value="">Select a severity</option>
                {RISK_SEVERITIES.filter((s) => s !== items[0]?.severity).map(
                  (s) => (
                    <option key={s}>{s}</option>
                  ),
                )}
              </Select>
            </Field>
          )}
          <Field
            label={action === "add_note" ? "Review note" : "Reason"}
            id="command-reason"
          >
            <textarea
              required
              maxLength={2000}
              id="command-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="w-full rounded border p-2"
            />
          </Field>
        </fieldset>
        {decision.isError && (
          <ErrorState
            title={
              isApiError(decision.error) && decision.error.status === 409
                ? "Review state changed"
                : isApiError(decision.error) && decision.error.isForbidden
                  ? "Permission denied"
                  : "Could not save decision"
            }
            message={errorMessage(decision.error)}
          />
        )}
        <Button
          type="submit"
          loading={decision.isPending}
          disabled={
            !reason.trim() ||
            (action === "assign_owner" && !owner) ||
            (action === "override" && !severity)
          }
        >
          {labels[action]}
        </Button>
      </form>
    </Modal>
  );
}

const defaultFilters = {
  category: "",
  severity: "",
  status: "actionable",
  owner_id: "",
  created_from: "",
  created_to: "",
  min_confidence: "",
  max_confidence: "",
  sort: "created_at",
  direction: "desc",
};
function ProjectReviewQueue({ projectId }: { projectId: string }) {
  const { session } = useAuth();
  const role = session?.roles[0];
  const canConvert = hasPermission(role ?? "", "change_orders.write");
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState(defaultFilters);
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<string[]>([]);
  const [dialog, setDialog] = useState<Selection | null>(null);
  const [notice, setNotice] = useState("");
  const [draft, setDraft] = useState<string | null>(null);
  const key = [
    "review-workspace",
    session?.tenantId,
    session?.userId,
    role,
    projectId,
  ];
  const queue = useQuery({
    queryKey: [...key, filters, page],
    queryFn: () =>
      workspaceApi.page(projectId, { ...filters, page, page_size: 20 }),
  });
  const roster = useQuery({
    queryKey: [...key, "reviewers"],
    queryFn: () => workspaceApi.reviewers(projectId),
  });
  const choices = roster.data ?? [];
  const ownerLabel = (id: string | null) =>
    choices.find((x) => x.id === id)?.full_name ?? id ?? "Unassigned";
  const changePage = (p: number) => {
    setPage(p);
    setSelected([]);
  };
  const update = (field: keyof typeof filters, value: string) => {
    setFilters((prev) => ({ ...prev, [field]: value }));
    changePage(1);
  };
  const dropdown = (
    field: keyof typeof filters,
    label: string,
    options: Record<string, string>,
  ) => (
    <FilterSelect
      field={field}
      label={label}
      value={filters[field]}
      options={options}
      onChange={(value) => update(field, value)}
    />
  );
  const rows = queue.data?.items ?? [];
  const rowKey = (i: WorkspaceItem) => i.kind + "/" + i.id;
  const pending = rows.filter(
    (i) => i.reviewable && selected.includes(rowKey(i)),
  );
  return (
    <section className="space-y-5">
      <fieldset className="grid gap-3 rounded-lg border p-4 sm:grid-cols-3">
        <legend>Filter reviews</legend>
        {dropdown("category", "Item type", {
          "": "All types",
          ...REVIEW_CATEGORIES,
        })}
        {dropdown("severity", "Severity", {
          "": "All severities",
          ...Object.fromEntries(RISK_SEVERITIES.map((s) => [s, s])),
        })}
        {dropdown("status", "Review state", states)}
        {dropdown("owner_id", "Owner", {
          "": "All owners",
          ...Object.fromEntries(choices.map((u) => [u.id, u.full_name])),
        })}
        {(
          [
            "created_from",
            "created_to",
            "min_confidence",
            "max_confidence",
          ] as const
        ).map((field, index) => (
          <Field
            key={field}
            id={field}
            label={
              [
                "Created from",
                "Created through",
                "Minimum confidence (0–1)",
                "Maximum confidence (0–1)",
              ][index]!
            }
          >
            <input
              className="w-full rounded border p-2"
              id={field}
              type={index < 2 ? "date" : "number"}
              min={index < 2 ? undefined : 0}
              max={index < 2 ? undefined : 1}
              step={index < 2 ? undefined : 0.01}
              value={filters[field]}
              onChange={(e) => update(field, e.target.value)}
            />
          </Field>
        ))}
        {dropdown("sort", "Sort by", {
          created_at: "Created date",
          deadline: "Deadline",
          severity: "Severity",
          confidence: "Confidence",
        })}
        {dropdown("direction", "Direction", {
          desc: "Descending",
          asc: "Ascending",
        })}
      </fieldset>
      {roster.isError && (
        <LoadError error={roster.error} retry={() => void roster.refetch()} />
      )}
      {queue.isPending && <LoadingSkeleton rows={3} />}
      {queue.isError && (
        <LoadError error={queue.error} retry={() => void queue.refetch()} />
      )}
      <p role="status">
        {notice}{" "}
        {draft && (
          <Link
            className="underline"
            href={`/projects/${projectId}/change-orders/${draft}`}
          >
            Open draft
          </Link>
        )}
      </p>
      {queue.isSuccess && (
        <>
          {rows.length === 0 && (
            <EmptyState title="No reviews match these filters" />
          )}
          {pending.length > 0 && (
            <Button
              onClick={() => setDialog({ items: pending, action: "add_note" })}
            >
              Add note to {pending.length} selected
            </Button>
          )}
          {rows.map((item) => (
            <article key={rowKey(item)} className="space-y-2">
              {item.reviewable && (
                <label>
                  <input
                    type="checkbox"
                    checked={selected.includes(rowKey(item))}
                    onChange={(e) =>
                      setSelected(
                        e.target.checked
                          ? [...selected, rowKey(item)]
                          : selected.filter((id) => id !== rowKey(item)),
                      )
                    }
                  />{" "}
                  Select {item.title} for a note
                </label>
              )}
              <ReviewCard
                item={item}
                owner={ownerLabel(item.owner_id)}
                canConvert={canConvert}
                onAction={(action) => setDialog({ items: [item], action })}
              />
              {item.change_order_id && (
                <Link
                  className="text-brand underline"
                  href={`/projects/${projectId}/change-orders/${item.change_order_id}`}
                >
                  Open change order for {item.title}
                </Link>
              )}
            </article>
          ))}
          <nav aria-label="Review pages" className="flex items-center gap-3">
            <Button
              variant="secondary"
              disabled={page === 1}
              onClick={() => changePage(page - 1)}
            >
              Previous
            </Button>
            <span>
              Page {page} · {queue.data.total} items
            </span>
            <Button
              variant="secondary"
              disabled={page * 20 >= queue.data.total}
              onClick={() => changePage(page + 1)}
            >
              Next
            </Button>
          </nav>
        </>
      )}
      {dialog && (
        <CommandDialog
          projectId={projectId}
          selection={dialog}
          reviewers={choices}
          close={() => {
            setDialog(null);
            void queryClient.invalidateQueries({ queryKey: key });
          }}
          saved={async (draftId) => {
            setDialog(null);
            setSelected([]);
            setNotice("Review saved.");
            setDraft(draftId);
            changePage(1);
            await queryClient.invalidateQueries({ queryKey: key });
          }}
        />
      )}
    </section>
  );
}

function ReviewQueue() {
  const { session } = useAuth();
  const requested = useSearchParams().get("project");
  const [selectedProject, setSelectedProject] = useState(requested ?? "");
  const projects = useQuery({
    queryKey: [
      "review-queue-projects",
      session?.tenantId,
      session?.userId,
      session?.roles[0],
    ],
    queryFn: async () => {
      const first = await projectsApi.list({ page: 1, page_size: 100 });
      const items = [...first.items];
      for (let page = 2; page <= first.metadata.total_pages; page++) {
        const next = await projectsApi.list({ page, page_size: 100 });
        if (next.items.length === 0) break;
        items.push(...next.items);
      }
      return items;
    },
  });
  const projectId =
    projects.data?.find((project) => project.id === selectedProject)?.id ??
    (selectedProject ? undefined : projects.data?.[0]?.id);
  return (
    <main className="mx-auto max-w-5xl space-y-5 px-4 py-8 sm:px-6">
      <h1 className="text-2xl font-semibold text-ink">Review Queue</h1>
      {projects.isPending && <LoadingSkeleton rows={3} />}
      {projects.isError && (
        <LoadError
          error={projects.error}
          retry={() => void projects.refetch()}
        />
      )}
      {projects.isSuccess && projectId && (
        <>
          <Field id="review-project" label="Project" className="max-w-xs">
            <Select
              id="review-project"
              value={projectId}
              onChange={(event) => setSelectedProject(event.target.value)}
            >
              {projects.data.map((project) => (
                <option key={project.id} value={project.id}>
                  {project.name}
                </option>
              ))}
            </Select>
          </Field>
          <ProjectReviewQueue key={projectId} projectId={projectId} />
        </>
      )}
      {projects.isSuccess && !projectId && (
        <EmptyState
          title="No projects available"
          description="Your review queue will appear here when you have access to a project."
        />
      )}
    </main>
  );
}

export default function ReviewQueuePage() {
  return (
    <ProtectedRoute requiredPermission="risks.accept">
      <Suspense fallback={<LoadingSkeleton rows={3} />}>
        <ReviewQueue />
      </Suspense>
    </ProtectedRoute>
  );
}
