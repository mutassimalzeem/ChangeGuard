"use client";

import { use, useState } from "react";
import Link from "next/link";
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
  IconArrowLeft,
  IconDocument,
  IconDownload,
  IconPlus,
  IconUpload,
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
  type ChangeOrderCreateInput,
  type DocumentItem,
  type ProjectStatus,
  type ProjectUpdate,
  type RiskDecisionInput,
  type RiskItem,
  type RiskSeverity,
} from "@/lib/contracts";

interface PageProps {
  params: Promise<{ projectId: string }>;
}

export default function ProjectDetailPage({ params }: PageProps) {
  const { projectId } = use(params);
  const queryClient = useQueryClient();
  const role = useRole();

  const canUpdateProject = role ? hasPermission(role, "project.update") : false;
  const canWriteDocs = role ? hasPermission(role, "documents.write") : false;
  const canWriteChanges = role ? hasPermission(role, "change_orders.write") : false;
  const canAcceptRisks = role ? hasPermission(role, "risks.accept") : false;

  const [activeTab, setActiveTab] = useState("overview");

  // Project fetch
  const {
    data: project,
    isLoading: isProjectLoading,
    isError: isProjectError,
    error: projectError,
    refetch: refetchProject,
  } = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => projectsApi.get(projectId),
  });

  // Documents fetch
  const {
    data: documents,
    isLoading: isDocsLoading,
    isError: isDocsError,
    error: docsError,
    refetch: refetchDocs,
  } = useQuery({
    queryKey: ["project-documents", projectId],
    queryFn: () => documentsApi.list(projectId),
    enabled: activeTab === "documents" || activeTab === "overview",
  });

  // Potential Changes fetch
  const {
    data: potentialChanges,
    isLoading: isChangesLoading,
    isError: isChangesError,
    error: changesError,
    refetch: refetchChanges,
  } = useQuery({
    queryKey: ["potential-changes", projectId],
    queryFn: () => potentialChangesApi.list(projectId),
    enabled: activeTab === "changes" || activeTab === "overview",
  });

  // Risks fetch
  const {
    data: risks,
    isLoading: isRisksLoading,
    isError: isRisksError,
    error: risksError,
    refetch: refetchRisks,
  } = useQuery({
    queryKey: ["risks", projectId],
    queryFn: () => risksApi.list(projectId),
    enabled: activeTab === "risks" || activeTab === "overview",
  });

  // Edit Project Modal state
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [editName, setEditName] = useState("");
  const [editClient, setEditClient] = useState("");
  const [editStatus, setEditStatus] = useState<ProjectStatus>("active");
  const [editValue, setEditValue] = useState("");
  const [editDesc, setEditDesc] = useState("");
  const [editError, setEditError] = useState<string | null>(null);

  const openEditModal = () => {
    if (!project) return;
    setEditName(project.name);
    setEditClient(project.client_name);
    setEditStatus(project.status);
    setEditValue(project.contract_value ?? "");
    setEditDesc(project.description ?? "");
    setEditError(null);
    setIsEditOpen(true);
  };

  const updateMutation = useMutation({
    mutationFn: (payload: ProjectUpdate) => projectsApi.update(projectId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project", projectId] });
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setIsEditOpen(false);
    },
    onError: (err) => setEditError(errorMessage(err, "Failed to update project.")),
  });

  const handleEditSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setEditError(null);
    updateMutation.mutate({
      name: editName.trim() || undefined,
      client_name: editClient.trim() || undefined,
      status: editStatus,
      contract_value: editValue.trim() || null,
      description: editDesc.trim() || null,
    });
  };

  // Upload Document Modal state
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadDocType, setUploadDocType] = useState("site_instruction");
  const [uploadAccess, setUploadAccess] = useState<"project" | "restricted">("project");
  const [uploadError, setUploadError] = useState<string | null>(null);

  const uploadMutation = useMutation({
    mutationFn: async () => {
      if (!uploadFile) throw new Error("Select a file to upload.");
      const form = new FormData();
      form.append("file", uploadFile);
      form.append("source", "web_upload");
      form.append("document_type", uploadDocType);
      form.append("access_level", uploadAccess);
      return documentsApi.upload(projectId, form);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["project-documents", projectId] });
      setIsUploadOpen(false);
      setUploadFile(null);
      setUploadError(null);
    },
    onError: (err) => setUploadError(errorMessage(err, "Upload failed.")),
  });

  // Risk Decision Modal state
  const [selectedRisk, setSelectedRisk] = useState<RiskItem | null>(null);
  const [riskAction, setRiskAction] = useState<"accept" | "dismiss" | "override">("accept");
  const [riskReason, setRiskReason] = useState("");
  const [overrideSeverity, setOverrideSeverity] = useState<RiskSeverity>("medium");
  const [overrideDays, setOverrideDays] = useState<string>("");
  const [riskDecisionError, setRiskDecisionError] = useState<string | null>(null);

  const riskDecisionMutation = useMutation({
    mutationFn: (payload: RiskDecisionInput) => risksApi.decide(projectId, selectedRisk!.id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["risks", projectId] });
      setSelectedRisk(null);
      setRiskReason("");
      setRiskDecisionError(null);
    },
    onError: (err) => setRiskDecisionError(errorMessage(err, "Failed to submit risk decision.")),
  });

  const handleRiskDecisionSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setRiskDecisionError(null);

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
      setRiskDecisionError(parsed.error.issues[0]?.message || "Invalid decision input.");
      return;
    }
    riskDecisionMutation.mutate(parsed.data);
  };

  // Create Change Order Modal state
  const [isCOModalOpen, setIsCOModalOpen] = useState(false);
  const [coRef, setCoRef] = useState("");
  const [coTitle, setCoTitle] = useState("");
  const [coDesc, setCoDesc] = useState("");
  const [coAmount, setCoAmount] = useState("");
  const [coCurrency, setCoCurrency] = useState("USD");
  const [coDays, setCoDays] = useState("");
  const [coError, setCoError] = useState<string | null>(null);

  const createCOMutation = useMutation({
    mutationFn: (payload: ChangeOrderCreateInput) => changeOrdersApi.create(projectId, payload),
    onSuccess: (order) => {
      queryClient.invalidateQueries({ queryKey: ["potential-changes", projectId] });
      setIsCOModalOpen(false);
      setCoRef("");
      setCoTitle("");
      setCoDesc("");
      setCoAmount("");
      setCoDays("");
      setCoError(null);
      alert(`Change Order ${order.reference} created successfully.`);
    },
    onError: (err) => setCoError(errorMessage(err, "Failed to create change order.")),
  });

  const handleCreateCOSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setCoError(null);

    const payload = {
      reference: coRef.trim().toUpperCase(),
      title: coTitle.trim(),
      description: coDesc.trim(),
      amount: coAmount.trim() || null,
      currency: coCurrency.trim().toUpperCase(),
      time_impact_days: coDays ? parseInt(coDays, 10) : null,
      evidence: [],
    };

    const parsed = changeOrderCreateSchema.safeParse(payload);
    if (!parsed.success) {
      setCoError(parsed.error.issues[0]?.message || "Invalid input.");
      return;
    }
    createCOMutation.mutate(parsed.data);
  };

  const statusTone = (status: ProjectStatus): "success" | "warning" | "neutral" | "danger" => {
    switch (status) {
      case "active":
        return "success";
      case "on_hold":
        return "warning";
      case "completed":
        return "neutral";
      default:
        return "danger";
    }
  };

  const docStatusTone = (s: string): "brand" | "success" | "warning" | "danger" | "neutral" => {
    switch (s) {
      case "completed":
      case "classified":
      case "linked":
        return "success";
      case "review_required":
        return "warning";
      case "failed":
      case "quarantined":
        return "danger";
      case "processing":
      case "extracted":
        return "brand";
      default:
        return "neutral";
    }
  };

  const riskSeverityTone = (s: string): "danger" | "warning" | "neutral" => {
    if (s === "critical" || s === "high") return "danger";
    if (s === "medium") return "warning";
    return "neutral";
  };

  if (isProjectLoading) {
    return (
      <ProtectedRoute>
        <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
          <LoadingSkeleton rows={5} variant="cards" />
        </div>
      </ProtectedRoute>
    );
  }

  if (isProjectError || !project) {
    return (
      <ProtectedRoute>
        <div className="mx-auto max-w-4xl px-4 py-12 flex flex-col gap-4">
          <ErrorState
            title="Project Unavailable"
            message={errorMessage(projectError, "Cannot find the requested project.")}
            onRetry={() => refetchProject()}
          />
          <Link href="/projects">
            <Button variant="secondary" size="sm">
              <IconArrowLeft className="size-4" />
              <span>Back to Projects</span>
            </Button>
          </Link>
        </div>
      </ProtectedRoute>
    );
  }

  const documentColumns: Column<DocumentItem>[] = [
    {
      key: "name",
      header: "File Name",
      render: (doc) => (
        <div className="flex items-center gap-2">
          <IconDocument className="size-4 text-brand shrink-0" />
          <span className="font-medium text-ink break-all">
            {doc.file_name || doc.filename || "Document"}
          </span>
        </div>
      ),
    },
    {
      key: "type",
      header: "Category",
      render: (doc) => (
        <span className="capitalize text-xs text-ink-muted">
          {(doc.document_type || doc.file_type || "general").replace("_", " ")}
        </span>
      ),
    },
    {
      key: "status",
      header: "Pipeline Status",
      render: (doc) => {
        const current = doc.processing_status || doc.status;
        return <Badge tone={docStatusTone(current)}>{current.replace("_", " ")}</Badge>;
      },
    },
    {
      key: "size",
      header: "Size",
      render: (doc) => {
        const bytes = doc.file_size || doc.size_bytes || 0;
        return (
          <span className="text-xs text-ink-muted tabular">
            {bytes > 1024 * 1024
              ? `${(bytes / (1024 * 1024)).toFixed(1)} MB`
              : `${Math.round(bytes / 1024)} KB`}
          </span>
        );
      },
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (doc) => {
        const docId = doc.document_id || doc.id;
        if (!docId) return null;
        return (
          <Button
            variant="ghost"
            size="sm"
            onClick={async () => {
              try {
                const url = await documentsApi.downloadUrl(docId);
                window.open(url, "_blank");
              } catch (e) {
                alert(errorMessage(e, "Cannot generate download link."));
              }
            }}
            title="Download original"
          >
            <IconDownload className="size-3.5" />
            <span className="sr-only">Download</span>
          </Button>
        );
      },
    },
  ];

  return (
    <ProtectedRoute>
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 flex flex-col gap-6">
        {/* Navigation Breadcrumb */}
        <div className="flex items-center gap-2 text-xs text-ink-muted">
          <Link href="/projects" className="hover:text-brand transition-colors">
            Projects
          </Link>
          <span>/</span>
          <span className="font-mono font-medium text-ink">{project.code}</span>
        </div>

        {/* Project Header Banner */}
        <div className="flex flex-col gap-4 rounded-[--radius-card] border border-border bg-surface p-6 shadow-card sm:flex-row sm:items-start sm:justify-between">
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-3">
              <span className="font-mono text-sm font-bold text-brand bg-brand-soft px-2.5 py-0.5 rounded">
                {project.code}
              </span>
              <h1 className="text-2xl font-bold tracking-tight text-ink">{project.name}</h1>
              <Badge tone={statusTone(project.status)}>
                {project.status.replace("_", " ")}
              </Badge>
            </div>
            <p className="text-sm text-ink-muted">
              Client: <span className="font-medium text-ink">{project.client_name}</span>
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {canUpdateProject ? (
              <Button variant="secondary" size="sm" onClick={openEditModal}>
                Edit Project
              </Button>
            ) : null}
            {canWriteChanges ? (
              <Button size="sm" onClick={() => setIsCOModalOpen(true)}>
                <IconPlus className="size-3.5" />
                <span>New Change Order</span>
              </Button>
            ) : null}
          </div>
        </div>

        {/* Tabs Bar */}
        <Tabs
          items={[
            { id: "overview", label: "Overview" },
            { id: "documents", label: "Documents", count: documents?.length },
            { id: "changes", label: "Potential Changes", count: potentialChanges?.length },
            { id: "risks", label: "Risks", count: risks?.length },
          ]}
          value={activeTab}
          onChange={setActiveTab}
        />

        {/* Tab 1: Overview */}
        {activeTab === "overview" && (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="md:col-span-2 flex flex-col gap-6">
              <Card>
                <CardHeader>
                  <CardTitle>Project Information</CardTitle>
                </CardHeader>
                <CardBody className="flex flex-col gap-4 text-sm">
                  <div>
                    <span className="text-xs font-semibold uppercase text-ink-muted">Scope & Description</span>
                    <p className="mt-1 text-ink leading-relaxed">
                      {project.description || "No project description recorded yet."}
                    </p>
                  </div>
                  <div className="grid grid-cols-2 gap-4 border-t border-border pt-4">
                    <div>
                      <span className="text-xs font-semibold uppercase text-ink-muted">Start Date</span>
                      <p className="text-ink font-medium mt-0.5">{project.start_date || "Not specified"}</p>
                    </div>
                    <div>
                      <span className="text-xs font-semibold uppercase text-ink-muted">Target Completion</span>
                      <p className="text-ink font-medium mt-0.5">{project.expected_end_date || "Not specified"}</p>
                    </div>
                  </div>
                </CardBody>
              </Card>

              {/* Stakeholders Card */}
              <Card>
                <CardHeader>
                  <CardTitle>Stakeholders</CardTitle>
                </CardHeader>
                <CardBody>
                  {project.stakeholders && project.stakeholders.length > 0 ? (
                    <div className="flex flex-wrap gap-2">
                      {project.stakeholders.map((s, i) => (
                        <Badge key={i} tone="neutral" className="text-xs py-1 px-3">
                          {s}
                        </Badge>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-ink-muted">No external stakeholders logged.</p>
                  )}
                </CardBody>
              </Card>
            </div>

            {/* Financial & Summary Sidebar */}
            <div className="flex flex-col gap-6">
              <Card>
                <CardHeader>
                  <CardTitle>Commercial Baseline</CardTitle>
                </CardHeader>
                <CardBody className="flex flex-col gap-4">
                  <div>
                    <span className="text-xs text-ink-muted">Original Contract Sum</span>
                    <p className="text-2xl font-bold text-ink tabular mt-0.5">
                      {project.contract_value
                        ? `${Number(project.contract_value).toLocaleString("en-US", {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 2,
                          })} ${project.currency}`
                        : "—"}
                    </p>
                  </div>
                  <div className="border-t border-border pt-3 flex flex-col gap-2">
                    <div className="flex justify-between text-xs">
                      <span className="text-ink-muted">Documents Linked:</span>
                      <span className="font-semibold text-ink">{documents?.length ?? "..."}</span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-ink-muted">Potential Changes:</span>
                      <span className="font-semibold text-ink">{potentialChanges?.length ?? "..."}</span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-ink-muted">Active Risks:</span>
                      <span className="font-semibold text-ink">{risks?.length ?? "..."}</span>
                    </div>
                  </div>
                </CardBody>
              </Card>
            </div>
          </div>
        )}

        {/* Tab 2: Documents */}
        {activeTab === "documents" && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold text-ink">Project Document Registry</h2>
                <p className="text-xs text-ink-muted">
                  Contracts, site instructions, RFIs, notices, and payment applications
                </p>
              </div>
              {canWriteDocs ? (
                <Button size="sm" onClick={() => setIsUploadOpen(true)}>
                  <IconUpload className="size-3.5" />
                  <span>Upload Document</span>
                </Button>
              ) : null}
            </div>

            {isDocsLoading ? (
              <LoadingSkeleton rows={4} variant="table" />
            ) : isDocsError ? (
              <ErrorState
                title="Failed to Load Documents"
                message={errorMessage(docsError, "Cannot read project documents.")}
                onRetry={() => refetchDocs()}
              />
            ) : documents && documents.length > 0 ? (
              <DataTable
                caption="Project document repository"
                captionHidden
                columns={documentColumns}
                rows={documents}
                rowKey={(doc) => doc.document_id || doc.id || Math.random().toString()}
              />
            ) : (
              <EmptyState
                title="No documents uploaded yet"
                description="Upload construction contracts, site photos, variation notices or RFIs to begin automated substantiation."
                action={
                  canWriteDocs ? (
                    <Button size="sm" onClick={() => setIsUploadOpen(true)}>
                      <IconUpload className="size-3.5" />
                      <span>Upload Document</span>
                    </Button>
                  ) : undefined
                }
              />
            )}
          </div>
        )}

        {/* Tab 3: Potential Changes */}
        {activeTab === "changes" && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold text-ink">Potential Construction Changes</h2>
                <p className="text-xs text-ink-muted">
                  Variances detected across documents, drawings, and site records requiring human review
                </p>
              </div>
              {canWriteChanges ? (
                <Button size="sm" onClick={() => setIsCOModalOpen(true)}>
                  <IconPlus className="size-3.5" />
                  <span>New Change Order</span>
                </Button>
              ) : null}
            </div>

            {isChangesLoading ? (
              <LoadingSkeleton rows={3} variant="cards" />
            ) : isChangesError ? (
              <ErrorState
                title="Failed to Load Potential Changes"
                message={errorMessage(changesError, "Could not fetch detected changes.")}
                onRetry={() => refetchChanges()}
              />
            ) : potentialChanges && potentialChanges.length > 0 ? (
              <div className="grid gap-4 sm:grid-cols-2">
                {potentialChanges.map((change) => (
                  <Card key={change.id} className="flex flex-col justify-between">
                    <CardHeader>
                      <div className="flex items-center justify-between gap-2 w-full">
                        <span className="text-xs font-mono font-semibold uppercase text-brand">
                          {change.event_type}
                        </span>
                        <Badge tone={change.human_review_required ? "warning" : "neutral"}>
                          {change.human_review_required ? "Review Required" : "Audited"}
                        </Badge>
                      </div>
                      <CardTitle className="mt-1 text-sm">{change.title}</CardTitle>
                    </CardHeader>
                    <CardBody className="flex flex-col gap-3 text-xs">
                      <p className="text-ink leading-relaxed">{change.description}</p>
                      <div className="grid grid-cols-2 gap-2 border-t border-border pt-2 text-ink-muted">
                        <div>
                          <span>Est. Cost Impact:</span>
                          <p className="font-semibold text-ink tabular">
                            {change.suggested_cost_impact
                              ? `${Number(change.suggested_cost_impact).toLocaleString()} ${change.suggested_currency}`
                              : "TBD"}
                          </p>
                        </div>
                        <div>
                          <span>Est. Schedule Impact:</span>
                          <p className="font-semibold text-ink">
                            {change.suggested_schedule_impact !== null
                              ? `${change.suggested_schedule_impact} days`
                              : "TBD"}
                          </p>
                        </div>
                      </div>
                      {canWriteChanges ? (
                        <div className="mt-2 pt-2 border-t border-border flex justify-end">
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => {
                              setCoTitle(`CO: ${change.title}`);
                              setCoDesc(change.description);
                              setCoAmount(change.suggested_cost_impact || "");
                              setCoDays(
                                change.suggested_schedule_impact
                                  ? String(change.suggested_schedule_impact)
                                  : "",
                              );
                              setIsCOModalOpen(true);
                            }}
                          >
                            Convert to Change Order &rarr;
                          </Button>
                        </div>
                      ) : null}
                    </CardBody>
                  </Card>
                ))}
              </div>
            ) : (
              <EmptyState
                title="No potential changes detected"
                description="The evidence links have not identified unapproved scope variances or cost deviations."
              />
            )}
          </div>
        )}

        {/* Tab 4: Risks */}
        {activeTab === "risks" && (
          <div className="flex flex-col gap-4">
            <div>
              <h2 className="text-base font-semibold text-ink">Commercial & Programme Risks</h2>
              <p className="text-xs text-ink-muted">
                Identified commercial exposures and schedule risks subject to audited human review
              </p>
            </div>

            {isRisksLoading ? (
              <LoadingSkeleton rows={3} variant="cards" />
            ) : isRisksError ? (
              <ErrorState
                title="Failed to Load Risks"
                message={errorMessage(risksError, "Cannot read project risks.")}
                onRetry={() => refetchRisks()}
              />
            ) : risks && risks.length > 0 ? (
              <div className="grid gap-4 sm:grid-cols-2">
                {risks.map((risk) => (
                  <Card key={risk.id} className="flex flex-col justify-between">
                    <CardHeader>
                      <div className="flex items-center justify-between w-full">
                        <Badge tone={riskSeverityTone(risk.severity)}>
                          {risk.severity.toUpperCase()}
                        </Badge>
                        <span className="text-[11px] font-mono text-ink-muted">
                          Status: {risk.status}
                        </span>
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
                      {canAcceptRisks && risk.status !== "accepted" && risk.status !== "dismissed" ? (
                        <div className="mt-2 pt-2 border-t border-border flex justify-end">
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => {
                              setSelectedRisk(risk);
                              setRiskAction("accept");
                              setRiskReason("");
                              setOverrideSeverity((risk.severity as RiskSeverity) || "medium");
                              setOverrideDays(
                                risk.schedule_impact_days ? String(risk.schedule_impact_days) : "",
                              );
                              setRiskDecisionError(null);
                            }}
                          >
                            Decide on Risk &rarr;
                          </Button>
                        </div>
                      ) : null}
                    </CardBody>
                  </Card>
                ))}
              </div>
            ) : (
              <EmptyState
                title="No active risks logged"
                description="All risk items for this project have either been resolved or no high-exposure issues are detected."
              />
            )}
          </div>
        )}

        {/* Edit Project Modal */}
        <Modal
          open={isEditOpen}
          title="Edit Project Details"
          onClose={() => setIsEditOpen(false)}
          actions={
            <>
              <Button variant="ghost" size="sm" onClick={() => setIsEditOpen(false)}>
                Cancel
              </Button>
              <Button
                size="sm"
                type="submit"
                form="edit-project-form"
                loading={updateMutation.isPending}
              >
                Save Changes
              </Button>
            </>
          }
        >
          <form id="edit-project-form" onSubmit={handleEditSubmit} className="flex flex-col gap-3">
            {editError ? (
              <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft p-2.5 text-xs text-danger">
                {editError}
              </div>
            ) : null}

            <Field id="edit-name" label="Project Name" required>
              <Input
                id="edit-name"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                required
              />
            </Field>

            <Field id="edit-client" label="Client Name" required>
              <Input
                id="edit-client"
                value={editClient}
                onChange={(e) => setEditClient(e.target.value)}
                required
              />
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field id="edit-status" label="Status">
                <Select
                  id="edit-status"
                  value={editStatus}
                  onChange={(e) => setEditStatus(e.target.value as ProjectStatus)}
                >
                  <option value="active">Active</option>
                  <option value="on_hold">On Hold</option>
                  <option value="completed">Completed</option>
                  <option value="cancelled">Cancelled</option>
                  <option value="archived">Archived</option>
                </Select>
              </Field>

              <Field id="edit-val" label="Contract Value">
                <Input
                  id="edit-val"
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  placeholder="1000000.00"
                />
              </Field>
            </div>

            <Field id="edit-desc" label="Description">
              <Input
                id="edit-desc"
                value={editDesc}
                onChange={(e) => setEditDesc(e.target.value)}
              />
            </Field>
          </form>
        </Modal>

        {/* Upload Document Modal */}
        <Modal
          open={isUploadOpen}
          title="Upload Project Document"
          onClose={() => setIsUploadOpen(false)}
          actions={
            <>
              <Button variant="ghost" size="sm" onClick={() => setIsUploadOpen(false)}>
                Cancel
              </Button>
              <Button
                size="sm"
                type="submit"
                form="upload-doc-form"
                loading={uploadMutation.isPending}
                disabled={!uploadFile}
              >
                Upload File
              </Button>
            </>
          }
        >
          <form id="upload-doc-form" onSubmit={(e) => { e.preventDefault(); uploadMutation.mutate(); }} className="flex flex-col gap-3.5">
            {uploadError ? (
              <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft p-2.5 text-xs text-danger">
                {uploadError}
              </div>
            ) : null}

            <Field id="upload-file" label="Select Document File" required>
              <Input
                id="upload-file"
                type="file"
                onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                required
                className="py-1.5"
              />
            </Field>

            <Field id="upload-type" label="Document Classification Type">
              <Select
                id="upload-type"
                value={uploadDocType}
                onChange={(e) => setUploadDocType(e.target.value)}
              >
                <option value="contract">Prime Contract / Agreement</option>
                <option value="variation_notice">Variation Notice</option>
                <option value="site_instruction">Site Instruction (SI)</option>
                <option value="rfi">Request for Information (RFI)</option>
                <option value="site_photo">Site Photo / Visual Record</option>
                <option value="payment_application">Payment Application / Invoice</option>
              </Select>
            </Field>

            <Field id="upload-access" label="Access Level">
              <Select
                id="upload-access"
                value={uploadAccess}
                onChange={(e) => setUploadAccess(e.target.value as "project" | "restricted")}
              >
                <option value="project">Project Team (Visible to all project members)</option>
                <option value="restricted">Restricted (Commercial Managers / Admins only)</option>
              </Select>
            </Field>
          </form>
        </Modal>

        {/* Risk Decision Modal */}
        <Modal
          open={selectedRisk !== null}
          title={`Risk Decision: ${selectedRisk?.title ?? ""}`}
          onClose={() => setSelectedRisk(null)}
          actions={
            <>
              <Button variant="ghost" size="sm" onClick={() => setSelectedRisk(null)}>
                Cancel
              </Button>
              <Button
                size="sm"
                type="submit"
                form="risk-decision-form"
                loading={riskDecisionMutation.isPending}
              >
                Confirm Decision
              </Button>
            </>
          }
        >
          <form id="risk-decision-form" onSubmit={handleRiskDecisionSubmit} className="flex flex-col gap-3">
            {riskDecisionError ? (
              <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft p-2.5 text-xs text-danger">
                {riskDecisionError}
              </div>
            ) : null}

            <Field id="risk-act" label="Action" required>
              <Select
                id="risk-act"
                value={riskAction}
                onChange={(e) => setRiskAction(e.target.value as "accept" | "dismiss" | "override")}
              >
                <option value="accept">Accept Risk (Acknowledge and proceed)</option>
                <option value="dismiss">Dismiss (Deem not applicable)</option>
                <option value="override">Override (Change severity or schedule effect)</option>
              </Select>
            </Field>

            {riskAction === "override" ? (
              <div className="grid grid-cols-2 gap-3 p-3 bg-subtle rounded-lg">
                <Field id="ov-sev" label="Revised Severity">
                  <Select
                    id="ov-sev"
                    value={overrideSeverity}
                    onChange={(e) => setOverrideSeverity(e.target.value as RiskSeverity)}
                  >
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                  </Select>
                </Field>

                <Field id="ov-days" label="Revised Schedule (Days)">
                  <Input
                    id="ov-days"
                    type="number"
                    value={overrideDays}
                    onChange={(e) => setOverrideDays(e.target.value)}
                    placeholder="0"
                  />
                </Field>
              </div>
            ) : null}

            <Field id="risk-reason" label="Audited Reason" hint="Mandatory justification recorded in audit log" required>
              <Input
                id="risk-reason"
                value={riskReason}
                onChange={(e) => setRiskReason(e.target.value)}
                placeholder="State the commercial justification..."
                required
              />
            </Field>
          </form>
        </Modal>

        {/* Create Change Order Modal */}
        <Modal
          open={isCOModalOpen}
          title="Create Change Order"
          onClose={() => setIsCOModalOpen(false)}
          actions={
            <>
              <Button variant="ghost" size="sm" onClick={() => setIsCOModalOpen(false)}>
                Cancel
              </Button>
              <Button
                size="sm"
                type="submit"
                form="create-co-form"
                loading={createCOMutation.isPending}
              >
                Create Change Order
              </Button>
            </>
          }
        >
          <form id="create-co-form" onSubmit={handleCreateCOSubmit} className="flex flex-col gap-3">
            {coError ? (
              <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft p-2.5 text-xs text-danger">
                {coError}
              </div>
            ) : null}

            <Field id="co-ref" label="Reference Code" hint="Unique change order reference, e.g. CO-001" required>
              <Input
                id="co-ref"
                value={coRef}
                onChange={(e) => setCoRef(e.target.value.toUpperCase())}
                placeholder="CO-001"
                required
              />
            </Field>

            <Field id="co-title" label="Title" required>
              <Input
                id="co-title"
                value={coTitle}
                onChange={(e) => setCoTitle(e.target.value)}
                placeholder="Foundations re-engineering variance"
                required
              />
            </Field>

            <div className="grid grid-cols-3 gap-3">
              <div className="col-span-2">
                <Field id="co-amt" label="Amount">
                  <Input
                    id="co-amt"
                    value={coAmount}
                    onChange={(e) => setCoAmount(e.target.value)}
                    placeholder="45000.00"
                  />
                </Field>
              </div>
              <Field id="co-curr" label="Currency">
                <Input
                  id="co-curr"
                  value={coCurrency}
                  onChange={(e) => setCoCurrency(e.target.value.toUpperCase())}
                  maxLength={3}
                />
              </Field>
            </div>

            <Field id="co-days" label="Time Impact (Calendar Days)">
              <Input
                id="co-days"
                type="number"
                value={coDays}
                onChange={(e) => setCoDays(e.target.value)}
                placeholder="14"
              />
            </Field>

            <Field id="co-desc" label="Description / Rationale">
              <Input
                id="co-desc"
                value={coDesc}
                onChange={(e) => setCoDesc(e.target.value)}
                placeholder="Contractual basis for claim..."
              />
            </Field>
          </form>
        </Modal>
      </div>
    </ProtectedRoute>
  );
}

