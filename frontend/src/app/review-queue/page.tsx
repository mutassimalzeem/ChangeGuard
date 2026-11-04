"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input, Select } from "@/components/ui/form";
import { Modal } from "@/components/ui/modal";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui/states";
import { ProtectedRoute } from "@/components/protected-route";
import {
  IconAlertCircle,
  IconAlertTriangle,
  IconCheck,
  IconCheckCircle,
  IconDocument,
  IconEdit,
  IconExternalLink,
  IconFilter,
  IconHistory,
  IconLock,
  IconReview,
  IconScale,
  IconSearch,
  IconShield,
  IconX,
} from "@/components/icons";
import { projectsApi, reviewsApi } from "@/lib/api/resources";
import { errorMessage } from "@/lib/api/errors";
import { useRole } from "@/lib/auth";
import { hasPermission, ROLES, type Permission, type Role } from "@/lib/rbac";
import {
  REVIEW_CATEGORIES,
  REVIEW_CATEGORY_META,
  reviewDecisionSchema,
  reviewEditSchema,
  type ReviewCategory,
  type ReviewEvidenceLink,
  type ReviewItem,
  type RiskSeverity,
} from "@/lib/contracts";

export default function ReviewQueuePage() {
  const queryClient = useQueryClient();
  const sessionRole = useRole();

  // Selected filters & options
  const [selectedCategory, setSelectedCategory] = useState<ReviewCategory | "all">("all");
  const [selectedProjectId, setSelectedProjectId] = useState<string>("all");
  const [selectedStatus, setSelectedStatus] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");

  // Role simulation toggle for testing authorization enforcement
  const [simulatedRole, setSimulatedRole] = useState<Role | null>(null);
  const currentRole: Role = (simulatedRole || (sessionRole as Role) || "commercial_manager") as Role;

  // Active modal targets
  const [approvingItem, setApprovingItem] = useState<ReviewItem | null>(null);
  const [approvalReason, setApprovalReason] = useState("");
  const [approvalError, setApprovalError] = useState<string | null>(null);

  const [rejectingItem, setRejectingItem] = useState<ReviewItem | null>(null);
  const [rejectionReason, setRejectionReason] = useState("");
  const [rejectionError, setRejectionError] = useState<string | null>(null);

  const [overridingItem, setOverridingItem] = useState<ReviewItem | null>(null);
  const [overrideReason, setOverrideReason] = useState("");
  const [overrideSeverity, setOverrideSeverity] = useState<RiskSeverity>("high");
  const [overrideDays, setOverrideDays] = useState("");
  const [overrideExposure, setOverrideExposure] = useState("");
  const [overrideError, setOverrideError] = useState<string | null>(null);

  const [editingItem, setEditingItem] = useState<ReviewItem | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editCorrection, setEditCorrection] = useState("");
  const [editExposure, setEditExposure] = useState("");
  const [editDays, setEditDays] = useState("");
  const [editReason, setEditReason] = useState("");
  const [editError, setEditError] = useState<string | null>(null);

  const [inspectingEvidence, setInspectingEvidence] = useState<{
    item: ReviewItem;
    link: ReviewEvidenceLink;
  } | null>(null);

  const [historyItem, setHistoryItem] = useState<ReviewItem | null>(null);

  // Load Projects
  const { data: projectsData, isLoading: isProjectsLoading } = useQuery({
    queryKey: ["review-projects"],
    queryFn: () => projectsApi.list({ page: 1, page_size: 50, status: "active" }),
  });
  const projects = projectsData?.items || [];

  // Load Review Queue Items
  const {
    data: allItems = [],
    isLoading: isItemsLoading,
    isError: isItemsError,
    error: itemsError,
    refetch: refetchItems,
  } = useQuery({
    queryKey: ["review-queue-items", selectedProjectId],
    queryFn: () =>
      reviewsApi.list({
        projectId: selectedProjectId === "all" ? undefined : selectedProjectId,
      }),
  });

  // Category counts
  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = { all: allItems.length };
    for (const cat of REVIEW_CATEGORIES) {
      counts[cat] = allItems.filter((i) => i.category === cat).length;
    }
    return counts;
  }, [allItems]);

  // Filtered items list
  const filteredItems = useMemo(() => {
    return allItems.filter((item) => {
      if (selectedCategory !== "all" && item.category !== selectedCategory) return false;
      if (selectedProjectId !== "all" && item.project_id !== selectedProjectId) return false;
      if (selectedStatus !== "all" && item.status !== selectedStatus) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesTitle = item.title.toLowerCase().includes(q);
        const matchesFound = item.system_found.toLowerCase().includes(q);
        const matchesWhy = item.why_review_needed.toLowerCase().includes(q);
        const matchesCode = item.project_code.toLowerCase().includes(q);
        if (!matchesTitle && !matchesFound && !matchesWhy && !matchesCode) return false;
      }
      return true;
    });
  }, [allItems, selectedCategory, selectedProjectId, selectedStatus, searchQuery]);

  // Mutations
  const approveMutation = useMutation({
    mutationFn: async (payload: { item: ReviewItem; reason: string }) => {
      return reviewsApi.approve(payload.item, payload.reason, {
        name: "Active Reviewer",
        role: currentRole,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["review-queue-items"] });
      setApprovingItem(null);
      setApprovalReason("");
      setApprovalError(null);
    },
    onError: (err) => setApprovalError(errorMessage(err, "Failed to approve review item.")),
  });

  const rejectMutation = useMutation({
    mutationFn: async (payload: { item: ReviewItem; reason: string }) => {
      return reviewsApi.reject(payload.item, payload.reason, {
        name: "Active Reviewer",
        role: currentRole,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["review-queue-items"] });
      setRejectingItem(null);
      setRejectionReason("");
      setRejectionError(null);
    },
    onError: (err) => setRejectionError(errorMessage(err, "Failed to reject review item.")),
  });

  const overrideMutation = useMutation({
    mutationFn: async (payload: {
      item: ReviewItem;
      reason: string;
      severity: RiskSeverity;
      schedule_impact_days?: number;
      financial_exposure?: string;
    }) => {
      return reviewsApi.override(
        payload.item,
        {
          reason: payload.reason,
          severity: payload.severity,
          schedule_impact_days: payload.schedule_impact_days,
          financial_exposure: payload.financial_exposure,
        },
        { name: "Active Reviewer", role: currentRole }
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["review-queue-items"] });
      setOverridingItem(null);
      setOverrideReason("");
      setOverrideError(null);
    },
    onError: (err) => setOverrideError(errorMessage(err, "Failed to apply override.")),
  });

  const editMutation = useMutation({
    mutationFn: async (payload: {
      item: ReviewItem;
      title: string;
      recommended_correction: string;
      financial_exposure?: string;
      schedule_impact_days?: number;
      reason: string;
    }) => {
      return reviewsApi.edit(
        payload.item,
        {
          title: payload.title,
          recommended_correction: payload.recommended_correction,
          financial_exposure: payload.financial_exposure || null,
          schedule_impact_days: payload.schedule_impact_days ?? null,
          reason: payload.reason,
        },
        { name: "Active Reviewer", role: currentRole }
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["review-queue-items"] });
      setEditingItem(null);
      setEditReason("");
      setEditError(null);
    },
    onError: (err) => setEditError(errorMessage(err, "Failed to save revisions.")),
  });

  // Submit Handlers
  const handleApproveSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!approvingItem) return;
    setApprovalError(null);

    // Permission check enforcement
    if (!hasPermission(currentRole, approvingItem.required_permission as Permission)) {
      setApprovalError(
        `Authorization denied: Your role (${currentRole}) lacks '${approvingItem.required_permission}' permission.`
      );
      return;
    }

    approveMutation.mutate({
      item: approvingItem,
      reason: approvalReason.trim() || "Approved during audited review",
    });
  };

  const handleRejectSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!rejectingItem) return;
    setRejectionError(null);

    const parsed = reviewDecisionSchema.safeParse({
      action: "reject",
      reason: rejectionReason,
    });
    if (!parsed.success) {
      setRejectionError(parsed.error.issues[0]?.message || "A justification reason is required.");
      return;
    }

    rejectMutation.mutate({
      item: rejectingItem,
      reason: parsed.data.reason,
    });
  };

  const handleOverrideSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!overridingItem) return;
    setOverrideError(null);

    if (!overrideReason.trim()) {
      setOverrideError("A mandatory justification reason is required for overrides.");
      return;
    }

    overrideMutation.mutate({
      item: overridingItem,
      reason: overrideReason.trim(),
      severity: overrideSeverity,
      schedule_impact_days: overrideDays ? parseInt(overrideDays, 10) : undefined,
      financial_exposure: overrideExposure.trim() || undefined,
    });
  };

  const handleEditSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingItem) return;
    setEditError(null);

    const parsed = reviewEditSchema.safeParse({
      title: editTitle,
      recommended_correction: editCorrection,
      financial_exposure: editExposure || null,
      schedule_impact_days: editDays ? parseInt(editDays, 10) : null,
      reason: editReason,
    });

    if (!parsed.success) {
      setEditError(parsed.error.issues[0]?.message || "Invalid edit inputs.");
      return;
    }

    editMutation.mutate({
      item: editingItem,
      title: parsed.data.title || editingItem.title,
      recommended_correction: parsed.data.recommended_correction || editingItem.recommended_correction,
      financial_exposure: parsed.data.financial_exposure || undefined,
      schedule_impact_days: parsed.data.schedule_impact_days ?? undefined,
      reason: parsed.data.reason,
    });
  };

  // Helper to open modals with prepopulated values
  const openEditModal = (item: ReviewItem) => {
    setEditingItem(item);
    setEditTitle(item.title);
    setEditCorrection(item.recommended_correction);
    setEditExposure(item.financial_exposure || "");
    setEditDays(item.schedule_impact_days !== null ? String(item.schedule_impact_days) : "");
    setEditReason("");
    setEditError(null);
  };

  const openOverrideModal = (item: ReviewItem) => {
    setOverridingItem(item);
    setOverrideSeverity(item.severity);
    setOverrideDays(item.schedule_impact_days !== null ? String(item.schedule_impact_days) : "");
    setOverrideExposure(item.financial_exposure || "");
    setOverrideReason("");
    setOverrideError(null);
  };

  const openRejectModal = (item: ReviewItem) => {
    setRejectingItem(item);
    setRejectionReason("");
    setRejectionError(null);
  };

  const openApproveModal = (item: ReviewItem) => {
    setApprovingItem(item);
    setApprovalReason("");
    setApprovalError(null);
  };

  return (
    <ProtectedRoute>
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 flex flex-col gap-6">
        {/* Top Header */}
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between border-b border-border pb-6">
          <div>
            <div className="flex items-center gap-3">
              <div className="flex size-10 items-center justify-center rounded-lg bg-brand-soft text-brand">
                <IconReview className="size-6" />
              </div>
              <div>
                <h1 className="text-2xl font-bold tracking-tight text-ink">Review Queue & Approvals</h1>
                <p className="text-xs text-ink-muted">
                  Audited commercial, contractual, and technical verification of pipeline findings
                </p>
              </div>
            </div>
          </div>

          {/* Controls: Project selector & Simulated Role switcher */}
          <div className="flex flex-wrap items-center gap-3">
            {/* Project Selector */}
            <div className="flex items-center gap-2">
              <label htmlFor="project-filter" className="text-xs font-medium text-ink-muted">
                Project:
              </label>
              {isProjectsLoading ? (
                <div className="h-9 w-40 rounded bg-subtle animate-pulse" />
              ) : (
                <Select
                  id="project-filter"
                  value={selectedProjectId}
                  onChange={(e) => setSelectedProjectId(e.target.value)}
                  className="h-9 text-xs w-48 font-medium"
                >
                  <option value="all">All Projects</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.code} - {p.name}
                    </option>
                  ))}
                </Select>
              )}
            </div>

            {/* Role Switcher */}
            <div className="flex items-center gap-2 rounded-lg border border-border bg-subtle/50 px-2.5 py-1.5">
              <span className="text-[11px] font-medium text-ink-muted flex items-center gap-1">
                <IconShield className="size-3.5 text-brand" />
                Active Role:
              </span>
              <select
                aria-label="Active role selector"
                value={currentRole}
                onChange={(e) => setSimulatedRole(e.target.value as Role)}
                className="h-7 rounded border border-border bg-surface px-2 text-xs font-semibold text-ink focus:outline-none focus:ring-1 focus:ring-brand"
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r.replace("_", " ")}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Category Pills Navigation (all 7 review categories) */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-ink-muted flex items-center gap-1.5">
              <IconFilter className="size-3.5" />
              Review Categories
            </span>
            <span className="text-xs text-ink-muted">
              Showing {filteredItems.length} of {allItems.length} review items
            </span>
          </div>

          <div className="flex flex-wrap gap-2 pt-1" role="tablist" aria-label="Review queue categories">
            <button
              type="button"
              role="tab"
              aria-selected={selectedCategory === "all"}
              onClick={() => setSelectedCategory("all")}
              className={`inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                selectedCategory === "all"
                  ? "border-brand bg-brand text-white shadow-xs"
                  : "border-border bg-surface text-ink hover:bg-subtle"
              }`}
            >
              <span>All Categories</span>
              <span
                className={`rounded-full px-1.5 py-0.2 text-[10px] font-bold ${
                  selectedCategory === "all" ? "bg-white/20 text-white" : "bg-subtle text-ink-muted"
                }`}
              >
                {categoryCounts.all ?? 0}
              </span>
            </button>

            {REVIEW_CATEGORIES.map((cat) => {
              const meta = REVIEW_CATEGORY_META[cat];
              const count = categoryCounts[cat] ?? 0;
              const isSelected = selectedCategory === cat;

              return (
                <button
                  key={cat}
                  type="button"
                  role="tab"
                  aria-selected={isSelected}
                  onClick={() => setSelectedCategory(cat)}
                  className={`inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors ${
                    isSelected
                      ? "border-brand bg-brand text-white shadow-xs"
                      : "border-border bg-surface text-ink hover:bg-subtle"
                  }`}
                >
                  <span>{meta.label}</span>
                  <span
                    className={`rounded-full px-1.5 py-0.2 text-[10px] font-bold ${
                      isSelected ? "bg-white/20 text-white" : "bg-subtle text-ink-muted"
                    }`}
                  >
                    {count}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Search and Secondary Filter Bar */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between rounded-lg border border-border bg-surface p-3">
          <div className="relative flex-1">
            <IconSearch className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-ink-muted" />
            <input
              type="search"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by title, findings, risk reason, or code..."
              className="h-9 w-full rounded-md border border-border bg-surface pl-9 pr-3 text-xs text-ink placeholder:text-ink-muted focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
            />
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <span className="text-xs font-medium text-ink-muted">Status:</span>
            <select
              aria-label="Filter items by status"
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className="h-9 rounded-md border border-border bg-surface px-2.5 text-xs font-medium text-ink focus:outline-none focus:ring-1 focus:ring-brand"
            >
              <option value="all">All Statuses</option>
              <option value="pending">Pending Review</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
              <option value="overridden">Overridden</option>
            </select>
          </div>
        </div>

        {/* Items List Content */}
        {isItemsLoading ? (
          <LoadingSkeleton rows={4} variant="cards" />
        ) : isItemsError ? (
          <ErrorState
            title="Failed to Load Review Queue"
            message={errorMessage(itemsError, "Could not fetch review items.")}
            onRetry={() => refetchItems()}
          />
        ) : filteredItems.length > 0 ? (
          <div className="flex flex-col gap-5">
            {filteredItems.map((item) => {
              const meta = REVIEW_CATEGORY_META[item.category];
              const isAuthorizedToApprove = hasPermission(currentRole, item.required_permission as Permission);

              return (
                <Card
                  key={item.id}
                  className={`border-l-4 transition-all ${
                    item.severity === "critical"
                      ? "border-l-danger"
                      : item.severity === "high"
                      ? "border-l-warning"
                      : "border-l-brand"
                  }`}
                >
                  <CardHeader className="border-b border-border/60 pb-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone={meta.tone}>{meta.label}</Badge>
                        <span className="rounded bg-subtle px-2 py-0.5 font-mono text-[11px] font-medium text-ink-muted">
                          {item.project_code}
                        </span>
                        <Badge
                          tone={
                            item.severity === "critical"
                              ? "danger"
                              : item.severity === "high"
                              ? "warning"
                              : "neutral"
                          }
                        >
                          {item.severity.toUpperCase()} SEVERITY
                        </Badge>
                      </div>

                      <div className="flex items-center gap-3">
                        {item.financial_exposure ? (
                          <div className="text-right">
                            <span className="text-[10px] uppercase font-semibold text-ink-muted block leading-none">
                              Financial Exposure
                            </span>
                            <span className="font-mono text-xs font-bold text-ink tabular">
                              {Number(item.financial_exposure).toLocaleString()} {item.currency}
                            </span>
                          </div>
                        ) : null}

                        {item.schedule_impact_days !== null && item.schedule_impact_days > 0 ? (
                          <div className="text-right border-l border-border pl-3">
                            <span className="text-[10px] uppercase font-semibold text-ink-muted block leading-none">
                              Schedule
                            </span>
                            <span className="font-mono text-xs font-bold text-danger tabular">
                              +{item.schedule_impact_days} days
                            </span>
                          </div>
                        ) : null}

                        <Badge
                          tone={
                            item.status === "approved"
                              ? "success"
                              : item.status === "rejected"
                              ? "danger"
                              : item.status === "overridden"
                              ? "brand"
                              : "warning"
                          }
                        >
                          {item.status.toUpperCase()}
                        </Badge>
                      </div>
                    </div>

                    <CardTitle className="mt-2 text-base font-bold text-ink">
                      {item.title}
                    </CardTitle>
                  </CardHeader>

                  <CardBody className="flex flex-col gap-4 text-xs pt-4">
                    {/* Findings & Why Review Is Needed Panels */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {/* What system found */}
                      <div className="rounded-lg border border-border bg-subtle/30 p-3.5 flex flex-col gap-1.5">
                        <div className="flex items-center gap-1.5 font-semibold text-ink">
                          <IconSearch className="size-4 text-brand shrink-0" />
                          <span>What the system found</span>
                        </div>
                        <p className="text-ink leading-relaxed">{item.system_found}</p>
                      </div>

                      {/* Why review is needed */}
                      <div className="rounded-lg border border-warning/30 bg-warning-soft/20 p-3.5 flex flex-col gap-1.5">
                        <div className="flex items-center gap-1.5 font-semibold text-warning-strong">
                          <IconAlertTriangle className="size-4 text-warning shrink-0" />
                          <span>Why review is needed</span>
                        </div>
                        <p className="text-ink leading-relaxed">{item.why_review_needed}</p>
                      </div>
                    </div>

                    {/* Evidence Links */}
                    {item.evidence_links.length > 0 && (
                      <div className="rounded-lg border border-border bg-surface p-3">
                        <div className="flex items-center justify-between pb-2 border-b border-border/50">
                          <span className="font-semibold text-ink flex items-center gap-1.5">
                            <IconDocument className="size-4 text-ink-muted" />
                            Evidence Links ({item.evidence_links.length})
                          </span>
                          <span className="text-[11px] text-ink-muted">
                            Click any citation to inspect source excerpt & verification metadata
                          </span>
                        </div>

                        <div className="divide-y divide-border/40 pt-1">
                          {item.evidence_links.map((link) => (
                            <div
                              key={link.id}
                              className="py-2.5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2"
                            >
                              <div className="flex flex-col gap-0.5 max-w-2xl">
                                <div className="flex items-center gap-2">
                                  <span className="font-medium text-ink">{link.document_name}</span>
                                  {link.page_number && (
                                    <span className="text-[11px] font-mono text-ink-muted">
                                      Page {link.page_number}
                                    </span>
                                  )}
                                  {link.confidence !== undefined && (
                                    <Badge
                                      tone={
                                        link.confidence >= 0.85
                                          ? "success"
                                          : link.confidence >= 0.7
                                          ? "warning"
                                          : "danger"
                                      }
                                    >
                                      {Math.round(link.confidence * 100)}% Confidence
                                    </Badge>
                                  )}
                                </div>
                                <p className="text-[11px] text-ink-muted italic line-clamp-2">
                                  &ldquo;{link.excerpt}&rdquo;
                                </p>
                              </div>

                              <Button
                                size="sm"
                                variant="ghost"
                                className="shrink-0 text-brand"
                                onClick={() => setInspectingEvidence({ item, link })}
                              >
                                <IconExternalLink className="size-3.5" />
                                <span>Inspect excerpt</span>
                              </Button>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Recommended Correction */}
                    <div className="rounded-lg border border-brand/20 bg-brand-soft/30 p-3.5 flex flex-col gap-1.5">
                      <div className="flex items-center gap-1.5 font-semibold text-brand">
                        <IconCheckCircle className="size-4 text-brand shrink-0" />
                        <span>Recommended correction</span>
                      </div>
                      <p className="text-ink leading-relaxed font-medium">{item.recommended_correction}</p>
                    </div>

                    {/* Action Controls & Audit History */}
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-t border-border pt-3 mt-1">
                      {/* Left: Audit History trigger */}
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setHistoryItem(item)}
                        className="text-ink-muted hover:text-ink"
                      >
                        <IconHistory className="size-4" />
                        <span>Audit history ({item.audit_history.length})</span>
                      </Button>

                      {/* Right: Approve / Edit / Reject / Override Controls */}
                      <div className="flex flex-wrap items-center gap-2">
                        {/* Edit Control */}
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => openEditModal(item)}
                          disabled={item.status === "approved"}
                        >
                          <IconEdit className="size-3.5" />
                          <span>Edit</span>
                        </Button>

                        {/* Reject Control */}
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => openRejectModal(item)}
                          disabled={item.status === "rejected"}
                          className="hover:border-danger hover:text-danger"
                        >
                          <IconX className="size-3.5" />
                          <span>Reject</span>
                        </Button>

                        {/* Override Control (for risks and high severity items) */}
                        {(item.entity_type === "risk" || item.severity === "critical" || item.severity === "high") && (
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => openOverrideModal(item)}
                          >
                            <IconScale className="size-3.5" />
                            <span>Override</span>
                          </Button>
                        )}

                        {/* Approve Control (Strict Authorization Protection) */}
                        {isAuthorizedToApprove ? (
                          <Button
                            size="sm"
                            variant="primary"
                            onClick={() => openApproveModal(item)}
                            disabled={item.status === "approved"}
                          >
                            <IconCheck className="size-3.5" />
                            <span>{item.status === "approved" ? "Approved" : "Approve"}</span>
                          </Button>
                        ) : (
                          <div className="relative group inline-block">
                            <Button
                              size="sm"
                              variant="secondary"
                              disabled
                              className="opacity-60 cursor-not-allowed bg-subtle text-ink-muted"
                            >
                              <IconLock className="size-3.5 text-danger shrink-0" />
                              <span>Approve</span>
                            </Button>
                            <div className="absolute right-0 bottom-full mb-1 hidden w-64 rounded-md bg-ink p-2 text-[11px] text-white shadow-lg group-hover:block z-30">
                              <p className="font-semibold text-danger-soft">Unauthorized Action</p>
                              <p className="mt-0.5">
                                Requires &lsquo;{item.required_permission}&rsquo; permission. Your active role (&lsquo;{currentRole}&rsquo;) is not authorized to sign off.
                              </p>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </CardBody>
                </Card>
              );
            })}
          </div>
        ) : (
          <EmptyState
            title="No review items match your criteria"
            description="All automated extractions, variations, and high-severity risks have been verified and audited."
            action={
              selectedCategory !== "all" || selectedProjectId !== "all" || selectedStatus !== "all" ? (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => {
                    setSelectedCategory("all");
                    setSelectedProjectId("all");
                    setSelectedStatus("all");
                    setSearchQuery("");
                  }}
                >
                  Reset filters
                </Button>
              ) : undefined
            }
          />
        )}

        {/* Modal 1: Approve Confirmation Modal */}
        <Modal
          open={approvingItem !== null}
          title={`Approve: ${approvingItem?.title ?? ""}`}
          onClose={() => setApprovingItem(null)}
          actions={
            <>
              <Button variant="ghost" size="sm" onClick={() => setApprovingItem(null)}>
                Cancel
              </Button>
              <Button
                size="sm"
                type="submit"
                form="approve-decision-form"
                loading={approveMutation.isPending}
              >
                Confirm & Sign Off
              </Button>
            </>
          }
        >
          <form id="approve-decision-form" onSubmit={handleApproveSubmit} className="flex flex-col gap-3">
            {approvalError ? (
              <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft p-2.5 text-xs text-danger">
                {approvalError}
              </div>
            ) : null}

            <div className="rounded-lg border border-border bg-subtle/50 p-3 text-xs flex flex-col gap-1.5">
              <span className="font-medium text-ink">Commercial sign-off confirmation</span>
              <p className="text-ink-muted">
                Approving this item executes the commercial workflow API on the backend and appends an immutable entry
                to the audit log under actor &lsquo;{currentRole}&rsquo;.
              </p>
              {approvingItem?.financial_exposure && (
                <p className="font-semibold text-ink">
                  Total recognized commitment: {Number(approvingItem.financial_exposure).toLocaleString()}{" "}
                  {approvingItem.currency}
                </p>
              )}
            </div>

            <Field
              id="appr-reason"
              label="Sign-Off Note"
              hint="Recorded in the permanent audit trail"
            >
              <Input
                id="appr-reason"
                value={approvalReason}
                onChange={(e) => setApprovalReason(e.target.value)}
                placeholder="Reason or rationale for commercial sign-off (e.g. rate audited against bill of quantities)..."
              />
            </Field>
          </form>
        </Modal>

        {/* Modal 2: Reject Modal (Mandatory Reason Required) */}
        <Modal
          open={rejectingItem !== null}
          title={`Reject: ${rejectingItem?.title ?? ""}`}
          onClose={() => setRejectingItem(null)}
          actions={
            <>
              <Button variant="ghost" size="sm" onClick={() => setRejectingItem(null)}>
                Cancel
              </Button>
              <Button
                size="sm"
                variant="primary"
                type="submit"
                form="reject-decision-form"
                loading={rejectMutation.isPending}
                className="bg-danger hover:bg-danger/90 text-white"
              >
                Confirm Rejection
              </Button>
            </>
          }
        >
          <form id="reject-decision-form" onSubmit={handleRejectSubmit} className="flex flex-col gap-3">
            {rejectionError ? (
              <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft p-2.5 text-xs text-danger">
                {rejectionError}
              </div>
            ) : null}

            <div className="rounded-lg border border-danger/20 bg-danger-soft/20 p-3 text-xs text-ink flex items-start gap-2">
              <IconAlertCircle className="size-4 text-danger shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold text-danger">Mandatory Audit Justification</span>
                <p className="text-ink-muted mt-0.5">
                  Rejection requires an explicit justification reason. This rationale will be permanently recorded in
                  the project audit trail.
                </p>
              </div>
            </div>

            <Field
              id="rej-reason"
              label="Rejection Justification"
              hint="State the contractual or factual grounds for rejection"
              required
            >
              <textarea
                id="rej-reason"
                rows={3}
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                placeholder="e.g. Claim disproven by calibrated site telemetry MET-JUN-2026 showing under 4.2mm precipitation..."
                required
                className="w-full rounded-md border border-border bg-surface p-2.5 text-xs text-ink placeholder:text-ink-muted focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
              />
            </Field>
          </form>
        </Modal>

        {/* Modal 3: Override Modal (Mandatory Reason Required) */}
        <Modal
          open={overridingItem !== null}
          title={`Override Parameters: ${overridingItem?.title ?? ""}`}
          onClose={() => setOverridingItem(null)}
          actions={
            <>
              <Button variant="ghost" size="sm" onClick={() => setOverridingItem(null)}>
                Cancel
              </Button>
              <Button
                size="sm"
                type="submit"
                form="override-form"
                loading={overrideMutation.isPending}
              >
                Apply Override
              </Button>
            </>
          }
        >
          <form id="override-form" onSubmit={handleOverrideSubmit} className="flex flex-col gap-3">
            {overrideError ? (
              <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft p-2.5 text-xs text-danger">
                {overrideError}
              </div>
            ) : null}

            <div className="rounded-lg border border-warning/20 bg-warning-soft/20 p-3 text-xs text-ink flex items-start gap-2">
              <IconAlertTriangle className="size-4 text-warning shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold text-warning-strong">Audited Human Override</span>
                <p className="text-ink-muted mt-0.5">
                  Overriding automated pipeline values requires an audited justification explaining why the system
                  assessment is adjusted.
                </p>
              </div>
            </div>

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

              <div className="col-span-2">
                <Field id="ov-exposure" label="Revised Financial Exposure">
                  <Input
                    id="ov-exposure"
                    type="text"
                    value={overrideExposure}
                    onChange={(e) => setOverrideExposure(e.target.value)}
                    placeholder="0.00"
                  />
                </Field>
              </div>
            </div>

            <Field
              id="ov-reason"
              label="Override Justification"
              hint="Mandatory commercial grounds for overriding system values"
              required
            >
              <textarea
                id="ov-reason"
                rows={3}
                value={overrideReason}
                onChange={(e) => setOverrideReason(e.target.value)}
                placeholder="Explain why the severity, schedule, or financial calculation is modified..."
                required
                className="w-full rounded-md border border-border bg-surface p-2.5 text-xs text-ink placeholder:text-ink-muted focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
              />
            </Field>
          </form>
        </Modal>

        {/* Modal 4: Edit Correction Modal */}
        <Modal
          open={editingItem !== null}
          title="Edit Review Item & Correction"
          onClose={() => setEditingItem(null)}
          actions={
            <>
              <Button variant="ghost" size="sm" onClick={() => setEditingItem(null)}>
                Cancel
              </Button>
              <Button
                size="sm"
                type="submit"
                form="edit-form"
                loading={editMutation.isPending}
              >
                Save Revisions
              </Button>
            </>
          }
        >
          <form id="edit-form" onSubmit={handleEditSubmit} className="flex flex-col gap-3">
            {editError ? (
              <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft p-2.5 text-xs text-danger">
                {editError}
              </div>
            ) : null}

            <Field id="ed-title" label="Title" required>
              <Input
                id="ed-title"
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                required
              />
            </Field>

            <Field id="ed-corr" label="Recommended Correction" required>
              <textarea
                id="ed-corr"
                rows={3}
                value={editCorrection}
                onChange={(e) => setEditCorrection(e.target.value)}
                required
                className="w-full rounded-md border border-border bg-surface p-2.5 text-xs text-ink placeholder:text-ink-muted focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
              />
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field id="ed-exposure" label="Financial Exposure">
                <Input
                  id="ed-exposure"
                  value={editExposure}
                  onChange={(e) => setEditExposure(e.target.value)}
                  placeholder="0.00"
                />
              </Field>

              <Field id="ed-days" label="Schedule Impact (Days)">
                <Input
                  id="ed-days"
                  type="number"
                  value={editDays}
                  onChange={(e) => setEditDays(e.target.value)}
                  placeholder="0"
                />
              </Field>
            </div>

            <Field
              id="ed-reason"
              label="Audited Edit Note"
              hint="Mandatory explanation for amending recommendation or values"
              required
            >
              <Input
                id="ed-reason"
                value={editReason}
                onChange={(e) => setEditReason(e.target.value)}
                placeholder="Reason for editing recommendation..."
                required
              />
            </Field>
          </form>
        </Modal>

        {/* Modal 5: Evidence Inspection Modal */}
        <Modal
          open={inspectingEvidence !== null}
          title={`Evidence Citation: ${inspectingEvidence?.link.document_name ?? ""}`}
          onClose={() => setInspectingEvidence(null)}
          actions={
            <Button size="sm" onClick={() => setInspectingEvidence(null)}>
              Close
            </Button>
          }
        >
          {inspectingEvidence && (
            <div className="flex flex-col gap-4 text-xs">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border pb-3">
                <div>
                  <span className="text-[11px] font-medium text-ink-muted uppercase">Document Source</span>
                  <p className="font-semibold text-ink">{inspectingEvidence.link.document_name}</p>
                </div>
                <div className="flex items-center gap-2">
                  {inspectingEvidence.link.page_number && (
                    <Badge tone="neutral">Page {inspectingEvidence.link.page_number}</Badge>
                  )}
                  {inspectingEvidence.link.confidence !== undefined && (
                    <Badge tone={inspectingEvidence.link.confidence >= 0.85 ? "success" : "warning"}>
                      {Math.round(inspectingEvidence.link.confidence * 100)}% Extraction Confidence
                    </Badge>
                  )}
                </div>
              </div>

              <div>
                <span className="text-[11px] font-semibold text-ink-muted uppercase block mb-1.5">
                  Verbatim Document Excerpt
                </span>
                <div className="rounded-lg border border-border bg-subtle p-3.5 font-mono text-xs leading-relaxed text-ink">
                  &ldquo;{inspectingEvidence.link.excerpt}&rdquo;
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 text-ink-muted border-t border-border pt-3">
                <div>
                  <span>Source Type:</span>
                  <p className="font-medium text-ink capitalize">{inspectingEvidence.link.source_type}</p>
                </div>
                <div>
                  <span>Source Reference ID:</span>
                  <p className="font-mono text-ink">{inspectingEvidence.link.source_id}</p>
                </div>
              </div>
            </div>
          )}
        </Modal>

        {/* Modal 6: Audit History Modal */}
        <Modal
          open={historyItem !== null}
          title={`Audit History: ${historyItem?.title ?? ""}`}
          onClose={() => setHistoryItem(null)}
          actions={
            <Button size="sm" onClick={() => setHistoryItem(null)}>
              Close
            </Button>
          }
        >
          {historyItem && (
            <div className="flex flex-col gap-3 text-xs">
              <p className="text-ink-muted">
                Immutable chronological log of all automated detections, human reviews, overrides, and approvals:
              </p>

              <div className="relative pl-6 space-y-4 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-border">
                {historyItem.audit_history.map((record) => (
                  <div key={record.id} className="relative">
                    <div className="absolute -left-6 top-1 size-2.5 rounded-full bg-brand ring-4 ring-surface" />
                    <div className="rounded-lg border border-border bg-surface p-3 flex flex-col gap-1">
                      <div className="flex items-center justify-between">
                        <span className="font-semibold text-ink">{record.action}</span>
                        <span className="text-[10px] text-ink-muted font-mono">
                          {new Date(record.timestamp).toLocaleString()}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5 text-ink-muted">
                        <span>Actor:</span>
                        <span className="font-medium text-ink">{record.actor_name}</span>
                        <span className="text-[11px] font-mono">({record.actor_role})</span>
                      </div>
                      {record.reason && (
                        <div className="mt-1 rounded bg-subtle p-2 text-ink">
                          <span className="font-semibold text-ink-muted text-[10px] block uppercase">
                            Audited Reason:
                          </span>
                          <span>{record.reason}</span>
                        </div>
                      )}
                      {record.details && Object.keys(record.details).length > 0 && (
                        <div className="mt-1 font-mono text-[10px] text-ink-muted">
                          {JSON.stringify(record.details)}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Modal>
      </div>
    </ProtectedRoute>
  );
}
