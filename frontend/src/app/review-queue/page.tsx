"use client";

import { useState, type FormEvent } from "react";
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
import { RISK_SEVERITIES, type RiskSeverity } from "@/lib/contracts";
import { hasPermission } from "@/lib/rbac";
import {
  availableReviewActions,
  REVIEW_ACTIONS,
  REVIEW_CATEGORIES,
  reviewDecisionSchema,
  reviewQueueApi,
  type ReviewAction,
  type ReviewCategory,
  type ReviewItem,
} from "@/lib/review-queue";

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
  canConvert,
  onAction,
}: {
  item: ReviewItem;
  canConvert: boolean;
  onAction: (action: ReviewAction) => void;
}) {
  const actions = availableReviewActions(item, canConvert);
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
            <dt className="text-ink-muted">Risk type</dt>
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
        </dl>
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
              <p className="text-ink-muted">
                {source.source_page === null
                  ? "Page unavailable"
                  : `Page ${source.source_page}`}
              </p>
              {source.source_text_snippet ? (
                <blockquote>“{source.source_text_snippet}”</blockquote>
              ) : (
                <p>Quotation unavailable</p>
              )}
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
        {actions.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {actions.map((action) => (
              <Button
                key={action}
                onClick={() => onAction(action)}
                variant={action === "accept" ? "primary" : "secondary"}
                size="sm"
              >
                {item.kind === "extraction" && action === "dismiss"
                  ? "Dismiss review item"
                  : REVIEW_ACTIONS[action]}
              </Button>
            ))}
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function ReviewDecision({
  projectId,
  item,
  action,
  canConvert,
  close,
  saved,
}: {
  projectId: string;
  item: ReviewItem;
  action: ReviewAction;
  canConvert: boolean;
  close: () => void;
  saved: (message: string) => Promise<void>;
}) {
  const [reason, setReason] = useState("");
  const [severity, setSeverity] = useState<RiskSeverity>(
    item.severity ?? "medium",
  );
  const [validation, setValidation] = useState("");
  const decision = useMutation({
    mutationFn: (payload: Parameters<typeof reviewQueueApi.decide>[2]) =>
      reviewQueueApi.decide(projectId, item, payload, canConvert),
    onSuccess: (order) =>
      saved(
        order
          ? `Draft change order ${order.reference} created.`
          : "Review decision saved.",
      ),
  });
  const label =
    item.kind === "extraction" && action === "dismiss"
      ? "Dismiss review item"
      : REVIEW_ACTIONS[action];

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = reviewDecisionSchema.safeParse({
      action,
      reason,
      severity: action === "override" ? severity : undefined,
    });
    if (!parsed.success) {
      setValidation(parsed.error.issues[0]?.message ?? "Check your decision.");
      return;
    }
    setValidation("");
    decision.mutate(parsed.data);
  }

  return (
    <Modal
      open
      title={label}
      onClose={() => {
        if (!decision.isPending) close();
      }}
      actions={
        <Button
          type="submit"
          form="review-decision"
          loading={decision.isPending}
        >
          {label}
        </Button>
      }
    >
      <form id="review-decision" onSubmit={submit} className="space-y-4">
        <p className="font-medium">{item.title}</p>
        {action === "convert_to_change_order" && (
          <p>
            This action creates a draft change order with the linked evidence.
          </p>
        )}
        {action === "override" && (
          <Field id="review-severity" label="Severity">
            <Select
              id="review-severity"
              value={severity}
              onChange={(event) =>
                setSeverity(event.target.value as RiskSeverity)
              }
            >
              {RISK_SEVERITIES.map((value) => (
                <option key={value} value={value}>
                  {value}
                </option>
              ))}
            </Select>
          </Field>
        )}
        <Field
          id="review-reason"
          label="Reason"
          required
          error={validation || undefined}
        >
          <textarea
            id="review-reason"
            required
            maxLength={2000}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            aria-describedby={validation ? "review-reason-error" : undefined}
            className="min-h-24 w-full rounded-lg border border-border bg-surface p-3"
          />
        </Field>
        {decision.isError && (
          <ErrorState
            title={
              isApiError(decision.error) && decision.error.isForbidden
                ? "Permission denied"
                : "Decision could not be saved"
            }
            message={errorMessage(decision.error)}
          />
        )}
      </form>
    </Modal>
  );
}

function ProjectReviewQueue({ projectId }: { projectId: string }) {
  const { session } = useAuth();
  const role = session?.roles[0];
  const canConvert = hasPermission(role ?? "", "change_orders.write");
  const queryClient = useQueryClient();
  const [category, setCategory] = useState<ReviewCategory | "">("");
  const [selection, setSelection] = useState<{
    item: ReviewItem;
    action: ReviewAction;
  } | null>(null);
  const [notice, setNotice] = useState("");
  const queryKey = [
    "review-queue",
    session?.tenantId,
    session?.userId,
    role,
    projectId,
  ];
  const queue = useQuery({
    queryKey,
    queryFn: () => reviewQueueApi.list(projectId),
  });

  if (queue.isPending) return <LoadingSkeleton rows={3} />;
  if (queue.isError)
    return <LoadError error={queue.error} retry={() => void queue.refetch()} />;
  if (queue.data.length === 0)
    return (
      <div className="space-y-4">
        {notice && <p role="status">{notice}</p>}
        <EmptyState
          title="Review queue is empty"
          description="There are no findings or extraction reviews for this project."
        />
      </div>
    );

  const items = queue.data.filter(
    (item) => !category || item.categories.includes(category),
  );
  return (
    <div className="space-y-4">
      <Field id="review-category" label="Category" className="max-w-xs">
        <Select
          id="review-category"
          value={category}
          onChange={(event) =>
            setCategory(event.target.value as ReviewCategory | "")
          }
        >
          <option value="">All categories</option>
          {Object.entries(REVIEW_CATEGORIES).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </Field>
      <p role="status" className="text-sm text-ink">
        {notice}
      </p>
      {items.length === 0 && <EmptyState title="No items in this category" />}
      {items.map((item) => (
        <div key={item.id}>
          <ReviewCard
            item={item}
            canConvert={canConvert}
            onAction={(action) => {
              setNotice("");
              setSelection({ item, action });
            }}
          />
          {item.change_order_id && (
            <Link
              className="mt-2 inline-block text-sm text-brand underline"
              href={`/projects/${projectId}/change-orders/${item.change_order_id}`}
            >
              Open change order for {item.title}
            </Link>
          )}
        </div>
      ))}
      {selection && (
        <ReviewDecision
          projectId={projectId}
          item={selection.item}
          action={selection.action}
          canConvert={canConvert}
          close={() => setSelection(null)}
          saved={async (message) => {
            await Promise.all([
              queryClient.invalidateQueries({ queryKey }),
              queryClient.invalidateQueries({ queryKey: ["risks", projectId] }),
              queryClient.invalidateQueries({
                queryKey: ["project-change-orders", projectId],
              }),
            ]);
            setSelection(null);
            setNotice(message);
          }}
        />
      )}
    </div>
  );
}

function ReviewQueue() {
  const { session } = useAuth();
  const [selectedProject, setSelectedProject] = useState("");
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
    projects.data?.[0]?.id;
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
      <ReviewQueue />
    </ProtectedRoute>
  );
}
