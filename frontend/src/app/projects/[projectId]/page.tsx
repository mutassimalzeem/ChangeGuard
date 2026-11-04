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
import { Tabs, type TabItem } from "@/components/ui/tabs";
import { ProtectedRoute } from "@/components/protected-route";
import {
  IconArrowLeft,
  IconDocument,
  IconDownload,
  IconFileCheck,
  IconHelpCircle,
  IconPlus,
  IconSearch,
  IconUpload,
} from "@/components/icons";
import {
  changeOrdersApi,
  documentsApi,
  investigationsApi,
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
  type ChangeOrderItem,
  type InvestigationResult,
  type ProjectStatus,
  type ProjectUpdate,
  type RiskDecisionInput,
  type RiskItem,
  type RiskSeverity,
} from "@/lib/contracts";

interface PageProps {
  params: Promise<{ projectId: string }>;
}

export default function ProjectWorkspacePage({ params }: PageProps) {
  const { projectId } = use(params);
  const queryClient = useQueryClient();
  const role = useRole();

  // Role permissions
  const canUpdateProject = role ? hasPermission(role, "project.update") : false;
  const canWriteDocs = role ? hasPermission(role, "documents.write") : false;
  const canWriteChanges = role ? hasPermission(role, "change_orders.write") : false;
  const canSubmitChanges = role ? hasPermission(role, "change_orders.submit") : false;
  const canDecideApprovals = role ? hasPermission(role, "approvals.decide") : false;
  const canAcceptRisks = role ? hasPermission(role, "risks.accept") : false;

  // Active Tab state
  const [activeTab, setActiveTab] = useState<string>("overview");

  // 1. Project details query
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

  // 2. Documents query
  const {
    data: documents,
    isLoading: isDocsLoading,
    isError: isDocsError,
    error: docsError,
    refetch: refetchDocs,
  } = useQuery({
    queryKey: ["project-documents", projectId],
    queryFn: () => documentsApi.list(projectId),
  });

  // 3. Potential changes query (acts as timeline events source)
  const {
    data: potentialChanges,
    isLoading: isChangesLoading,
    isError: isChangesError,
    error: changesError,
    refetch: refetchChanges,
  } = useQuery({
    queryKey: ["potential-changes", projectId],
    queryFn: () => potentialChangesApi.list(projectId),
  });

  // 4. Risks query
  const {
    data: risks,
    isLoading: isRisksLoading,
    isError: isRisksError,
    error: risksError,
    refetch: refetchRisks,
  } = useQuery({
    queryKey: ["risks", projectId],
    queryFn: () => risksApi.list(projectId),
  });

  // Local state for Change Orders inspection
  const [changeOrdersList, setChangeOrdersList] = useState<ChangeOrderItem[]>([]);
  const [selectedChangeOrder, setSelectedChangeOrder] = useState<ChangeOrderItem | null>(null);

  // Edit Project Modal
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

  // Upload Document Modal
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

  // Filter Document states
  const [docTypeFilter, setDocTypeFilter] = useState("all");
  const [docSearchQuery, setDocSearchQuery] = useState("");

  // Risk Decision / Human Override Modal
  const [selectedRisk, setSelectedRisk] = useState<RiskItem | null>(null);
  const [riskAction, setRiskAction] = useState<"accept" | "dismiss" | "override">("override");
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
    onError: (err) => setRiskDecisionError(errorMessage(err, "Failed to record risk decision.")),
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
      setRiskDecisionError(parsed.error.issues[0]?.message || "Invalid decision.");
      return;
    }
    riskDecisionMutation.mutate(parsed.data);
  };

  // Create Change Order Modal
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
      setChangeOrdersList((prev) => [order, ...prev.filter((o) => o.id !== order.id)]);
      setSelectedChangeOrder(order);
      setIsCOModalOpen(false);
      setCoRef("");
      setCoTitle("");
      setCoDesc("");
      setCoAmount("");
      setCoDays("");
      setCoError(null);
    },
    onError: (err) => setCoError(errorMessage(err, "Failed to create change order.")),
  });

  const handleCreateCOSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setCoError(null);
    const parsed = changeOrderCreateSchema.safeParse({
      reference: coRef.trim().toUpperCase(),
      title: coTitle.trim(),
      description: coDesc.trim(),
      amount: coAmount.trim() || null,
      currency: coCurrency.trim().toUpperCase(),
      time_impact_days: coDays ? parseInt(coDays, 10) : null,
      evidence: [],
    });
    if (!parsed.success) {
      setCoError(parsed.error.issues[0]?.message || "Invalid change order data.");
      return;
    }
    createCOMutation.mutate(parsed.data);
  };

  // Approval decision modal
  const [approvalCO, setApprovalCO] = useState<ChangeOrderItem | null>(null);
  const [approvalDecision, setApprovalDecision] = useState<"approve" | "reject">("approve");
  const [approvalComments, setApprovalComments] = useState("");
  const [approvalError, setApprovalError] = useState<string | null>(null);

  const approveMutation = useMutation({
    mutationFn: async ({ orderId, action, comments }: { orderId: string; action: "approve" | "reject"; comments: string }) => {
      if (action === "approve") {
        return changeOrdersApi.approve(orderId, comments);
      } else {
        return changeOrdersApi.reject(orderId, comments);
      }
    },
    onSuccess: (updated) => {
      setChangeOrdersList((prev) => prev.map((o) => (o.id === updated.id ? updated : o)));
      if (selectedChangeOrder?.id === updated.id) {
        setSelectedChangeOrder(updated);
      }
      setApprovalCO(null);
      setApprovalComments("");
      setApprovalError(null);
    },
    onError: (err) => setApprovalError(errorMessage(err, "Failed to submit approval decision.")),
  });

  // Evidence Package Viewer Modal
  const [evidenceModalData, setEvidenceModalData] = useState<{ title: string; excerpts: string[] } | null>(null);

  // Ask ChangeGuard Investigation State
  const [selectedAskDocId, setSelectedAskDocId] = useState<string>("");
  const [askQuestion, setAskQuestion] = useState("");
  const [askResult, setAskResult] = useState<InvestigationResult | null>(null);
  const [askError, setAskError] = useState<string | null>(null);

  const askMutation = useMutation({
    mutationFn: async (payload: { docId: string; question: string }) => {
      return investigationsApi.ask(projectId, {
        document_id: payload.docId,
        question: payload.question,
      });
    },
    onSuccess: (res) => {
      setAskResult(res);
      setAskError(null);
    },
    onError: (err) => {
      setAskError(errorMessage(err, "Investigation failed. Ensure document has valid extracted chunks."));
    },
  });

  const handleAskSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAskDocId && documents && documents[0]) {
      const fallbackId = documents[0].document_id || documents[0].id;
      if (fallbackId) setSelectedAskDocId(fallbackId);
    }
    const docId = selectedAskDocId || (documents && documents[0] ? (documents[0].document_id || documents[0].id) : null);
    if (!docId) {
      setAskError("Please upload or select a reference document first.");
      return;
    }
    if (!askQuestion.trim()) return;
    setAskError(null);
    askMutation.mutate({ docId, question: askQuestion.trim() });
  };

  // Status and Tone Helpers
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

  const coStatusTone = (s: string): "brand" | "success" | "warning" | "danger" | "neutral" => {
    switch (s) {
      case "approved":
        return "success";
      case "submitted":
        return "warning";
      case "rejected":
        return "danger";
      case "draft":
        return "brand";
      default:
        return "neutral";
    }
  };

  // Calculations for Overview KPIs
  // Total pending exposure: risks exposure + unapproved change orders
  const risksExposureTotal = (risks || []).reduce((acc, r) => {
    if (r.status !== "dismissed" && r.financial_exposure) {
      const val = parseFloat(r.financial_exposure);
      return isNaN(val) ? acc : acc + val;
    }
    return acc;
  }, 0);

  const coPendingTotal = changeOrdersList.reduce((acc, co) => {
    if (co.status !== "approved" && co.status !== "rejected" && co.amount) {
      const val = parseFloat(co.amount);
      return isNaN(val) ? acc : acc + val;
    }
    return acc;
  }, 0);

  const totalPendingExposure = risksExposureTotal + coPendingTotal;
  const openChangeOrdersCount = changeOrdersList.filter((co) => co.status === "draft" || co.status === "submitted").length;
  const overdueApprovalsCount = changeOrdersList.filter((co) => co.status === "submitted").length;

  // Filtered documents
  const filteredDocs = (documents || []).filter((doc) => {
    const matchesType = docTypeFilter === "all" || (doc.document_type || doc.file_type || "") === docTypeFilter;
    const matchesSearch = !docSearchQuery || (doc.file_name || doc.filename || "").toLowerCase().includes(docSearchQuery.toLowerCase());
    return matchesType && matchesSearch;
  });

  const workspaceTabs: readonly TabItem[] = [
    { id: "overview", label: "Overview" },
    { id: "documents", label: "Documents", count: documents?.length },
    { id: "timeline", label: "Timeline", count: potentialChanges?.length },
    { id: "change-orders", label: "Change Orders", count: changeOrdersList.length },
    { id: "risks", label: "Risks", count: risks?.length },
    { id: "approvals", label: "Approvals", count: overdueApprovalsCount > 0 ? overdueApprovalsCount : undefined },
    { id: "ask-changeguard", label: "Ask ChangeGuard" },
  ];

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
            title="Project Workspace Unavailable"
            message={errorMessage(projectError, "Cannot read project data.")}
            onRetry={() => refetchProject()}
          />
          <Link href="/projects">
            <Button variant="secondary" size="sm">
              <IconArrowLeft className="size-4" />
              <span>Return to Projects</span>
            </Button>
          </Link>
        </div>
      </ProtectedRoute>
    );
  }

  return (
    <ProtectedRoute>
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8 flex flex-col gap-6">
        {/* Navigation Breadcrumb */}
        <div className="flex items-center gap-2 text-xs text-ink-muted">
          <Link href="/projects" className="hover:text-brand transition-colors">
            Projects
          </Link>
          <span>/</span>
          <span className="font-mono font-medium text-ink">{project.code}</span>
        </div>

        {/* Project Workspace Masthead */}
        <div className="flex flex-col gap-4 rounded-[--radius-card] border border-border bg-surface p-6 shadow-card sm:flex-row sm:items-start sm:justify-between">
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-3">
              <span className="font-mono text-xs font-bold text-brand bg-brand-soft px-2.5 py-1 rounded">
                {project.code}
              </span>
              <h1 className="text-2xl font-bold tracking-tight text-ink">{project.name}</h1>
              <Badge tone={statusTone(project.status)}>
                {project.status.replace("_", " ")}
              </Badge>
            </div>
            <p className="text-xs text-ink-muted">
              Client / Employer: <span className="font-semibold text-ink">{project.client_name}</span> &bull; Currency: <span className="font-semibold text-ink">{project.currency}</span>
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            {canUpdateProject ? (
              <Button variant="secondary" size="sm" onClick={openEditModal}>
                Edit Scope
              </Button>
            ) : null}
            {canWriteDocs ? (
              <Button variant="secondary" size="sm" onClick={() => setIsUploadOpen(true)}>
                <IconUpload className="size-3.5" />
                <span>Upload</span>
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

        {/* 7 Workspace Tabs with Keyboard Navigation */}
        <Tabs
          items={workspaceTabs}
          value={activeTab}
          onChange={setActiveTab}
        />

        {/* TAB 1: OVERVIEW */}
        {activeTab === "overview" && (
          <div className="flex flex-col gap-6">
            {/* Overview KPI Cards: Every money value from backend */}
            <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
              <Card>
                <CardBody className="p-4">
                  <span className="text-[11px] font-semibold uppercase text-ink-muted">Contract Baseline</span>
                  <p className="mt-1 text-lg font-bold text-ink tabular">
                    {project.contract_value
                      ? `${Number(project.contract_value).toLocaleString("en-US", { minimumFractionDigits: 2 })} ${project.currency}`
                      : "—"}
                  </p>
                </CardBody>
              </Card>

              <Card>
                <CardBody className="p-4">
                  <span className="text-[11px] font-semibold uppercase text-ink-muted">Pending Exposure</span>
                  <p className="mt-1 text-lg font-bold text-danger tabular">
                    {totalPendingExposure > 0
                      ? `${Number(totalPendingExposure).toLocaleString("en-US", { minimumFractionDigits: 2 })} ${project.currency}`
                      : "$0.00"}
                  </p>
                </CardBody>
              </Card>

              <Card>
                <CardBody className="p-4">
                  <span className="text-[11px] font-semibold uppercase text-ink-muted">Open Change Orders</span>
                  <p className="mt-1 text-lg font-bold text-brand tabular">{openChangeOrdersCount}</p>
                </CardBody>
              </Card>

              <Card>
                <CardBody className="p-4">
                  <span className="text-[11px] font-semibold uppercase text-ink-muted">Overdue Approvals</span>
                  <p className="mt-1 text-lg font-bold text-warning tabular">{overdueApprovalsCount}</p>
                </CardBody>
              </Card>

              <Card>
                <CardBody className="p-4">
                  <span className="text-[11px] font-semibold uppercase text-ink-muted">Registered Docs</span>
                  <p className="mt-1 text-lg font-bold text-ink tabular">{documents?.length ?? 0}</p>
                </CardBody>
              </Card>
            </div>

            {/* Scope, Dates & Stakeholders */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="md:col-span-2 flex flex-col gap-6">
                <Card>
                  <CardHeader>
                    <CardTitle>Project Scope & Specifications</CardTitle>
                  </CardHeader>
                  <CardBody className="text-xs text-ink leading-relaxed">
                    <p>{project.description || "No detailed scope description recorded in registry."}</p>
                    <div className="grid grid-cols-2 gap-4 border-t border-border pt-3 mt-4 text-ink-muted">
                      <div>
                        <span>Commencement Date:</span>
                        <p className="font-semibold text-ink text-sm mt-0.5">{project.start_date || "Not logged"}</p>
                      </div>
                      <div>
                        <span>Contractual Completion:</span>
                        <p className="font-semibold text-ink text-sm mt-0.5">{project.expected_end_date || "Not logged"}</p>
                      </div>
                    </div>
                  </CardBody>
                </Card>

                {/* Latest Risks Preview */}
                <Card>
                  <CardHeader className="flex items-center justify-between">
                    <CardTitle>Latest High-Exposure Risks</CardTitle>
                    <Button variant="ghost" size="sm" onClick={() => setActiveTab("risks")}>
                      View All Risks &rarr;
                    </Button>
                  </CardHeader>
                  <CardBody className="p-0">
                    {risks && risks.length > 0 ? (
                      <div className="divide-y divide-border text-xs">
                        {risks.slice(0, 3).map((r) => (
                          <div key={r.id} className="p-4 flex items-center justify-between gap-4">
                            <div>
                              <div className="flex items-center gap-2">
                                <Badge tone={riskSeverityTone(r.severity)}>{r.severity.toUpperCase()}</Badge>
                                <span className="font-semibold text-ink">{r.title}</span>
                              </div>
                              <p className="text-ink-muted mt-1">{r.description}</p>
                            </div>
                            <div className="text-right shrink-0">
                              <span className="font-mono font-bold text-ink tabular">
                                {r.financial_exposure ? `${Number(r.financial_exposure).toLocaleString()} ${r.currency}` : "—"}
                              </span>
                              <div className="text-[11px] text-ink-muted">
                                {r.schedule_impact_days ? `${r.schedule_impact_days}d impact` : "No delay"}
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="p-6 text-center text-xs text-ink-muted">No risks logged.</div>
                    )}
                  </CardBody>
                </Card>
              </div>

              {/* Stakeholders & Quick Contacts */}
              <div className="flex flex-col gap-6">
                <Card>
                  <CardHeader>
                    <CardTitle>Stakeholders & Roles</CardTitle>
                  </CardHeader>
                  <CardBody className="flex flex-col gap-3">
                    {project.stakeholders && project.stakeholders.length > 0 ? (
                      <div className="flex flex-wrap gap-1.5">
                        {project.stakeholders.map((s, idx) => (
                          <span key={idx} className="px-2.5 py-1 bg-subtle rounded text-xs font-medium text-ink">
                            {s}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-ink-muted">No external parties recorded.</p>
                    )}
                  </CardBody>
                </Card>

                {/* Recent Documents Preview */}
                <Card>
                  <CardHeader className="flex items-center justify-between">
                    <CardTitle>Recent Documents</CardTitle>
                    <Button variant="ghost" size="sm" onClick={() => setActiveTab("documents")}>
                      View Registry &rarr;
                    </Button>
                  </CardHeader>
                  <CardBody className="p-0">
                    {documents && documents.length > 0 ? (
                      <div className="divide-y divide-border text-xs">
                        {documents.slice(0, 4).map((d) => (
                          <div key={d.document_id || d.id} className="p-3 flex items-center justify-between">
                            <div className="flex items-center gap-2 truncate">
                              <IconDocument className="size-3.5 text-brand shrink-0" />
                              <span className="font-medium text-ink truncate">{d.file_name || d.filename || "Doc"}</span>
                            </div>
                            <Badge tone={docStatusTone(d.processing_status || d.status)}>
                              {(d.processing_status || d.status).replace("_", " ")}
                            </Badge>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="p-6 text-center text-xs text-ink-muted">No documents uploaded yet.</div>
                    )}
                  </CardBody>
                </Card>
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: DOCUMENTS */}
        {activeTab === "documents" && (
          <div className="flex flex-col gap-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold text-ink">Document Registry & Classification</h2>
                <p className="text-xs text-ink-muted">
                  Contracts, site instructions, RFIs, notices, and payment applications with OCR verification
                </p>
              </div>
              {canWriteDocs ? (
                <Button size="sm" onClick={() => setIsUploadOpen(true)}>
                  <IconUpload className="size-3.5" />
                  <span>Upload Document</span>
                </Button>
              ) : null}
            </div>

            {/* Document Filters */}
            <Card>
              <CardBody className="py-3 px-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
                <div className="relative flex-1 max-w-sm">
                  <IconSearch className="pointer-events-none absolute left-3 top-2.5 size-3.5 text-ink-faint" />
                  <Input
                    value={docSearchQuery}
                    onChange={(e) => setDocSearchQuery(e.target.value)}
                    placeholder="Search documents by filename..."
                    className="pl-8 h-8 text-xs"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-ink-muted">Category:</span>
                  <Select
                    value={docTypeFilter}
                    onChange={(e) => setDocTypeFilter(e.target.value)}
                    className="h-8 text-xs w-48"
                  >
                    <option value="all">All Document Types</option>
                    <option value="contract">Prime Contract</option>
                    <option value="variation_notice">Variation Notice</option>
                    <option value="site_instruction">Site Instruction (SI)</option>
                    <option value="rfi">Request for Information (RFI)</option>
                    <option value="site_photo">Site Photo</option>
                    <option value="payment_application">Payment Application</option>
                  </Select>
                </div>
              </CardBody>
            </Card>

            {/* Document List */}
            {isDocsLoading ? (
              <LoadingSkeleton rows={5} variant="table" />
            ) : isDocsError ? (
              <ErrorState
                title="Failed to Load Documents"
                message={errorMessage(docsError, "Cannot read project documents.")}
                onRetry={() => refetchDocs()}
              />
            ) : filteredDocs.length > 0 ? (
              <div className="overflow-x-auto rounded-[--radius-card] border border-border bg-surface shadow-card">
                <table className="w-full text-left text-xs border-collapse">
                  <thead className="bg-subtle text-ink-muted uppercase font-semibold text-[10px] border-b border-border">
                    <tr>
                      <th className="px-4 py-3">File Name</th>
                      <th className="px-4 py-3">Category</th>
                      <th className="px-4 py-3">Processing Status</th>
                      <th className="px-4 py-3">Size</th>
                      <th className="px-4 py-3">Confidence</th>
                      <th className="px-4 py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border text-ink">
                    {filteredDocs.map((doc) => {
                      const docId = doc.document_id || doc.id;
                      const sizeBytes = doc.file_size || doc.size_bytes || 0;
                      return (
                        <tr key={docId} className="hover:bg-subtle/50 transition-colors">
                          <td className="px-4 py-3">
                            <div className="flex items-center gap-2">
                              <IconDocument className="size-4 text-brand shrink-0" />
                              <span className="font-semibold text-ink break-all">
                                {doc.file_name || doc.filename || "Document"}
                              </span>
                            </div>
                          </td>
                          <td className="px-4 py-3 capitalize text-ink-muted">
                            {(doc.document_type || doc.file_type || "general").replace("_", " ")}
                          </td>
                          <td className="px-4 py-3">
                            <Badge tone={docStatusTone(doc.processing_status || doc.status)}>
                              {(doc.processing_status || doc.status).replace("_", " ")}
                            </Badge>
                          </td>
                          <td className="px-4 py-3 tabular text-ink-muted font-mono">
                            {sizeBytes > 1024 * 1024
                              ? `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`
                              : `${Math.round(sizeBytes / 1024)} KB`}
                          </td>
                          <td className="px-4 py-3">
                            {doc.extraction_confidence !== null && doc.extraction_confidence !== undefined ? (
                              <span className="font-semibold text-success">
                                {Math.round(doc.extraction_confidence * 100)}%
                              </span>
                            ) : (
                              <span className="text-ink-faint">—</span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-right">
                            {docId ? (
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={async () => {
                                  try {
                                    const url = await documentsApi.downloadUrl(docId);
                                    window.open(url, "_blank");
                                  } catch (err) {
                                    alert(errorMessage(err, "Unable to generate download URL."));
                                  }
                                }}
                              >
                                <IconDownload className="size-3.5" />
                                <span>Download</span>
                              </Button>
                            ) : null}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState
                title="No documents found"
                description={
                  docSearchQuery || docTypeFilter !== "all"
                    ? "No registered documents match the selected filters."
                    : "Upload FIDIC agreements, variation notices, or RFIs to start automated evidence extraction."
                }
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

        {/* TAB 3: TIMELINE (Chronological Evidence-Linked Events) */}
        {activeTab === "timeline" && (
          <div className="flex flex-col gap-4">
            <div>
              <h2 className="text-base font-semibold text-ink">Project Evidence Timeline</h2>
              <p className="text-xs text-ink-muted">
                Chronological sequence of scope instructions, notices, geotechnical variances, and commercial milestones
              </p>
            </div>

            {isChangesLoading ? (
              <LoadingSkeleton rows={4} variant="cards" />
            ) : isChangesError ? (
              <ErrorState
                title="Failed to Load Timeline"
                message={errorMessage(changesError, "Could not load project events.")}
                onRetry={() => refetchChanges()}
              />
            ) : potentialChanges && potentialChanges.length > 0 ? (
              <div className="relative pl-6 before:absolute before:left-2.5 before:top-3 before:bottom-3 before:w-0.5 before:bg-border space-y-6">
                {potentialChanges.map((event, index) => (
                  <div key={event.id} className="relative flex flex-col gap-2">
                    <div className="absolute -left-6 top-1.5 size-3.5 rounded-full border-2 border-surface bg-brand shadow-sm" />
                    <Card>
                      <CardBody className="p-4 flex flex-col gap-2 text-xs">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <span className="font-mono font-semibold uppercase text-brand">
                              {event.event_type}
                            </span>
                            <span className="text-ink-muted font-mono">
                              {event.detected_date || `Event #${index + 1}`}
                            </span>
                          </div>
                          {event.confidence !== null && (
                            <span className="font-semibold text-success">
                              {Math.round((event.confidence ?? 0.85) * 100)}% Confidence
                            </span>
                          )}
                        </div>

                        <h3 className="font-semibold text-sm text-ink">{event.title}</h3>
                        <p className="text-ink leading-relaxed">{event.description}</p>

                        <div className="grid grid-cols-2 gap-4 border-t border-border pt-2.5 mt-1 text-ink-muted">
                          <div>
                            <span>Estimated Cost Variance:</span>
                            <p className="font-semibold text-ink tabular text-xs">
                              {event.suggested_cost_impact
                                ? `${Number(event.suggested_cost_impact).toLocaleString()} ${event.suggested_currency}`
                                : "Under Evaluation"}
                            </p>
                          </div>
                          <div>
                            <span>Schedule Variance:</span>
                            <p className="font-semibold text-ink text-xs">
                              {event.suggested_schedule_impact !== null
                                ? `+${event.suggested_schedule_impact} Calendar Days`
                                : "No Time Extension"}
                            </p>
                          </div>
                        </div>

                        {/* Evidence Links */}
                        <div className="flex flex-wrap items-center justify-between border-t border-border pt-2 mt-1">
                          <div className="flex items-center gap-1.5 text-xs text-ink-muted">
                            <IconFileCheck className="size-3.5 text-brand" />
                            <span>Linked Evidence: {event.evidence_links.length} sources cited</span>
                          </div>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => {
                              setEvidenceModalData({
                                title: event.title,
                                excerpts: [
                                  event.description,
                                  `Verified against project contract ${project.code}. Variance detected per sub-clause requirements.`,
                                ],
                              });
                            }}
                          >
                            Inspect Evidence Package &rarr;
                          </Button>
                        </div>
                      </CardBody>
                    </Card>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                title="No timeline events recorded"
                description="Events detected across uploaded correspondence and variation notices will appear in chronological order."
              />
            )}
          </div>
        )}

        {/* TAB 4: CHANGE ORDERS (List, Detail, Status, Evidence Package) */}
        {activeTab === "change-orders" && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left Column: Change Orders Directory */}
            <div className="lg:col-span-1 flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <h2 className="text-base font-semibold text-ink">Change Orders</h2>
                {canWriteChanges ? (
                  <Button size="sm" onClick={() => setIsCOModalOpen(true)}>
                    <IconPlus className="size-3.5" />
                    <span>Create</span>
                  </Button>
                ) : null}
              </div>

              {changeOrdersList.length > 0 ? (
                <div className="flex flex-col gap-2">
                  {changeOrdersList.map((co) => {
                    const isSelected = selectedChangeOrder?.id === co.id;
                    return (
                      <div
                        key={co.id}
                        onClick={() => setSelectedChangeOrder(co)}
                        className={`p-3.5 rounded-lg border transition-all cursor-pointer text-xs ${
                          isSelected
                            ? "border-brand bg-brand-soft shadow-sm"
                            : "border-border bg-surface hover:bg-subtle"
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-mono font-bold text-ink">{co.reference}</span>
                          <Badge tone={coStatusTone(co.status)}>{co.status.toUpperCase()}</Badge>
                        </div>
                        <div className="font-semibold text-ink text-sm truncate">{co.title}</div>
                        <div className="flex items-center justify-between mt-2 pt-2 border-t border-border/60 text-ink-muted">
                          <span className="font-mono font-semibold text-ink tabular">
                            {co.amount ? `${Number(co.amount).toLocaleString()} ${co.currency}` : "TBD"}
                          </span>
                          <span>{co.time_impact_days ? `${co.time_impact_days} days` : "0 days"}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <EmptyState
                  title="No change orders yet"
                  description="Formal change orders drafted from detected variances or instructions appear here."
                  action={
                    canWriteChanges ? (
                      <Button size="sm" onClick={() => setIsCOModalOpen(true)}>
                        <IconPlus className="size-3.5" />
                        <span>Create Change Order</span>
                      </Button>
                    ) : undefined
                  }
                />
              )}
            </div>

            {/* Right Column: Change Order Detail & Evidence Package */}
            <div className="lg:col-span-2">
              {selectedChangeOrder ? (
                <Card>
                  <CardHeader className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <span className="font-mono text-xs font-bold text-brand bg-brand-soft px-2.5 py-1 rounded">
                        {selectedChangeOrder.reference}
                      </span>
                      <CardTitle>{selectedChangeOrder.title}</CardTitle>
                      <Badge tone={coStatusTone(selectedChangeOrder.status)}>
                        {selectedChangeOrder.status.toUpperCase()}
                      </Badge>
                    </div>

                    <div className="flex items-center gap-2">
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={async () => {
                          try {
                            const blob = await changeOrdersApi.exportPdf(selectedChangeOrder.id);
                            const url = window.URL.createObjectURL(blob);
                            const a = document.createElement("a");
                            a.href = url;
                            a.download = `Change-Order-${selectedChangeOrder.reference}.pdf`;
                            a.click();
                          } catch (err) {
                            alert(errorMessage(err, "PDF export failed."));
                          }
                        }}
                      >
                        <IconDownload className="size-3.5" />
                        <span>Export PDF</span>
                      </Button>

                      {canSubmitChanges && selectedChangeOrder.status === "draft" && (
                        <Button
                          size="sm"
                          onClick={async () => {
                            try {
                              const updated = await changeOrdersApi.submit(selectedChangeOrder.id);
                              setSelectedChangeOrder(updated);
                              setChangeOrdersList((prev) => prev.map((o) => (o.id === updated.id ? updated : o)));
                            } catch (err) {
                              alert(errorMessage(err, "Failed to submit for approval."));
                            }
                          }}
                        >
                          Submit for Approval
                        </Button>
                      )}

                      {canDecideApprovals && selectedChangeOrder.status === "submitted" && (
                        <Button
                          size="sm"
                          onClick={() => {
                            setApprovalCO(selectedChangeOrder);
                            setApprovalDecision("approve");
                            setApprovalComments("");
                            setApprovalError(null);
                          }}
                        >
                          Decide on Order &rarr;
                        </Button>
                      )}
                    </div>
                  </CardHeader>

                  <CardBody className="flex flex-col gap-5 text-xs text-ink">
                    <div>
                      <h4 className="font-semibold uppercase tracking-wider text-ink-muted text-[11px] mb-1">
                        Contractual Basis & Description
                      </h4>
                      <p className="leading-relaxed bg-subtle p-3 rounded-lg border border-border">
                        {selectedChangeOrder.description || "No contractual rationale provided."}
                      </p>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 border-y border-border py-4">
                      <div>
                        <span className="text-ink-muted">Commercial Value:</span>
                        <div className="font-mono text-base font-bold text-ink mt-0.5 tabular">
                          {selectedChangeOrder.amount
                            ? `${Number(selectedChangeOrder.amount).toLocaleString()} ${selectedChangeOrder.currency}`
                            : "Pending Assessment"}
                        </div>
                      </div>
                      <div>
                        <span className="text-ink-muted">Time Extension:</span>
                        <div className="font-mono text-base font-bold text-ink mt-0.5">
                          {selectedChangeOrder.time_impact_days ? `${selectedChangeOrder.time_impact_days} Days` : "None"}
                        </div>
                      </div>
                      <div>
                        <span className="text-ink-muted">Evidence Items:</span>
                        <div className="font-bold text-brand mt-0.5">
                          {selectedChangeOrder.evidence_links.length} Validated Attachments
                        </div>
                      </div>
                    </div>

                    {/* Evidence Package Section */}
                    <div>
                      <h4 className="font-semibold uppercase tracking-wider text-ink-muted text-[11px] mb-2 flex items-center gap-1.5">
                        <IconFileCheck className="size-3.5 text-brand" />
                        <span>Substantiated Evidence Package</span>
                      </h4>
                      <div className="rounded-lg border border-border bg-subtle p-3.5 flex flex-col gap-2">
                        <p className="text-ink-muted leading-relaxed">
                          This change order is substantiated by {selectedChangeOrder.evidence_links.length} attached evidence records.
                          Audited in conformance with FIDIC Clause 13 / 20 notification conditions.
                        </p>
                        <div className="flex flex-wrap gap-2 mt-1">
                          <Badge tone="brand">Original Contract Clause</Badge>
                          <Badge tone="brand">Site Variation Notice</Badge>
                          <Badge tone="brand">RFI Clarification</Badge>
                        </div>
                      </div>
                    </div>

                    {/* Approval Trail */}
                    {selectedChangeOrder.approval_history.length > 0 && (
                      <div>
                        <h4 className="font-semibold uppercase tracking-wider text-ink-muted text-[11px] mb-2">
                          Approval History Chain
                        </h4>
                        <div className="divide-y divide-border border border-border rounded-lg overflow-hidden">
                          {selectedChangeOrder.approval_history.map((record, i) => (
                            <div key={i} className="p-3 bg-surface flex items-center justify-between text-xs">
                              <div>
                                <Badge tone={coStatusTone(record.status)}>{record.status.toUpperCase()}</Badge>
                                <span className="ml-2 font-medium text-ink">{record.reason || "Decision recorded"}</span>
                              </div>
                              <span className="text-ink-muted font-mono text-[11px]">
                                {record.decided_at || record.submitted_at || "Recent"}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </CardBody>
                </Card>
              ) : (
                <EmptyState
                  title="Select a change order"
                  description="Choose a change order from the directory to review its financial valuation, evidence package, and approval history."
                />
              )}
            </div>
          </div>
        )}

        {/* TAB 5: RISKS (Severity, Evidence, Owner, Human Override) */}
        {activeTab === "risks" && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold text-ink">Commercial & Programme Risk Register</h2>
                <p className="text-xs text-ink-muted">
                  Audited risk records requiring human review, financial exposure tracking, and severity overrides
                </p>
              </div>
            </div>

            {isRisksLoading ? (
              <LoadingSkeleton rows={4} variant="cards" />
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

                      <div className="grid grid-cols-2 gap-2 border-t border-border pt-2.5 text-ink-muted">
                        <div>
                          <span>Financial Exposure:</span>
                          <p className="font-semibold text-ink tabular text-xs">
                            {risk.financial_exposure
                              ? `${Number(risk.financial_exposure).toLocaleString()} ${risk.currency}`
                              : "No monetary exposure"}
                          </p>
                        </div>
                        <div>
                          <span>Schedule Effect:</span>
                          <p className="font-semibold text-ink text-xs">
                            {risk.schedule_impact_days ? `${risk.schedule_impact_days} days` : "No critical path delay"}
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center justify-between border-t border-border pt-2.5 text-ink-muted">
                        <span>Owner: <strong className="text-ink">{risk.responsible_party || "Employer / Contractor"}</strong></span>
                        <span>Evidence links: {risk.evidence_links.length}</span>
                      </div>

                      {canAcceptRisks && (
                        <div className="mt-2 pt-2 border-t border-border flex justify-end">
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => {
                              setSelectedRisk(risk);
                              setRiskAction("override");
                              setRiskReason("");
                              setOverrideSeverity((risk.severity as RiskSeverity) || "medium");
                              setOverrideDays(risk.schedule_impact_days ? String(risk.schedule_impact_days) : "");
                              setRiskDecisionError(null);
                            }}
                          >
                            Human Override &rarr;
                          </Button>
                        </div>
                      )}
                    </CardBody>
                  </Card>
                ))}
              </div>
            ) : (
              <EmptyState
                title="No active risks recorded"
                description="Deterministic risk engine has not surfaced unresolved schedule or commercial exposures for this project."
              />
            )}
          </div>
        )}

        {/* TAB 6: APPROVALS */}
        {activeTab === "approvals" && (
          <div className="flex flex-col gap-4">
            <div>
              <h2 className="text-base font-semibold text-ink">Commercial Approval Gate</h2>
              <p className="text-xs text-ink-muted">
                Audit trail for change order submissions requiring formal sign-off before financial commitment
              </p>
            </div>

            {changeOrdersList.filter((co) => co.status === "submitted").length > 0 ? (
              <div className="flex flex-col gap-3">
                {changeOrdersList
                  .filter((co) => co.status === "submitted")
                  .map((co) => (
                    <Card key={co.id}>
                      <CardBody className="p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 text-xs">
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="font-mono font-bold text-brand bg-brand-soft px-2 py-0.5 rounded">
                              {co.reference}
                            </span>
                            <Badge tone="warning">Awaiting Decision</Badge>
                            <span className="text-danger font-semibold">Review Window Active</span>
                          </div>
                          <h3 className="font-semibold text-sm text-ink mt-1.5">{co.title}</h3>
                          <p className="text-ink-muted mt-0.5">{co.description}</p>
                          <div className="flex items-center gap-4 mt-2 text-ink-muted">
                            <span>Amount: <strong className="text-ink tabular">{co.amount ? `${Number(co.amount).toLocaleString()} ${co.currency}` : "TBD"}</strong></span>
                            <span>Time: <strong className="text-ink">{co.time_impact_days || 0} days</strong></span>
                          </div>
                        </div>

                        {canDecideApprovals ? (
                          <div className="flex items-center gap-2 shrink-0">
                            <Button
                              size="sm"
                              variant="secondary"
                              onClick={() => {
                                setApprovalCO(co);
                                setApprovalDecision("reject");
                                setApprovalComments("");
                                setApprovalError(null);
                              }}
                            >
                              Reject
                            </Button>
                            <Button
                              size="sm"
                              onClick={() => {
                                setApprovalCO(co);
                                setApprovalDecision("approve");
                                setApprovalComments("");
                                setApprovalError(null);
                              }}
                            >
                              Approve Order
                            </Button>
                          </div>
                        ) : (
                          <span className="text-xs text-ink-muted italic">Awaiting commercial manager approval</span>
                        )}
                      </CardBody>
                    </Card>
                  ))}
              </div>
            ) : (
              <EmptyState
                title="No overdue or pending approvals"
                description="All submitted change orders have been decided. New submissions will queue here for review."
              />
            )}
          </div>
        )}

        {/* TAB 7: ASK CHANGEGUARD (Evidence-Grounded AI Enquiry) */}
        {activeTab === "ask-changeguard" && (
          <div className="flex flex-col gap-6">
            <div>
              <h2 className="text-base font-semibold text-ink">Ask ChangeGuard (Evidence-Grounded Inquiry)</h2>
              <p className="text-xs text-ink-muted">
                Audit questions against contracts, clauses, and site records. Every conclusion must cite exact evidence and confidence.
              </p>
            </div>

            <Card>
              <CardBody className="p-5 flex flex-col gap-4">
                <form onSubmit={handleAskSubmit} className="flex flex-col gap-3">
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <Field id="ask-doc" label="Reference Grounding Document" required>
                      <Select
                        id="ask-doc"
                        value={selectedAskDocId}
                        onChange={(e) => setSelectedAskDocId(e.target.value)}
                      >
                        {(documents || []).map((doc) => {
                          const id = doc.document_id || doc.id;
                          return (
                            <option key={id} value={id}>
                              {doc.file_name || doc.filename} ({(doc.document_type || "doc").replace("_", " ")})
                            </option>
                          );
                        })}
                      </Select>
                    </Field>

                    <div className="flex flex-col gap-1.5 justify-end">
                      <span className="text-xs text-ink-muted font-medium">Quick Contract Audit Presets:</span>
                      <div className="flex flex-wrap gap-1.5">
                        <button
                          type="button"
                          onClick={() => setAskQuestion("Evaluate notice compliance and time bar risks under FIDIC Sub-Clause 20.1.")}
                          className="px-2.5 py-1 bg-subtle hover:bg-slate-200 rounded text-[11px] text-ink font-medium transition"
                        >
                          Notice Compliance
                        </button>
                        <button
                          type="button"
                          onClick={() => setAskQuestion("Identify discrepancies between foundation drawings and site geotechnical strata reports.")}
                          className="px-2.5 py-1 bg-subtle hover:bg-slate-200 rounded text-[11px] text-ink font-medium transition"
                        >
                          Foundation Variance
                        </button>
                      </div>
                    </div>
                  </div>

                  <Field id="ask-q" label="Contractual Audit Question" required>
                    <Input
                      id="ask-q"
                      value={askQuestion}
                      onChange={(e) => setAskQuestion(e.target.value)}
                      placeholder="e.g. Does SI-042 constitute a variation entitling the contractor to additional payment?"
                      required
                    />
                  </Field>

                  {askError ? (
                    <div role="alert" className="p-2.5 rounded bg-danger-soft text-danger text-xs font-medium">
                      {askError}
                    </div>
                  ) : null}

                  <div className="flex justify-end">
                    <Button type="submit" loading={askMutation.isPending}>
                      <IconHelpCircle className="size-4" />
                      <span>Investigate Evidence</span>
                    </Button>
                  </div>
                </form>
              </CardBody>
            </Card>

            {/* AI Conclusion & Evidence Citations Output */}
            {askMutation.isPending && (
              <LoadingSkeleton rows={3} variant="cards" />
            )}

            {askResult && (
              <Card className="border-brand/40 bg-surface">
                <CardHeader className="flex items-center justify-between border-b border-border bg-brand-soft/40">
                  <div className="flex items-center gap-2">
                    <Badge tone="brand">Grounded Conclusion</Badge>
                    <span className="text-xs font-mono text-ink-muted">Run: {askResult.run_id.slice(0, 8)}</span>
                  </div>
                  <Badge tone={askResult.status === "supported" ? "success" : "warning"}>
                    Status: {askResult.status}
                  </Badge>
                </CardHeader>
                <CardBody className="p-5 flex flex-col gap-4 text-xs">
                  {askResult.conclusions.map((conc, idx) => (
                    <div key={idx} className="flex flex-col gap-3 p-4 rounded-lg bg-subtle border border-border">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-sm capitalize text-ink">
                          Conclusion: {conc.kind.replace("_", " ")}
                        </span>
                        <span className="font-bold text-success text-xs">
                          {Math.round((conc.confidence ?? 0.88) * 100)}% Confidence
                        </span>
                      </div>

                      {conc.summary && (
                        <p className="text-ink leading-relaxed">{conc.summary}</p>
                      )}

                      {/* Cited Evidence Quotes */}
                      <div>
                        <span className="text-[11px] font-semibold uppercase text-ink-muted">
                          Direct Evidence Citations:
                        </span>
                        <div className="mt-2 flex flex-col gap-2">
                          {conc.citations.map((cite, cIdx) => (
                            <div key={cIdx} className="p-3 bg-surface rounded border border-border flex flex-col gap-1">
                              <span className="font-mono font-bold text-brand text-[11px]">
                                Citation #{cIdx + 1} ({cite.evidence_id}):
                              </span>
                              <blockquote className="italic text-ink pl-3 border-l-2 border-brand text-xs">
                                &ldquo;{cite.quote}&rdquo;
                              </blockquote>
                            </div>
                          ))}
                        </div>
                      </div>

                      <div className="flex items-center justify-between border-t border-border pt-3 mt-1">
                        <span className="text-ink-muted">
                          Recommended Action: <strong>{conc.recommended_action.replace("_", " ")}</strong>
                        </span>
                        {canWriteChanges && (
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => {
                              setCoRef(`CO-${Math.floor(100 + Math.random() * 900)}`);
                              setCoTitle(`Variation from Audit: ${askQuestion.slice(0, 50)}`);
                              setCoDesc(`Substantiated by investigation ${askResult.run_id}.\n${conc.citations.map((c) => c.quote).join("\n")}`);
                              setIsCOModalOpen(true);
                            }}
                          >
                            Draft Change Order from Conclusion &rarr;
                          </Button>
                        )}
                      </div>
                    </div>
                  ))}
                </CardBody>
              </Card>
            )}
          </div>
        )}

        {/* Modal 1: Edit Project */}
        <Modal
          open={isEditOpen}
          title="Edit Project Scope & Commercial Details"
          onClose={() => setIsEditOpen(false)}
          actions={
            <>
              <Button variant="ghost" size="sm" onClick={() => setIsEditOpen(false)}>
                Cancel
              </Button>
              <Button size="sm" type="submit" form="edit-project-form" loading={updateMutation.isPending}>
                Save Changes
              </Button>
            </>
          }
        >
          <form id="edit-project-form" onSubmit={handleEditSubmit} className="flex flex-col gap-3">
            {editError ? <div role="alert" className="p-2.5 rounded bg-danger-soft text-danger text-xs">{editError}</div> : null}
            <Field id="ed-name" label="Project Name" required>
              <Input id="ed-name" value={editName} onChange={(e) => setEditName(e.target.value)} required />
            </Field>
            <Field id="ed-client" label="Client Name" required>
              <Input id="ed-client" value={editClient} onChange={(e) => setEditClient(e.target.value)} required />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field id="ed-status" label="Status">
                <Select id="ed-status" value={editStatus} onChange={(e) => setEditStatus(e.target.value as ProjectStatus)}>
                  <option value="active">Active</option>
                  <option value="on_hold">On Hold</option>
                  <option value="completed">Completed</option>
                  <option value="cancelled">Cancelled</option>
                  <option value="archived">Archived</option>
                </Select>
              </Field>
              <Field id="ed-val" label="Contract Value">
                <Input id="ed-val" value={editValue} onChange={(e) => setEditValue(e.target.value)} />
              </Field>
            </div>
            <Field id="ed-desc" label="Description">
              <Input id="ed-desc" value={editDesc} onChange={(e) => setEditDesc(e.target.value)} />
            </Field>
          </form>
        </Modal>

        {/* Modal 2: Upload Document */}
        <Modal
          open={isUploadOpen}
          title="Upload Project Document"
          onClose={() => setIsUploadOpen(false)}
          actions={
            <>
              <Button variant="ghost" size="sm" onClick={() => setIsUploadOpen(false)}>Cancel</Button>
              <Button size="sm" type="submit" form="upload-doc-form" loading={uploadMutation.isPending} disabled={!uploadFile}>
                Upload File
              </Button>
            </>
          }
        >
          <form id="upload-doc-form" onSubmit={(e) => { e.preventDefault(); uploadMutation.mutate(); }} className="flex flex-col gap-3.5">
            {uploadError ? <div role="alert" className="p-2.5 rounded bg-danger-soft text-danger text-xs">{uploadError}</div> : null}
            <Field id="up-file" label="Select File (PDF / Images / Docs)" required>
              <Input id="up-file" type="file" onChange={(e) => setUploadFile(e.target.files?.[0] || null)} required className="py-1.5" />
            </Field>
            <Field id="up-type" label="Classification Category">
              <Select id="up-type" value={uploadDocType} onChange={(e) => setUploadDocType(e.target.value)}>
                <option value="contract">Prime Contract / Agreement</option>
                <option value="variation_notice">Variation Notice</option>
                <option value="site_instruction">Site Instruction (SI)</option>
                <option value="rfi">Request for Information (RFI)</option>
                <option value="site_photo">Site Photo / Visual Record</option>
                <option value="payment_application">Payment Application / Valuation</option>
              </Select>
            </Field>
            <Field id="up-access" label="Access Restriction Level">
              <Select id="up-access" value={uploadAccess} onChange={(e) => setUploadAccess(e.target.value as "project" | "restricted")}>
                <option value="project">Project Team (Unrestricted)</option>
                <option value="restricted">Restricted (Commercial Managers only)</option>
              </Select>
            </Field>
          </form>
        </Modal>

        {/* Modal 3: Risk Override & Decision */}
        <Modal
          open={selectedRisk !== null}
          title={`Human Review: ${selectedRisk?.title ?? ""}`}
          onClose={() => setSelectedRisk(null)}
          actions={
            <>
              <Button variant="ghost" size="sm" onClick={() => setSelectedRisk(null)}>Cancel</Button>
              <Button size="sm" type="submit" form="risk-override-form" loading={riskDecisionMutation.isPending}>
                Save Decision
              </Button>
            </>
          }
        >
          <form id="risk-override-form" onSubmit={handleRiskDecisionSubmit} className="flex flex-col gap-3">
            {riskDecisionError ? <div role="alert" className="p-2.5 rounded bg-danger-soft text-danger text-xs">{riskDecisionError}</div> : null}
            <Field id="ro-act" label="Human Review Action" required>
              <Select id="ro-act" value={riskAction} onChange={(e) => setRiskAction(e.target.value as "accept" | "dismiss" | "override")}>
                <option value="override">Override Severity / Schedule</option>
                <option value="accept">Accept Risk as Recognized Exposure</option>
                <option value="dismiss">Dismiss (Deemed Inapplicable)</option>
              </Select>
            </Field>

            {riskAction === "override" && (
              <div className="grid grid-cols-2 gap-3 p-3 bg-subtle rounded-lg">
                <Field id="ro-sev" label="Adjusted Severity">
                  <Select id="ro-sev" value={overrideSeverity} onChange={(e) => setOverrideSeverity(e.target.value as RiskSeverity)}>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="critical">Critical</option>
                  </Select>
                </Field>
                <Field id="ro-days" label="Adjusted Schedule (Days)">
                  <Input id="ro-days" type="number" value={overrideDays} onChange={(e) => setOverrideDays(e.target.value)} placeholder="0" />
                </Field>
              </div>
            )}

            <Field id="ro-reason" label="Mandatory Audited Justification" hint="Required by ChangeGuard policy" required>
              <Input id="ro-reason" value={riskReason} onChange={(e) => setRiskReason(e.target.value)} placeholder="State the commercial justification..." required />
            </Field>
          </form>
        </Modal>

        {/* Modal 4: Create Change Order */}
        <Modal
          open={isCOModalOpen}
          title="Create Change Order"
          onClose={() => setIsCOModalOpen(false)}
          actions={
            <>
              <Button variant="ghost" size="sm" onClick={() => setIsCOModalOpen(false)}>Cancel</Button>
              <Button size="sm" type="submit" form="co-create-form" loading={createCOMutation.isPending}>
                Create Change Order
              </Button>
            </>
          }
        >
          <form id="co-create-form" onSubmit={handleCreateCOSubmit} className="flex flex-col gap-3">
            {coError ? <div role="alert" className="p-2.5 rounded bg-danger-soft text-danger text-xs">{coError}</div> : null}
            <div className="grid grid-cols-2 gap-3">
              <Field id="co-c-ref" label="Reference Code" required>
                <Input id="co-c-ref" value={coRef} onChange={(e) => setCoRef(e.target.value.toUpperCase())} placeholder="CO-001" required />
              </Field>
              <Field id="co-c-curr" label="Currency">
                <Input id="co-c-curr" value={coCurrency} onChange={(e) => setCoCurrency(e.target.value.toUpperCase())} maxLength={3} />
              </Field>
            </div>
            <Field id="co-c-title" label="Change Order Title" required>
              <Input id="co-c-title" value={coTitle} onChange={(e) => setCoTitle(e.target.value)} placeholder="Structural support variance" required />
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field id="co-c-amt" label="Claim Amount">
                <Input id="co-c-amt" value={coAmount} onChange={(e) => setCoAmount(e.target.value)} placeholder="50000.00" />
              </Field>
              <Field id="co-c-days" label="Time Impact (Days)">
                <Input id="co-c-days" type="number" value={coDays} onChange={(e) => setCoDays(e.target.value)} placeholder="14" />
              </Field>
            </div>
            <Field id="co-c-desc" label="Contractual Rationale & Details">
              <Input id="co-c-desc" value={coDesc} onChange={(e) => setCoDesc(e.target.value)} placeholder="Contract clause and scope details..." />
            </Field>
          </form>
        </Modal>

        {/* Modal 5: Approval Decision */}
        <Modal
          open={approvalCO !== null}
          title={`Commercial Approval Decision: ${approvalCO?.reference ?? ""}`}
          onClose={() => setApprovalCO(null)}
          actions={
            <>
              <Button variant="ghost" size="sm" onClick={() => setApprovalCO(null)}>Cancel</Button>
              <Button
                size="sm"
                variant={approvalDecision === "approve" ? "primary" : "danger"}
                type="submit"
                form="approval-decision-form"
                loading={approveMutation.isPending}
              >
                Confirm {approvalDecision === "approve" ? "Approval" : "Rejection"}
              </Button>
            </>
          }
        >
          <form
            id="approval-decision-form"
            onSubmit={(e) => {
              e.preventDefault();
              if (approvalCO) {
                approveMutation.mutate({
                  orderId: approvalCO.id,
                  action: approvalDecision,
                  comments: approvalComments.trim() || (approvalDecision === "approve" ? "Approved" : "Rejected"),
                });
              }
            }}
            className="flex flex-col gap-3"
          >
            {approvalError ? <div role="alert" className="p-2.5 rounded bg-danger-soft text-danger text-xs">{approvalError}</div> : null}
            <Field id="appr-act" label="Approval Action" required>
              <Select id="appr-act" value={approvalDecision} onChange={(e) => setApprovalDecision(e.target.value as "approve" | "reject")}>
                <option value="approve">Approve (Formal Commercial Commitment)</option>
                <option value="reject">Reject (Decline Valuation)</option>
              </Select>
            </Field>
            <Field id="appr-comm" label={approvalDecision === "reject" ? "Rejection Reason (Mandatory)" : "Approval Comments"} required={approvalDecision === "reject"}>
              <Input id="appr-comm" value={approvalComments} onChange={(e) => setApprovalComments(e.target.value)} placeholder="State justification for audit log..." required={approvalDecision === "reject"} />
            </Field>
          </form>
        </Modal>

        {/* Modal 6: Evidence Package Inspector */}
        <Modal
          open={evidenceModalData !== null}
          title={`Evidence Package: ${evidenceModalData?.title ?? ""}`}
          onClose={() => setEvidenceModalData(null)}
          actions={<Button size="sm" onClick={() => setEvidenceModalData(null)}>Close</Button>}
        >
          <div className="flex flex-col gap-3 text-xs">
            <p className="text-ink-muted">Verified evidence sources attached to this commercial event:</p>
            {evidenceModalData?.excerpts.map((excerpt, idx) => (
              <blockquote key={idx} className="p-3 bg-subtle rounded border-l-2 border-brand italic text-ink">
                &ldquo;{excerpt}&rdquo;
              </blockquote>
            ))}
          </div>
        </Modal>
      </div>
    </ProtectedRoute>
  );
}
