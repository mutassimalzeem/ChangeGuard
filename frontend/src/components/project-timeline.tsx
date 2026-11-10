"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { timelineApi, documentsApi, changeOrdersApi } from "@/lib/api/resources";
import { errorMessage } from "@/lib/api/errors";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Modal } from "@/components/ui/modal";
import { Field, Input } from "@/components/ui/form";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui/states";
import type { TimelineItem } from "@/lib/contracts";

export function ProjectTimeline({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const [offset, setOffset] = useState(0);
  const [sourceError, setSourceError] = useState<string | null>(null);

  // Draft Creation Modal State
  const [draftingRisk, setDraftingRisk] = useState<TimelineItem | null>(null);
  const [draftRef, setDraftRef] = useState("");
  const [draftTitle, setDraftTitle] = useState("");
  const [draftReason, setDraftReason] = useState("");
  const [draftError, setDraftError] = useState<string | null>(null);
  const [draftSuccessMessage, setDraftSuccessMessage] = useState<string | null>(null);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["project-timeline", projectId, offset],
    queryFn: () => timelineApi.list(projectId, offset),
    refetchInterval: 5000,
  });

  const createDraftMutation = useMutation({
    mutationFn: async (vars: {
      riskId: string;
      reference?: string;
      title?: string;
      reason: string;
    }) => {
      return changeOrdersApi.createFromRisk(projectId, vars.riskId, {
        reference: vars.reference?.trim() || undefined,
        title: vars.title?.trim() || undefined,
        reason: vars.reason.trim(),
      });
    },
    onSuccess: (order) => {
      setDraftSuccessMessage(
        `Draft change order "${order.reference}" successfully created with status "${order.status}". Financial & schedule fields remain null for human review.`
      );
      setDraftingRisk(null);
      setDraftRef("");
      setDraftTitle("");
      setDraftReason("");
      setDraftError(null);
      queryClient.invalidateQueries({ queryKey: ["project-timeline", projectId] });
    },
    onError: (err) => {
      setDraftError(errorMessage(err, "Failed to create change order draft."));
    },
  });

  function handleStartDraft(item: TimelineItem) {
    setDraftingRisk(item);
    setDraftRef(`CO-DR-${item.id.slice(0, 8).toUpperCase()}`);
    setDraftTitle(`Delay Mitigation: ${item.title}`);
    setDraftReason("Substantiated delay risk converted to formal change-order draft citing evidence");
    setDraftError(null);
    setDraftSuccessMessage(null);
  }

  function handleDraftSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!draftingRisk) return;
    if (!draftReason.trim()) {
      setDraftError("A reason is mandatory to create a change-order draft");
      return;
    }
    createDraftMutation.mutate({
      riskId: draftingRisk.id,
      reference: draftRef,
      title: draftTitle,
      reason: draftReason,
    });
  }

  async function openSource(documentId: string) {
    setSourceError(null);
    try {
      const result = await documentsApi.downloadUrl(documentId);
      window.open(result, "_blank", "noopener,noreferrer");
    } catch (cause) {
      setSourceError(errorMessage(cause, "Could not open the source document."));
    }
  }

  return (
    <section className="flex flex-col gap-4" aria-label="Project evidence timeline">
      <div>
        <h2 className="text-base font-semibold text-ink">Project Evidence Timeline</h2>
        <p className="text-xs text-ink-muted">Recorded events and risks, with their source evidence. Updates automatically.</p>
      </div>

      {sourceError && <p role="alert" className="text-sm text-danger">{sourceError}</p>}
      {draftSuccessMessage && (
        <div role="status" className="rounded-lg border border-success/30 bg-success-soft p-3 text-xs text-success">
          {draftSuccessMessage}
        </div>
      )}

      {isLoading ? <LoadingSkeleton rows={4} variant="cards" /> : error ? (
        <ErrorState title="Failed to load timeline" message={errorMessage(error)} onRetry={() => refetch()} />
      ) : data?.items.length ? (
        <ol className="space-y-4">
          {data.items.map((item) => (
            <li key={`${item.kind}:${item.id}`}>
              <Card><CardBody className="flex flex-col gap-3 p-4">
                <div className="flex flex-wrap justify-between gap-2 text-xs text-ink-muted">
                  <span>{item.kind === "risk" ? `Risk · ${item.severity}` : "Event"} · {item.status.replaceAll("_", " ")}</span>
                  <time dateTime={item.occurred_at}>{new Date(item.occurred_at).toLocaleString()}</time>
                </div>
                <h3 className="font-semibold text-ink">{item.title}</h3>
                <p className="text-sm text-ink">{item.description}</p>
                {item.evidence_status === "insufficient_evidence" && (
                  <p className="text-sm text-ink-muted">Insufficient evidence. Review the original before relying on this signal.</p>
                )}
                {item.event_type === "daily_report_delay_without_link" && (
                  <p className="text-xs text-ink-muted">Financial exposure and schedule impact require review.</p>
                )}

                {/* Evidence Inspection */}
                <details className="border-t border-border pt-3">
                  <summary className="cursor-pointer text-sm font-medium text-brand">Inspect evidence ({item.evidence.length})</summary>
                  <ul className="mt-3 space-y-3">
                    {item.evidence.map((source) => (
                      <li key={source.evidence_link_id} className="text-sm text-ink">
                        <p className="text-xs text-ink-muted">Source {source.source_id}{source.source_page ? ` · Page ${source.source_page}` : " · Page unavailable"}</p>
                        {source.source_text_snippet ? <blockquote className="my-2 border-l-2 border-brand pl-3">{source.source_text_snippet}</blockquote> : <p>No source quotation available.</p>}
                        {source.source_type === "document" && <Button variant="ghost" size="sm" onClick={() => openSource(source.source_id)}>Open original</Button>}
                      </li>
                    ))}
                  </ul>
                </details>

                {/* Flow Step 1 & 2: Risk to Change Order Draft Action */}
                {item.kind === "risk" && (
                  <div className="mt-1 flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3">
                    {item.status === "converted" || item.change_order_id ? (
                      <span className="inline-flex items-center gap-1.5 rounded-full bg-brand/10 px-2.5 py-0.5 text-xs font-medium text-brand">
                        ✓ Change order draft created
                      </span>
                    ) : (
                      <div className="flex flex-wrap items-center gap-2">
                        <Button
                          size="sm"
                          variant="secondary"
                          disabled={item.evidence_status === "insufficient_evidence" || item.evidence.length === 0}
                          onClick={() => handleStartDraft(item)}
                        >
                          Create change-order draft
                        </Button>
                        {item.evidence_status === "insufficient_evidence" && (
                          <span className="text-xs text-ink-muted">Every draft must cite evidence</span>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </CardBody></Card>
            </li>
          ))}
        </ol>
      ) : <EmptyState title="No visible timeline entries" description="Upload a daily report to begin. Processing and evidence review may take a few minutes." />}
      
      {data && (offset > 0 || data.has_more) && <nav aria-label="Timeline pages" className="flex gap-2">
        <Button variant="ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</Button>
        <Button variant="ghost" disabled={!data.has_more} onClick={() => setOffset(offset + 50)}>Next</Button>
      </nav>}

      {/* Modal: Create Change Order Draft from Delay Risk */}
      {draftingRisk && (
        <Modal
          open={Boolean(draftingRisk)}
          title="Create Change-Order Draft from Delay Risk"
          onClose={() => setDraftingRisk(null)}
          actions={
            <>
              <Button variant="ghost" size="sm" onClick={() => setDraftingRisk(null)}>
                Cancel
              </Button>
              <Button
                size="sm"
                type="submit"
                form="create-draft-form"
                loading={createDraftMutation.isPending}
              >
                Create Draft
              </Button>
            </>
          }
        >
          <form id="create-draft-form" onSubmit={handleDraftSubmit} className="flex flex-col gap-3">
            {draftError && (
              <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft p-2.5 text-xs text-danger">
                {draftError}
              </div>
            )}

            <div className="rounded-lg border border-border bg-surface-raised p-3 text-xs text-ink-muted space-y-1">
              <p className="font-semibold text-ink">Grounded Drafting Rules:</p>
              <p>• The narrative will cite only the {draftingRisk.evidence.length} linked evidence item(s).</p>
              <p>• Cost and schedule impacts strictly remain null until a human reviewer enters them.</p>
              <p>• No external communications will be sent automatically.</p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <Field id="draft-ref" label="Change Order Reference">
                <Input
                  id="draft-ref"
                  value={draftRef}
                  onChange={(e) => setDraftRef(e.target.value)}
                  placeholder="CO-DR-..."
                />
              </Field>

              <Field id="draft-title" label="Draft Title">
                <Input
                  id="draft-title"
                  value={draftTitle}
                  onChange={(e) => setDraftTitle(e.target.value)}
                  placeholder="Delay Mitigation: ..."
                />
              </Field>
            </div>

            <Field
              id="draft-reason"
              label="Justification Reason"
              hint="Mandatory reason for audit record"
              required
            >
              <textarea
                id="draft-reason"
                rows={3}
                value={draftReason}
                onChange={(e) => setDraftReason(e.target.value)}
                placeholder="Explain the commercial rationale for converting this evidence-backed delay risk to a change-order draft..."
                required
                className="w-full rounded-md border border-border bg-surface p-2.5 text-xs text-ink placeholder:text-ink-muted focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
              />
            </Field>
          </form>
        </Modal>
      )}
    </section>
  );
}
