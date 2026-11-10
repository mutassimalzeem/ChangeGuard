"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { timelineApi, documentsApi } from "@/lib/api/resources";
import { errorMessage } from "@/lib/api/errors";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui/states";

export function ProjectTimeline({ projectId }: { projectId: string }) {
  const [offset, setOffset] = useState(0);
  const [sourceError, setSourceError] = useState<string | null>(null);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["project-timeline", projectId, offset],
    queryFn: () => timelineApi.list(projectId, offset),
    refetchInterval: 5000,
  });

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
              </CardBody></Card>
            </li>
          ))}
        </ol>
      ) : <EmptyState title="No visible timeline entries" description="Upload a daily report to begin. Processing and evidence review may take a few minutes." />}
      {data && (offset > 0 || data.has_more) && <nav aria-label="Timeline pages" className="flex gap-2">
        <Button variant="ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</Button>
        <Button variant="ghost" disabled={!data.has_more} onClick={() => setOffset(offset + 50)}>Next</Button>
      </nav>}
    </section>
  );
}
