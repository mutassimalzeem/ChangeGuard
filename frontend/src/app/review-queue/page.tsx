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
  reviewEditSchema,
  riskDismissDecisionSchema,
  riskRequestEvidenceSchema,
  riskConvertChangeOrderSchema,
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

  // Authorization flags
  const canAcceptRisks = hasPermission(currentRole, "risks.accept" as Permission);
  const canWriteChanges = hasPermission(currentRole, "change_orders.write" as Permission);
  const canDecideApprovals = hasPermission(currentRole, "approvals.decide" as Permission);
  const isAuthorized = canAcceptRisks || canDecideApprovals;

  // Active modal targets
  // 1. Accept Risk Modal
  const [acceptingItem, setAcceptingItem] = useState<ReviewItem | null>(null);
  const [acceptReason, setAcceptReason] = useState("");
  const [acceptError, setAcceptError] = useState<string | null>(null);

  // 2. Dismiss Risk Modal
  const [dismissingItem, setDismissingItem] = useState<ReviewItem | null>(null);
  const [dismissReason, setDismissReason] = useState("");
  const [dismissError, setDismissError] = useState<string | null>(null);

  // 3. Request Evidence Modal
  const [requestingItem, setRequestingItem] = useState<ReviewItem | null>(null);
  const [requestReason, setRequestReason] = useState("");
  const [requestDetails, setRequestDetails] = useState("");
  const [requestError, setRequestError] = useState<string | null>(null);

  // 4. Convert to Change Order Modal
  const [convertingItem, setConvertingItem] = useState<ReviewItem | null>(null);
  const [convertRef, setConvertRef] = useState("");
  const [convertTitle, setConvertTitle] = useState("");
  const [convertReason, setConvertReason] = useState("");
  const [convertAmount, setConvertAmount] = useState("");
  const [convertDays, setConvertDays] = useState("");
  const [convertError, setConvertError] = useState<string | null>(null);

  // 5. Override Modal
  const [overridingItem, setOverridingItem] = useState<ReviewItem | null>(null);
  const [overrideReason, setOverrideReason] = useState("");
  const [overrideSeverity, setOverrideSeverity] = useState<RiskSeverity>("high");
  const [overrideDays, setOverrideDays] = useState("");
  const [overrideExposure, setOverrideExposure] = useState("");
  const [overrideError, setOverrideError] = useState<string | null>(null);

  // 6. Edit Modal
  const [editingItem, setEditingItem] = useState<ReviewItem | null>(null);
  const [editTitle, setEditTitle] = useState("");
  const [editCorrection, setEditCorrection] = useState("");
  const [editExposure, setEditExposure] = useState("");
  const [editDays, setEditDays] = useState("");
  const [editReason, setEditReason] = useState("");
  const [editError, setEditError] = useState<string | null>(null);

  // 7. Evidence Inspector & Audit History
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
        const matchesType = (item.risk_type || "").toLowerCase().includes(q);
        if (!matchesTitle && !matchesFound && !matchesWhy && !matchesCode && !matchesType) return false;
      }
      return true;
    });
  }, [allItems, selectedCategory, selectedProjectId, selectedStatus, searchQuery]);

  // Mutations
  const acceptRiskMutation = useMutation({
    mutationFn: async (payload: { item: ReviewItem; reason: string }) => {
      return reviewsApi.acceptRisk(payload.item, payload.reason, {
        name: "Active Reviewer",
        role: currentRole,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["review-queue-items"] });
      setAcceptingItem(null);
      setAcceptReason("");
      setAcceptError(null);
    },
    onError: (err) => setAcceptError(errorMessage(err, "Failed to accept risk.")),
  });

  const dismissRiskMutation = useMutation({
    mutationFn: async (payload: { item: ReviewItem; reason: string }) => {
      return reviewsApi.dismissRisk(payload.item, payload.reason, {
        name: "Active Reviewer",
        role: currentRole,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["review-queue-items"] });
      setDismissingItem(null);
      setDismissReason("");
      setDismissError(null);
    },
    onError: (err) => setDismissError(errorMessage(err, "Failed to dismiss risk.")),
  });

  const requestEvidenceMutation = useMutation({
    mutationFn: async (payload: { item: ReviewItem; reason: string; requestedDetails?: string }) => {
      return reviewsApi.requestEvidence(
        payload.item,
        { reason: payload.reason, requested_details: payload.requestedDetails },
        { name: "Active Reviewer", role: currentRole }
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["review-queue-items"] });
      setRequestingItem(null);
      setRequestReason("");
      setRequestDetails("");
      setRequestError(null);
    },
    onError: (err) => setRequestError(errorMessage(err, "Failed to request more evidence.")),
  });

  const convertChangeOrderMutation = useMutation({
    mutationFn: async (payload: {
      item: ReviewItem;
      reference: string;
      title: string;
      reason: string;
      amount?: string;
      timeImpactDays?: number;
    }) => {
      return reviewsApi.convertToChangeOrder(
        payload.item,
        {
          change_order_reference: payload.reference,
          change_order_title: payload.title,
          reason: payload.reason,
          amount: payload.amount,
          time_impact_days: payload.timeImpactDays,
        },
        { name: "Active Reviewer", role: currentRole }
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["review-queue-items"] });
      setConvertingItem(null);
      setConvertRef("");
      setConvertTitle("");
      setConvertReason("");
      setConvertAmount("");
      setConvertDays("");
      setConvertError(null);
    },
    onError: (err) => setConvertError(errorMessage(err, "Failed to convert risk to change order.")),
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
  const handleAcceptSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!acceptingItem) return;
    setAcceptError(null);

    // Constraint: Insufficient-evidence risks cannot be accepted as supported evidence
    if (
      acceptingItem.category === "insufficient_evidence_risk" ||
      acceptingItem.status === "insufficient_evidence" ||
      acceptingItem.evidence_links.length === 0
    ) {
      setAcceptError("Insufficient-evidence risks cannot be accepted as supported evidence.");
      return;
    }

    if (!canAcceptRisks && !hasPermission(currentRole, acceptingItem.required_permission as Permission)) {
      setAcceptError(`Permission Denied: Your role (${currentRole}) lacks 'risks.accept' permission.`);
      return;
    }

    acceptRiskMutation.mutate({
      item: acceptingItem,
      reason: acceptReason.trim() || "Accepted risk in review queue",
    });
  };

  const handleDismissSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!dismissingItem) return;
    setDismissError(null);

    const parsed = riskDismissDecisionSchema.safeParse({ reason: dismissReason });
    if (!parsed.success) {
      setDismissError(parsed.error.issues[0]?.message || "A justification reason is required for dismissal.");
      return;
    }

    if (!canAcceptRisks && !hasPermission(currentRole, dismissingItem.required_permission as Permission)) {
      setDismissError(`Permission Denied: Your role (${currentRole}) lacks 'risks.accept' permission.`);
      return;
    }

    dismissRiskMutation.mutate({
      item: dismissingItem,
      reason: parsed.data.reason,
    });
  };

  const handleRequestEvidenceSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!requestingItem) return;
    setRequestError(null);

    const parsed = riskRequestEvidenceSchema.safeParse({
      reason: requestReason,
      requested_details: requestDetails,
    });
    if (!parsed.success) {
      setRequestError(parsed.error.issues[0]?.message || "A justification reason is required to request more evidence.");
      return;
    }

    if (!canAcceptRisks && !hasPermission(currentRole, requestingItem.required_permission as Permission)) {
      setRequestError(`Permission Denied: Your role (${currentRole}) lacks 'risks.accept' permission.`);
      return;
    }

    requestEvidenceMutation.mutate({
      item: requestingItem,
      reason: parsed.data.reason,
      requestedDetails: parsed.data.requested_details,
    });
  };

  const handleConvertSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!convertingItem) return;
    setConvertError(null);

    const parsed = riskConvertChangeOrderSchema.safeParse({
      change_order_reference: convertRef,
      change_order_title: convertTitle,
      reason: convertReason,
      amount: convertAmount || undefined,
      time_impact_days: convertDays ? parseInt(convertDays, 10) : undefined,
    });
    if (!parsed.success) {
      setConvertError(parsed.error.issues[0]?.message || "Please complete all mandatory change order fields.");
      return;
    }

    if (!canWriteChanges && !hasPermission(currentRole, "risks.accept" as Permission)) {
      setConvertError(`Permission Denied: Your role (${currentRole}) lacks 'change_orders.write' permission.`);
      return;
    }

    convertChangeOrderMutation.mutate({
      item: convertingItem,
      reference: parsed.data.change_order_reference,
      title: parsed.data.change_order_title,
      reason: parsed.data.reason,
      amount: parsed.data.amount,
      timeImpactDays: parsed.data.time_impact_days,
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

    if (!canAcceptRisks && !hasPermission(currentRole, overridingItem.required_permission as Permission)) {
      setOverrideError(`Permission Denied: Your role (${currentRole}) lacks authority to override system findings.`);
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

  // Helper open modal functions
  const openAcceptModal = (item: ReviewItem) => {
    setAcceptingItem(item);
    setAcceptReason("");
    setAcceptError(null);
  };

  const openDismissModal = (item: ReviewItem) => {
    setDismissingItem(item);
    setDismissReason("");
    setDismissError(null);
  };

  const openRequestEvidenceModal = (item: ReviewItem) => {
    setRequestingItem(item);
    setRequestReason("");
    setRequestDetails("Contemporaneous site records, calibrated sensor logs, or certified laboratory test reports");
    setRequestError(null);
  };

  const openConvertModal = (item: ReviewItem) => {
    setConvertingItem(item);
    setConvertRef(item.change_order_reference || `CO-${item.project_code.replace(/\D/g, "") || "025"}`);
    setConvertTitle(item.title);
    setConvertReason("");
    setConvertAmount(item.financial_exposure || "");
    setConvertDays(item.schedule_impact_days !== null ? String(item.schedule_impact_days) : "");
    setConvertError(null);
  };

  const openOverrideModal = (item: ReviewItem) => {
    setOverridingItem(item);
    setOverrideSeverity(item.severity);
    setOverrideDays(item.schedule_impact_days !== null ? String(item.schedule_impact_days) : "");
    setOverrideExposure(item.financial_exposure || "");
    setOverrideReason("");
    setOverrideError(null);
  };

  const openEditModal = (item: ReviewItem) => {
    setEditingItem(item);
    setEditTitle(item.title);
    setEditCorrection(item.recommended_action || item.recommended_correction);
    setEditExposure(item.financial_exposure || "");
    setEditDays(item.schedule_impact_days !== null ? String(item.schedule_impact_days) : "");
    setEditReason("");
    setEditError(null);
  };

  const renderStatusBadge = (status: string) => {
    switch (status) {
      case "accepted":
      case "approved":
        return <Badge tone="success">{status.toUpperCase()}</Badge>;
      case "dismissed":
      case "rejected":
        return <Badge tone="danger">{status.toUpperCase()}</Badge>;
      case "evidence_requested":
        return <Badge tone="warning">EVIDENCE REQUESTED</Badge>;
      case "converted":
        return <Badge tone="brand">CONVERTED TO CO</Badge>;
      case "insufficient_evidence":
        return <Badge tone="danger">INSUFFICIENT EVIDENCE</Badge>;
      case "overridden":
        return <Badge tone="brand">OVERRIDDEN</Badge>;
      case "pending":
      default:
        return <Badge tone="neutral">PENDING REVIEW</Badge>;
    }
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
                <h1 className="text-2xl font-bold tracking-tight text-ink">Review Queue & Risk Approvals</h1>
                <p className="text-xs text-ink-muted">
                  Audited commercial, contractual, and technical verification for risks and change variances
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

        {/* Permission-Denied Banner State if user role lacks commercial authority */}
        {!isAuthorized && (
          <div
            role="status"
            className="rounded-lg border border-warning/40 bg-warning-soft/30 p-3.5 flex items-start gap-3 text-xs text-ink"
          >
            <IconLock className="size-5 text-warning shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold text-warning-strong">
                Read-Only Review Mode (Role: {currentRole})
              </span>
              <p className="text-ink-muted mt-0.5 leading-relaxed">
                Your role does not possess commercial sign-off permissions (&lsquo;risks.accept&rsquo; or
                &lsquo;approvals.decide&rsquo;). You may inspect source excerpts, quotations, and audit trails. Decision
                actions (Accept, Dismiss, Request Evidence, Convert) require Commercial Manager, Project Manager, or Admin authority.
              </p>
            </div>
          </div>
        )}

        {/* Category Pills Navigation (including 6 core required categories) */}
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
              placeholder="Search by title, risk type, quotations, findings, or code..."
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
              <option value="accepted">Accepted</option>
              <option value="dismissed">Dismissed</option>
              <option value="evidence_requested">Evidence Requested</option>
              <option value="converted">Converted to Change Order</option>
              <option value="insufficient_evidence">Insufficient Evidence</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
              <option value="overridden">Overridden</option>
            </select>
          </div>
        </div>

        {/* Items List Content with clear loading, empty, error states */}
        {isItemsLoading ? (
          <LoadingSkeleton rows={4} variant="cards" />
        ) : isItemsError ? (
          <ErrorState
            title="Failed to Load Review Queue"
            message={errorMessage(itemsError, "Could not fetch review items from the server.")}
            onRetry={() => refetchItems()}
          />
        ) : filteredItems.length > 0 ? (
          <div className="flex flex-col gap-5">
            {filteredItems.map((item) => {
              const meta = REVIEW_CATEGORY_META[item.category];
              const isInsufficientEvidence =
                item.category === "insufficient_evidence_risk" ||
                item.status === "insufficient_evidence" ||
                item.evidence_links.length === 0;

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
                        {/* 1. Category */}
                        <Badge tone={meta.tone}>{meta.label}</Badge>

                        {/* Project Code */}
                        <span className="rounded bg-subtle px-2 py-0.5 font-mono text-[11px] font-medium text-ink-muted">
                          {item.project_code}
                        </span>

                        {/* 2. Risk Type */}
                        <Badge tone="neutral">
                          <span className="capitalize font-mono text-[10px]">
                            TYPE: {(item.risk_type || "commercial_risk").replace(/_/g, " ")}
                          </span>
                        </Badge>

                        {/* Severity */}
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

                        {/* 3. Confidence Badge */}
                        {item.confidence !== null && item.confidence !== undefined && (
                          <Badge
                            tone={
                              item.confidence >= 0.85
                                ? "success"
                                : item.confidence >= 0.6
                                ? "warning"
                                : "danger"
                            }
                          >
                            {Math.round(item.confidence * 100)}% Extraction Confidence
                          </Badge>
                        )}
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

                        {/* 8. Current Status */}
                        {renderStatusBadge(item.status)}
                      </div>
                    </div>

                    {/* 1. Title */}
                    <div className="mt-2 flex flex-col sm:flex-row sm:items-baseline sm:justify-between gap-1">
                      <CardTitle className="text-base font-bold text-ink">{item.title}</CardTitle>

                      {/* 6. Link to Original Document */}
                      <a
                        href={item.original_document_url || `/documents/${item.document_id || item.entity_id}`}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1.5 text-xs text-brand hover:underline font-semibold shrink-0"
                      >
                        <IconDocument className="size-3.5 text-brand" />
                        <span>Original Document: {item.document_id || "source-document"}</span>
                        <IconExternalLink className="size-3 text-brand" />
                      </a>
                    </div>
                  </CardHeader>

                  <CardBody className="flex flex-col gap-4 text-xs pt-4">
                    {/* Findings & Why Review Is Needed */}
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

                    {/* 4 & 5. Evidence Links with Source Quotation and Page */}
                    {item.evidence_links.length > 0 ? (
                      <div className="rounded-lg border border-border bg-surface p-3">
                        <div className="flex items-center justify-between pb-2 border-b border-border/50">
                          <span className="font-semibold text-ink flex items-center gap-1.5">
                            <IconDocument className="size-4 text-ink-muted" />
                            Evidence Links ({item.evidence_links.length})
                          </span>
                          <span className="text-[11px] text-ink-muted">
                            Verified citations with page numbers, verbatim quotations & confidence
                          </span>
                        </div>

                        <div className="divide-y divide-border/40 pt-1">
                          {item.evidence_links.map((link) => {
                            const page = link.source_page ?? link.page_number;
                            const quotation = link.source_quotation || link.excerpt;
                            const docUrl =
                              link.original_document_url || `/documents/${link.document_id || link.source_id}`;

                            return (
                              <div
                                key={link.id}
                                className="py-2.5 flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3"
                              >
                                <div className="flex flex-col gap-1 max-w-2xl">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <span className="font-semibold text-ink">{link.document_name}</span>
                                    {page && (
                                      <span className="rounded bg-subtle px-1.5 py-0.5 font-mono text-[10px] text-ink-muted">
                                        Page {page}
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
                                    <a
                                      href={docUrl}
                                      target="_blank"
                                      rel="noreferrer"
                                      className="inline-flex items-center gap-1 text-[11px] text-brand hover:underline font-mono"
                                    >
                                      <span>Source Document</span>
                                      <IconExternalLink className="size-2.5" />
                                    </a>
                                  </div>

                                  {/* 5. Source Quotation */}
                                  <p className="text-[11px] text-ink-muted italic border-l-2 border-border pl-2 my-0.5 leading-relaxed">
                                    &ldquo;{quotation}&rdquo;
                                  </p>
                                </div>

                                <Button
                                  size="sm"
                                  variant="ghost"
                                  className="shrink-0 text-brand text-xs"
                                  onClick={() => setInspectingEvidence({ item, link })}
                                >
                                  <IconExternalLink className="size-3.5" />
                                  <span>Inspect Excerpt</span>
                                </Button>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ) : (
                      /* Insufficient Evidence Warning Banner */
                      <div className="rounded-lg border border-danger/30 bg-danger-soft/20 p-3.5 flex items-start gap-2.5 text-xs text-ink">
                        <IconAlertTriangle className="size-4 text-danger shrink-0 mt-0.5" />
                        <div>
                          <span className="font-semibold text-danger">
                            Insufficient Evidence: Zero Substantiating Citations
                          </span>
                          <p className="text-ink-muted mt-0.5 leading-relaxed">
                            This risk notification was logged without contemporaneous site logs, calibrated telemetry,
                            or certified lab assays. Under governance rules,{" "}
                            <strong>insufficient-evidence risks cannot be accepted as supported evidence</strong>. You
                            may dismiss the claim or request verified evidence from the contractor.
                          </p>
                        </div>
                      </div>
                    )}

                    {/* 7. Recommended Action */}
                    <div className="rounded-lg border border-brand/20 bg-brand-soft/30 p-3.5 flex flex-col gap-1.5">
                      <div className="flex items-center gap-1.5 font-semibold text-brand">
                        <IconCheckCircle className="size-4 text-brand shrink-0" />
                        <span>Recommended Action</span>
                      </div>
                      <p className="text-ink leading-relaxed font-medium">
                        {item.recommended_action || item.recommended_correction}
                      </p>
                    </div>

                    {/* Action Controls & Audit History Bar */}
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-t border-border pt-3 mt-1">
                      {/* Left: Audit History trigger */}
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setHistoryItem(item)}
                        className="text-ink-muted hover:text-ink text-xs"
                      >
                        <IconHistory className="size-4" />
                        <span>Audit history ({item.audit_history.length})</span>
                      </Button>

                      {/* Right: Decision Actions: Accept, Dismiss, Request Evidence, Convert, Override */}
                      <div className="flex flex-wrap items-center gap-2">
                        {/* Action 1: Accept Risk (Protected: Cannot accept if insufficient evidence, requires risks.accept) */}
                        {isInsufficientEvidence ? (
                          <div className="relative group inline-block">
                            <Button
                              size="sm"
                              variant="secondary"
                              disabled
                              className="opacity-60 cursor-not-allowed bg-subtle text-ink-muted"
                            >
                              <IconLock className="size-3.5 text-danger shrink-0" />
                              <span>Accept risk</span>
                            </Button>
                            <div className="absolute right-0 bottom-full mb-1 hidden w-64 rounded-md bg-ink p-2 text-[11px] text-white shadow-lg group-hover:block z-30">
                              <p className="font-semibold text-danger-soft">Governance Constraint</p>
                              <p className="mt-0.5">
                                Insufficient-evidence risks cannot be accepted as supported evidence.
                              </p>
                            </div>
                          </div>
                        ) : !canAcceptRisks ? (
                          <div className="relative group inline-block">
                            <Button
                              size="sm"
                              variant="secondary"
                              disabled
                              className="opacity-60 cursor-not-allowed bg-subtle text-ink-muted"
                            >
                              <IconLock className="size-3.5 text-danger shrink-0" />
                              <span>Accept risk</span>
                            </Button>
                            <div className="absolute right-0 bottom-full mb-1 hidden w-64 rounded-md bg-ink p-2 text-[11px] text-white shadow-lg group-hover:block z-30">
                              <p className="font-semibold text-danger-soft">Unauthorized Action</p>
                              <p className="mt-0.5">
                                Requires &lsquo;risks.accept&rsquo; authority. Role &lsquo;{currentRole}&rsquo; is read-only.
                              </p>
                            </div>
                          </div>
                        ) : (
                          <Button
                            size="sm"
                            variant="primary"
                            onClick={() => openAcceptModal(item)}
                            disabled={item.status === "accepted" || item.status === "approved"}
                          >
                            <IconCheck className="size-3.5" />
                            <span>{item.status === "accepted" ? "Accepted" : "Accept risk"}</span>
                          </Button>
                        )}

                        {/* Action 2: Dismiss Risk (Requires reason) */}
                        {!canAcceptRisks ? (
                          <div className="relative group inline-block">
                            <Button
                              size="sm"
                              variant="secondary"
                              disabled
                              className="opacity-60 cursor-not-allowed bg-subtle text-ink-muted"
                            >
                              <IconLock className="size-3.5 text-danger shrink-0" />
                              <span>Dismiss</span>
                            </Button>
                            <div className="absolute right-0 bottom-full mb-1 hidden w-60 rounded-md bg-ink p-2 text-[11px] text-white shadow-lg group-hover:block z-30">
                              <p className="font-semibold text-danger-soft">Unauthorized Action</p>
                              <p className="mt-0.5">Requires &lsquo;risks.accept&rsquo; authority to dismiss risk.</p>
                            </div>
                          </div>
                        ) : (
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => openDismissModal(item)}
                            disabled={item.status === "dismissed"}
                            className="hover:border-danger hover:text-danger"
                          >
                            <IconX className="size-3.5" />
                            <span>Dismiss risk</span>
                          </Button>
                        )}

                        {/* Action 3: Request More Evidence */}
                        {!canAcceptRisks ? (
                          <div className="relative group inline-block">
                            <Button
                              size="sm"
                              variant="secondary"
                              disabled
                              className="opacity-60 cursor-not-allowed bg-subtle text-ink-muted"
                            >
                              <IconLock className="size-3.5 text-danger shrink-0" />
                              <span>Request evidence</span>
                            </Button>
                            <div className="absolute right-0 bottom-full mb-1 hidden w-60 rounded-md bg-ink p-2 text-[11px] text-white shadow-lg group-hover:block z-30">
                              <p className="font-semibold text-danger-soft">Unauthorized Action</p>
                              <p className="mt-0.5">Requires commercial review permissions.</p>
                            </div>
                          </div>
                        ) : (
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => openRequestEvidenceModal(item)}
                            disabled={item.status === "evidence_requested"}
                          >
                            <IconSearch className="size-3.5" />
                            <span>Request evidence</span>
                          </Button>
                        )}

                        {/* Action 4: Convert Risk to Change Order */}
                        {!canWriteChanges ? (
                          <div className="relative group inline-block">
                            <Button
                              size="sm"
                              variant="secondary"
                              disabled
                              className="opacity-60 cursor-not-allowed bg-subtle text-ink-muted"
                            >
                              <IconLock className="size-3.5 text-danger shrink-0" />
                              <span>Convert to CO</span>
                            </Button>
                            <div className="absolute right-0 bottom-full mb-1 hidden w-64 rounded-md bg-ink p-2 text-[11px] text-white shadow-lg group-hover:block z-30">
                              <p className="font-semibold text-danger-soft">Unauthorized Action</p>
                              <p className="mt-0.5">
                                Requires &lsquo;change_orders.write&rsquo; authority to convert risks.
                              </p>
                            </div>
                          </div>
                        ) : (
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => openConvertModal(item)}
                            disabled={item.status === "converted"}
                          >
                            <IconEdit className="size-3.5" />
                            <span>Convert to CO</span>
                          </Button>
                        )}

                        {/* Action 5: Override (for risks and critical items) */}
                        {canAcceptRisks && (
                          <Button size="sm" variant="secondary" onClick={() => openOverrideModal(item)}>
                            <IconScale className="size-3.5" />
                            <span>Override</span>
                          </Button>
                        )}

                        {/* Action 6: Edit */}
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => openEditModal(item)}
                          disabled={item.status === "accepted" || item.status === "approved"}
                          className="text-ink-muted hover:text-ink"
                        >
                          <IconEdit className="size-3.5" />
                          <span>Edit</span>
                        </Button>
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
            description="All automated extractions, risk notifications, and change variances have been verified and audited."
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

        {/* Modal 1: Accept Risk Modal */}
        <Modal
          open={acceptingItem !== null}
          title={`Accept Risk: ${acceptingItem?.title ?? ""}`}
          onClose={() => setAcceptingItem(null)}
          actions={
            <>
              <Button variant="ghost" size="sm" onClick={() => setAcceptingItem(null)}>
                Cancel
              </Button>
              <Button
                size="sm"
                type="submit"
                form="accept-risk-form"
                loading={acceptRiskMutation.isPending}
              >
                Confirm & Accept
              </Button>
            </>
          }
        >
          <form id="accept-risk-form" onSubmit={handleAcceptSubmit} className="flex flex-col gap-3">
            {acceptError && (
              <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft p-2.5 text-xs text-danger">
                {acceptError}
              </div>
            )}

            <div className="rounded-lg border border-border bg-subtle/50 p-3 text-xs flex flex-col gap-1.5">
              <span className="font-semibold text-ink">Risk Acceptance Verification</span>
              <p className="text-ink-muted">
                Accepting this item formally incorporates this risk into project exposure under actor &lsquo;
                {currentRole}&rsquo;.
              </p>
              {acceptingItem?.financial_exposure && (
                <p className="font-semibold text-ink">
                  Financial Exposure: {Number(acceptingItem.financial_exposure).toLocaleString()}{" "}
                  {acceptingItem.currency}
                </p>
              )}
            </div>

            <Field
              id="acc-reason"
              label="Acceptance Rationale / Note"
              hint="Recorded in the immutable project audit log"
            >
              <Input
                id="acc-reason"
                value={acceptReason}
                onChange={(e) => setAcceptReason(e.target.value)}
                placeholder="Rationale for accepting risk into project baseline..."
              />
            </Field>
          </form>
        </Modal>

        {/* Modal 2: Dismiss Risk Modal (Mandatory Reason Required) */}
        <Modal
          open={dismissingItem !== null}
          title={`Dismiss Risk: ${dismissingItem?.title ?? ""}`}
          onClose={() => setDismissingItem(null)}
          actions={
            <>
              <Button variant="ghost" size="sm" onClick={() => setDismissingItem(null)}>
                Cancel
              </Button>
              <Button
                size="sm"
                variant="primary"
                type="submit"
                form="dismiss-risk-form"
                loading={dismissRiskMutation.isPending}
                className="bg-danger hover:bg-danger/90 text-white"
              >
                Confirm Dismissal
              </Button>
            </>
          }
        >
          <form id="dismiss-risk-form" onSubmit={handleDismissSubmit} className="flex flex-col gap-3">
            {dismissError && (
              <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft p-2.5 text-xs text-danger">
                {dismissError}
              </div>
            )}

            <div className="rounded-lg border border-danger/20 bg-danger-soft/20 p-3 text-xs text-ink flex items-start gap-2">
              <IconAlertCircle className="size-4 text-danger shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold text-danger">Mandatory Audit Justification</span>
                <p className="text-ink-muted mt-0.5">
                  Dismissing a risk requires an audited justification reason explaining why the notification is invalid
                  or rejected.
                </p>
              </div>
            </div>

            <Field
              id="dism-reason"
              label="Dismissal Justification"
              hint="Mandatory grounds for dismissal (e.g. disproven by telemetry or duplicate submission)"
              required
            >
              <textarea
                id="dism-reason"
                rows={3}
                value={dismissReason}
                onChange={(e) => setDismissReason(e.target.value)}
                placeholder="State the contractual or factual grounds for dismissal..."
                required
                className="w-full rounded-md border border-border bg-surface p-2.5 text-xs text-ink placeholder:text-ink-muted focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
              />
            </Field>
          </form>
        </Modal>

        {/* Modal 3: Request More Evidence Modal (Mandatory Reason) */}
        <Modal
          open={requestingItem !== null}
          title={`Request More Evidence: ${requestingItem?.title ?? ""}`}
          onClose={() => setRequestingItem(null)}
          actions={
            <>
              <Button variant="ghost" size="sm" onClick={() => setRequestingItem(null)}>
                Cancel
              </Button>
              <Button
                size="sm"
                type="submit"
                form="request-evidence-form"
                loading={requestEvidenceMutation.isPending}
              >
                Submit Evidence Request
              </Button>
            </>
          }
        >
          <form id="request-evidence-form" onSubmit={handleRequestEvidenceSubmit} className="flex flex-col gap-3">
            {requestError && (
              <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft p-2.5 text-xs text-danger">
                {requestError}
              </div>
            )}

            <div className="rounded-lg border border-brand/20 bg-brand-soft/20 p-3 text-xs text-ink flex items-start gap-2">
              <IconSearch className="size-4 text-brand shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold text-brand">Subcontractor Evidence Requirement</span>
                <p className="text-ink-muted mt-0.5">
                  Formal notice will be audited requesting certified substantiate records before commercial evaluation.
                </p>
              </div>
            </div>

            <Field
              id="req-reason"
              label="Evidence Request Rationale"
              hint="Explain why current records are insufficient"
              required
            >
              <Input
                id="req-reason"
                value={requestReason}
                onChange={(e) => setRequestReason(e.target.value)}
                placeholder="e.g. Lacks certified third-party lab assays or daily foreman signatures..."
                required
              />
            </Field>

            <Field
              id="req-details"
              label="Specific Items Requested"
              hint="List the specific documents, tickets, or telemetry records required"
            >
              <textarea
                id="req-details"
                rows={3}
                value={requestDetails}
                onChange={(e) => setRequestDetails(e.target.value)}
                placeholder="e.g. Certified delivery note tickets, geotechnical soil tests, daily site weather logs..."
                className="w-full rounded-md border border-border bg-surface p-2.5 text-xs text-ink placeholder:text-ink-muted focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
              />
            </Field>
          </form>
        </Modal>

        {/* Modal 4: Convert Risk to Change Order Modal */}
        <Modal
          open={convertingItem !== null}
          title={`Convert to Change Order: ${convertingItem?.title ?? ""}`}
          onClose={() => setConvertingItem(null)}
          actions={
            <>
              <Button variant="ghost" size="sm" onClick={() => setConvertingItem(null)}>
                Cancel
              </Button>
              <Button
                size="sm"
                type="submit"
                form="convert-co-form"
                loading={convertChangeOrderMutation.isPending}
              >
                Create Change Order
              </Button>
            </>
          }
        >
          <form id="convert-co-form" onSubmit={handleConvertSubmit} className="flex flex-col gap-3">
            {convertError && (
              <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft p-2.5 text-xs text-danger">
                {convertError}
              </div>
            )}

            <div className="rounded-lg border border-border bg-surface-raised p-2.5 text-xs text-ink-muted space-y-1">
              <p className="font-semibold text-ink">Grounded Draft Conversion Rules:</p>
              <p>• Creates a draft change order with status &quot;drafted&quot; citing linked evidence.</p>
              <p>• The system does not estimate cost or schedule impact automatically (financial and schedule fields remain null until entered by a human).</p>
              <p>• No external communications will be sent automatically.</p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <Field id="co-ref" label="Change Order Reference" required>
                <Input
                  id="co-ref"
                  value={convertRef}
                  onChange={(e) => setConvertRef(e.target.value)}
                  placeholder="CO-024"
                  required
                />
              </Field>

              <Field id="co-title" label="Change Order Title" required>
                <Input
                  id="co-title"
                  value={convertTitle}
                  onChange={(e) => setConvertTitle(e.target.value)}
                  required
                />
              </Field>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <Field id="co-amt" label="Commercial Amount (USD)">
                <Input
                  id="co-amt"
                  value={convertAmount}
                  onChange={(e) => setConvertAmount(e.target.value)}
                  placeholder="0.00"
                />
              </Field>

              <Field id="co-days" label="Schedule Impact (Days)">
                <Input
                  id="co-days"
                  type="number"
                  value={convertDays}
                  onChange={(e) => setConvertDays(e.target.value)}
                  placeholder="0"
                />
              </Field>
            </div>

            <Field
              id="co-reason"
              label="Conversion Justification Reason"
              hint="Mandatory commercial grounds for formal variation conversion"
              required
            >
              <textarea
                id="co-reason"
                rows={3}
                value={convertReason}
                onChange={(e) => setConvertReason(e.target.value)}
                placeholder="Explain the contractual entitlement and basis for converting this risk to a formal change order..."
                required
                className="w-full rounded-md border border-border bg-surface p-2.5 text-xs text-ink placeholder:text-ink-muted focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
              />
            </Field>
          </form>
        </Modal>

        {/* Modal 5: Override Parameters Modal (Mandatory Reason Required) */}
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
            {overrideError && (
              <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft p-2.5 text-xs text-danger">
                {overrideError}
              </div>
            )}

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

        {/* Modal 6: Edit Modal */}
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
            {editError && (
              <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft p-2.5 text-xs text-danger">
                {editError}
              </div>
            )}

            <Field id="ed-title" label="Title" required>
              <Input
                id="ed-title"
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                required
              />
            </Field>

            <Field id="ed-corr" label="Recommended Action / Correction" required>
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

        {/* Modal 7: Evidence Inspection Modal */}
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
                  {(inspectingEvidence.link.source_page || inspectingEvidence.link.page_number) && (
                    <Badge tone="neutral">
                      Page {inspectingEvidence.link.source_page || inspectingEvidence.link.page_number}
                    </Badge>
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
                  Verbatim Source Quotation
                </span>
                <div className="rounded-lg border border-border bg-subtle p-3.5 font-mono text-xs leading-relaxed text-ink">
                  &ldquo;{inspectingEvidence.link.source_quotation || inspectingEvidence.link.excerpt}&rdquo;
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

        {/* Modal 8: Audit History Modal */}
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
                Immutable chronological log of all automated detections, risk reviews, dismissals, evidence requests, and conversions:
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
