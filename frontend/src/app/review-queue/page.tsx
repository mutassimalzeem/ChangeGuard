"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input, Select } from "@/components/ui/form";
import { Modal } from "@/components/ui/modal";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui/states";
import { DataTable, type Column } from "@/components/ui/table";
import { Tabs } from "@/components/ui/tabs";
import { ProtectedRoute } from "@/components/protected-route";
import {
  IconDocument,
  IconDownload,
  IconReview,
} from "@/components/icons";
import {
  changeOrdersApi,
  documentsApi,
  potentialChangesApi,
  projectsApi,
  risksApi,
} from "@/lib/api/resources";
import { errorMessage } from "@/lib/api/errors";
import { useRole } from "@/lib/auth";
import { hasPermission } from "@/lib/rbac";
import {
  changeOrderCreateSchema,
  riskDecisionSchema,
  type DocumentItem,
  type PotentialChangeItem,
  type RiskDecisionInput,
  type RiskItem,
  type RiskSeverity,
} from "@/lib/contracts";

export default function ReviewQueuePage() {
  const queryClient = useQueryClient();
  const role = useRole();

  const canAcceptRisks = role ? hasPermission(role, "risks.accept") : false;
  const canWriteChanges = role ? hasPermission(role, "change_orders.write") : false;

  const [activeTab, setActiveTab] = useState<"changes" | "risks" | "documents">("changes");
  const [selectedProjectId, setSelectedProjectId] = useState<string>("");

  // Projects list
  const { data: projectsData, isLoading: isProjectsLoading } = useQuery({
    queryKey: ["review-projects"],
    queryFn: () => projectsApi.list({ page: 1, page_size: 50, status: "active" }),
  });

  const projects = projectsData?.items || [];
  const currentProjectId = selectedProjectId || (projects[0]?.id ?? "");

  // Potential changes query
  const {
    data: changes,
    isLoading: isChangesLoading,
    isError: isChangesError,
    error: changesError,
    refetch: refetchChanges,
  } = useQuery({
    queryKey: ["review-changes", currentProjectId],
    queryFn: () => potentialChangesApi.list(currentProjectId),
    enabled: !!currentProjectId,
  });

  // Risks query
  const {
    data: risks,
    isLoading: isRisksLoading,
    isError: isRisksError,
    error: risksError,
    refetch: refetchRisks,
  } = useQuery({
    queryKey: ["review-risks", currentProjectId],
    queryFn: () => risksApi.list(currentProjectId),
    enabled: !!currentProjectId,
  });

  // Documents query
  const {
    data: documents,
    isLoading: isDocsLoading,
    isError: isDocsError,
    error: docsError,
    refetch: refetchDocs,
  } = useQuery({
    queryKey: ["review-documents", currentProjectId],
    queryFn: () => documentsApi.list(currentProjectId),
    enabled: !!currentProjectId,
  });

  // Risk decision modal
  const [selectedRisk, setSelectedRisk] = useState<RiskItem | null>(null);
  const [riskAction, setRiskAction] = useState<"accept" | "dismiss" | "override">("accept");
  const [riskReason, setRiskReason] = useState("");
  const [overrideSeverity, setOverrideSeverity] = useState<RiskSeverity>("medium");
  const [overrideDays, setOverrideDays] = useState("");
  const [decisionError, setDecisionError] = useState<string | null>(null);

  const riskMutation = useMutation({
    mutationFn: (payload: RiskDecisionInput) =>
      risksApi.decide(currentProjectId, selectedRisk!.id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["review-risks", currentProjectId] });
      setSelectedRisk(null);
      setRiskReason("");
      setDecisionError(null);
    },
    onError: (err) => setDecisionError(errorMessage(err, "Failed to submit risk decision.")),
  });

  const handleDecisionSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setDecisionError(null);

    const payload: Record<string, unknown> = {
      action: riskAction,
      reason: riskReason.trim(),
    };
    if (riskAction === "override") {
      payload.severity = overrideSeverity;
      if (overrideDays) payload.schedule_impact_days = parseInt(overrideDays, 10);
    }

    const parsed = riskDecisionSchema.safeParse(payload);
    if (!parsed.success) {
      setDecisionError(parsed.error.issues[0]?.message || "Invalid decision.");
      return;
    }
    riskMutation.mutate(parsed.data);
  };

  // Convert to CO modal
  const [selectedChange, setSelectedChange] = useState<PotentialChangeItem | null>(null);
  const [coRef, setCoRef] = useState("");
  const [coTitle, setCoTitle] = useState("");
  const [coAmount, setCoAmount] = useState("");
  const [coError, setCoError] = useState<string | null>(null);

  const convertCOMutation = useMutation({
    mutationFn: (payload: { reference: string; title: string; amount: string | null }) =>
      changeOrdersApi.create(currentProjectId, {
        reference: payload.reference,
        title: payload.title,
        amount: payload.amount,
        currency: "USD",
        time_impact_days: selectedChange?.suggested_schedule_impact ?? null,
        description: selectedChange?.description ?? "",
        evidence: [],
      }),
    onSuccess: (co) => {
      queryClient.invalidateQueries({ queryKey: ["review-changes", currentProjectId] });
      setSelectedChange(null);
      setCoError(null);
      alert(`Created Change Order ${co.reference} from potential variance.`);
    },
    onError: (err) => setCoError(errorMessage(err, "Failed to convert into change order.")),
  });

  const handleCOSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setCoError(null);
    const parsed = changeOrderCreateSchema.safeParse({
      reference: coRef.trim().toUpperCase(),
      title: coTitle.trim(),
      amount: coAmount.trim() || null,
      currency: "USD",
      evidence: [],
    });
    if (!parsed.success) {
      setCoError(parsed.error.issues[0]?.message || "Invalid input.");
      return;
    }
    convertCOMutation.mutate({
      reference: coRef.trim().toUpperCase(),
      title: coTitle.trim(),
      amount: coAmount.trim() || null,
    });
  };

  // Filtered review counts
  const pendingChanges = changes?.filter((c) => c.human_review_required) || [];
  const pendingRisks = risks?.filter((r) => r.status !== "accepted" && r.status !== "dismissed") || [];
  const flaggedDocs =
    documents?.filter(
      (d) => d.processing_status === "review_required" || d.status === "review_required",
    ) || [];

  const totalPending = pendingChanges.length + pendingRisks.length + flaggedDocs.length;

  const flaggedDocColumns: Column<DocumentItem>[] = [
    {
      key: "name",
      header: "Document File",
      render: (doc) => (
        <div className="flex items-center gap-2">
          <IconDocument className="size-4 text-warning shrink-0" />
          <span className="font-medium text-ink">{doc.file_name || doc.filename || "File"}</span>
        </div>
      ),
    },
    {
      key: "type",
      header: "Identified Type",
      render: (doc) => <span className="text-xs text-ink-muted capitalize">{doc.document_type || "Unclassified"}</span>,
    },
    {
      key: "reason",
      header: "Flag Reason",
      render: (doc) => (
        <span className="text-xs text-danger font-medium">
          {doc.error_message || "Classification confidence below threshold; manual verification needed"}
        </span>
      ),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (doc) => {
        const id = doc.document_id || doc.id;
        if (!id) return null;
        return (
          <Button
            variant="ghost"
            size="sm"
            onClick={async () => {
              try {
                const url = await documentsApi.downloadUrl(id);
                window.open(url, "_blank");
              } catch (e) {
                alert(errorMessage(e, "Cannot generate download url."));
              }
            }}
          >
            <IconDownload className="size-3.5" />
            <span>Inspect</span>
          </Button>
        );
      },
    },
  ];

  return (
    <ProtectedRoute>
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 flex flex-col gap-6">
        {/* Header & Project Selector */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-2.5">
              <div className="flex size-8 items-center justify-center rounded-lg bg-warning-soft text-warning">
                <IconReview className="size-5" />
              </div>
              <h1 className="text-2xl font-bold tracking-tight text-ink">Review Queue</h1>
            </div>
            <p className="mt-1 text-sm text-ink-muted">
              Audited human review for variances, potential changes, and commercial risk exposures
            </p>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-ink-muted">Project:</span>
            {isProjectsLoading ? (
              <div className="h-9 w-44 rounded bg-subtle animate-pulse" />
            ) : (
              <Select
                value={currentProjectId}
                onChange={(e) => setSelectedProjectId(e.target.value)}
                className="h-9 text-xs w-56 font-medium"
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.code} - {p.name}
                  </option>
                ))}
              </Select>
            )}
          </div>
        </div>

        {/* Metrics KPI Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <Card>
            <CardBody className="p-4">
              <span className="text-xs font-semibold uppercase text-ink-muted">Total Pending</span>
              <p className="mt-1 text-2xl font-bold text-ink tabular">{totalPending}</p>
            </CardBody>
          </Card>
          <Card>
            <CardBody className="p-4">
              <span className="text-xs font-semibold uppercase text-ink-muted">Potential Changes</span>
              <p className="mt-1 text-2xl font-bold text-brand tabular">{pendingChanges.length}</p>
            </CardBody>
          </Card>
          <Card>
            <CardBody className="p-4">
              <span className="text-xs font-semibold uppercase text-ink-muted">Risks Awaiting Decision</span>
              <p className="mt-1 text-2xl font-bold text-warning tabular">{pendingRisks.length}</p>
            </CardBody>
          </Card>
          <Card>
            <CardBody className="p-4">
              <span className="text-xs font-semibold uppercase text-ink-muted">Flagged Documents</span>
              <p className="mt-1 text-2xl font-bold text-danger tabular">{flaggedDocs.length}</p>
            </CardBody>
          </Card>
        </div>

        {/* Tabs */}
        <Tabs
          items={[
            { id: "changes", label: "Potential Changes", count: pendingChanges.length },
            { id: "risks", label: "Risks Requiring Decision", count: pendingRisks.length },
            { id: "documents", label: "Flagged Documents", count: flaggedDocs.length },
          ]}
          value={activeTab}
          onChange={(tab) => setActiveTab(tab as "changes" | "risks" | "documents")}
        />

        {/* Tab 1: Potential Changes */}
        {activeTab === "changes" && (
          <div className="flex flex-col gap-4">
            {isChangesLoading ? (
              <LoadingSkeleton rows={3} variant="cards" />
            ) : isChangesError ? (
              <ErrorState
                title="Failed to Load Changes"
                message={errorMessage(changesError, "Could not fetch changes.")}
                onRetry={() => refetchChanges()}
              />
            ) : pendingChanges.length > 0 ? (
              <div className="grid gap-4 sm:grid-cols-2">
                {pendingChanges.map((change) => (
                  <Card key={change.id} className="flex flex-col justify-between">
                    <CardHeader>
                      <div className="flex items-center justify-between w-full">
                        <span className="font-mono text-xs font-semibold uppercase text-brand">
                          {change.event_type}
                        </span>
                        <Badge tone="warning">Human Review Required</Badge>
                      </div>
                      <CardTitle className="mt-1 text-sm">{change.title}</CardTitle>
                    </CardHeader>
                    <CardBody className="flex flex-col gap-3 text-xs">
                      <p className="text-ink leading-relaxed">{change.description}</p>
                      <div className="grid grid-cols-2 gap-2 border-t border-border pt-2 text-ink-muted">
                        <div>
                          <span>Estimated Cost Impact:</span>
                          <p className="font-semibold text-ink tabular">
                            {change.suggested_cost_impact
                              ? `${Number(change.suggested_cost_impact).toLocaleString()} ${change.suggested_currency}`
                              : "TBD"}
                          </p>
                        </div>
                        <div>
                          <span>Estimated Schedule:</span>
                          <p className="font-semibold text-ink">
                            {change.suggested_schedule_impact !== null
                              ? `${change.suggested_schedule_impact} days`
                              : "TBD"}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center justify-between border-t border-border pt-3">
                        <span className="text-ink-muted">
                          Evidence references: {change.evidence_links.length}
                        </span>
                        {canWriteChanges ? (
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => {
                              setSelectedChange(change);
                              setCoRef(`CO-${Math.floor(100 + Math.random() * 900)}`);
                              setCoTitle(`Variation: ${change.title}`);
                              setCoAmount(change.suggested_cost_impact || "");
                              setCoError(null);
                            }}
                          >
                            Convert to Change Order &rarr;
                          </Button>
                        ) : null}
                      </div>
                    </CardBody>
                  </Card>
                ))}
              </div>
            ) : (
              <EmptyState
                title="All potential changes reviewed"
                description="No scope variances or cost deviations are currently pending human review."
              />
            )}
          </div>
        )}

        {/* Tab 2: Risks Requiring Decision */}
        {activeTab === "risks" && (
          <div className="flex flex-col gap-4">
            {isRisksLoading ? (
              <LoadingSkeleton rows={3} variant="cards" />
            ) : isRisksError ? (
              <ErrorState
                title="Failed to Load Risks"
                message={errorMessage(risksError, "Cannot read risks.")}
                onRetry={() => refetchRisks()}
              />
            ) : pendingRisks.length > 0 ? (
              <div className="grid gap-4 sm:grid-cols-2">
                {pendingRisks.map((risk) => (
                  <Card key={risk.id} className="flex flex-col justify-between">
                    <CardHeader>
                      <div className="flex items-center justify-between w-full">
                        <Badge tone={risk.severity === "critical" || risk.severity === "high" ? "danger" : "warning"}>
                          {risk.severity.toUpperCase()}
                        </Badge>
                        <span className="text-[11px] font-mono text-ink-muted">Status: {risk.status}</span>
                      </div>
                      <CardTitle className="mt-1 text-sm">{risk.title}</CardTitle>
                    </CardHeader>
                    <CardBody className="flex flex-col gap-3 text-xs">
                      <p className="text-ink leading-relaxed">{risk.description}</p>
                      <div className="grid grid-cols-2 gap-2 border-t border-border pt-2 text-ink-muted">
                        <div>
                          <span>Exposure:</span>
                          <p className="font-semibold text-ink tabular">
                            {risk.financial_exposure
                              ? `${Number(risk.financial_exposure).toLocaleString()} ${risk.currency}`
                              : "—"}
                          </p>
                        </div>
                        <div>
                          <span>Schedule Impact:</span>
                          <p className="font-semibold text-ink">
                            {risk.schedule_impact_days ? `${risk.schedule_impact_days} days` : "—"}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center justify-between border-t border-border pt-3">
                        <span className="text-ink-muted">Responsible: {risk.responsible_party || "Unassigned"}</span>
                        {canAcceptRisks ? (
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => {
                              setSelectedRisk(risk);
                              setRiskAction("accept");
                              setRiskReason("");
                              setOverrideSeverity((risk.severity as RiskSeverity) || "medium");
                              setOverrideDays(risk.schedule_impact_days ? String(risk.schedule_impact_days) : "");
                              setDecisionError(null);
                            }}
                          >
                            Decide Risk &rarr;
                          </Button>
                        ) : null}
                      </div>
                    </CardBody>
                  </Card>
                ))}
              </div>
            ) : (
              <EmptyState
                title="No risks requiring decision"
                description="All commercial and programme risk items have an approved audited decision."
              />
            )}
          </div>
        )}

        {/* Tab 3: Flagged Documents */}
        {activeTab === "documents" && (
          <div className="flex flex-col gap-4">
            {isDocsLoading ? (
              <LoadingSkeleton rows={3} variant="table" />
            ) : isDocsError ? (
              <ErrorState
                title="Failed to Load Flagged Documents"
                message={errorMessage(docsError, "Cannot read documents.")}
                onRetry={() => refetchDocs()}
              />
            ) : flaggedDocs.length > 0 ? (
              <DataTable
                caption="Flagged documents awaiting classification audit"
                captionHidden
                columns={flaggedDocColumns}
                rows={flaggedDocs}
                rowKey={(doc) => doc.document_id || doc.id || Math.random().toString()}
              />
            ) : (
              <EmptyState
                title="No documents flagged for review"
                description="All uploaded project documents have passed validation and automated pipeline extraction."
              />
            )}
          </div>
        )}

        {/* Risk Decision Modal */}
        <Modal
          open={selectedRisk !== null}
          title={`Review Risk: ${selectedRisk?.title ?? ""}`}
          onClose={() => setSelectedRisk(null)}
          actions={
            <>
              <Button variant="ghost" size="sm" onClick={() => setSelectedRisk(null)}>
                Cancel
              </Button>
              <Button
                size="sm"
                type="submit"
                form="queue-risk-decision-form"
                loading={riskMutation.isPending}
              >
                Submit Decision
              </Button>
            </>
          }
        >
          <form id="queue-risk-decision-form" onSubmit={handleDecisionSubmit} className="flex flex-col gap-3">
            {decisionError ? (
              <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft p-2.5 text-xs text-danger">
                {decisionError}
              </div>
            ) : null}

            <Field id="q-risk-act" label="Action" required>
              <Select
                id="q-risk-act"
                value={riskAction}
                onChange={(e) => setRiskAction(e.target.value as "accept" | "dismiss" | "override")}
              >
                <option value="accept">Accept (Commercial recognition)</option>
                <option value="dismiss">Dismiss (Deem not applicable)</option>
                <option value="override">Override (Adjust severity or schedule effect)</option>
              </Select>
            </Field>

            {riskAction === "override" ? (
              <div className="grid grid-cols-2 gap-3 p-3 bg-subtle rounded-lg">
                <Field id="q-ov-sev" label="Revised Severity">
                  <Select
                    id="q-ov-sev"
                    value={overrideSeverity}
                    onChange={(e) => setOverrideSeverity(e.target.value as RiskSeverity)}
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                  </Select>
                </Field>

                <Field id="q-ov-days" label="Revised Schedule (Days)">
                  <Input
                    id="q-ov-days"
                    type="number"
                    value={overrideDays}
                    onChange={(e) => setOverrideDays(e.target.value)}
                    placeholder="0"
                  />
                </Field>
              </div>
            ) : null}

            <Field id="q-risk-reason" label="Audited Reason" hint="Mandatory justification recorded in audit log" required>
              <Input
                id="q-risk-reason"
                value={riskReason}
                onChange={(e) => setRiskReason(e.target.value)}
                placeholder="State the commercial justification..."
                required
              />
            </Field>
          </form>
        </Modal>

        {/* Convert to CO Modal */}
        <Modal
          open={selectedChange !== null}
          title="Convert Potential Change into Change Order"
          onClose={() => setSelectedChange(null)}
          actions={
            <>
              <Button variant="ghost" size="sm" onClick={() => setSelectedChange(null)}>
                Cancel
              </Button>
              <Button
                size="sm"
                type="submit"
                form="convert-co-form"
                loading={convertCOMutation.isPending}
              >
                Create Change Order
              </Button>
            </>
          }
        >
          <form id="convert-co-form" onSubmit={handleCOSubmit} className="flex flex-col gap-3">
            {coError ? (
              <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft p-2.5 text-xs text-danger">
                {coError}
              </div>
            ) : null}

            <Field id="conv-ref" label="Change Order Reference" required>
              <Input
                id="conv-ref"
                value={coRef}
                onChange={(e) => setCoRef(e.target.value.toUpperCase())}
                required
              />
            </Field>

            <Field id="conv-title" label="Change Order Title" required>
              <Input
                id="conv-title"
                value={coTitle}
                onChange={(e) => setCoTitle(e.target.value)}
                required
              />
            </Field>

            <Field id="conv-amt" label="Claim Amount">
              <Input
                id="conv-amt"
                value={coAmount}
                onChange={(e) => setCoAmount(e.target.value)}
                placeholder="0.00"
              />
            </Field>
          </form>
        </Modal>
      </div>
    </ProtectedRoute>
  );
}

