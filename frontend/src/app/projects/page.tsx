"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Field, Input, Select } from "@/components/ui/form";
import { Modal } from "@/components/ui/modal";
import { EmptyState, ErrorState, LoadingSkeleton } from "@/components/ui/states";
import { DataTable, type Column } from "@/components/ui/table";
import { ProtectedRoute } from "@/components/protected-route";
import { IconPlus, IconSearch } from "@/components/icons";
import { projectsApi } from "@/lib/api/resources";
import { errorMessage } from "@/lib/api/errors";
import { useRole } from "@/lib/auth";
import { hasPermission } from "@/lib/rbac";
import {
  projectCreateSchema,
  type Project,
  type ProjectCreate,
  type ProjectStatus,
} from "@/lib/contracts";

export default function ProjectsPage() {
  const queryClient = useQueryClient();
  const role = useRole();
  const canCreate = role ? hasPermission(role, "project.create") : false;

  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [activeSearch, setActiveSearch] = useState("");

  // Create Project Modal state
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [clientName, setClientName] = useState("");
  const [contractValue, setContractValue] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [startDate, setStartDate] = useState("");
  const [expectedEndDate, setExpectedEndDate] = useState("");
  const [description, setDescription] = useState("");
  const [modalErrors, setModalErrors] = useState<Record<string, string>>({});
  const [modalError, setModalError] = useState<string | null>(null);

  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
  } = useQuery({
    queryKey: ["projects", page, statusFilter, activeSearch],
    queryFn: () =>
      projectsApi.list({
        page,
        page_size: 15,
        status: statusFilter === "all" ? null : (statusFilter as ProjectStatus),
        search: activeSearch.trim() || null,
      }),
  });

  const createMutation = useMutation({
    mutationFn: (newProject: ProjectCreate) => projectsApi.create(newProject),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      setIsCreateOpen(false);
      resetModalForm();
    },
    onError: (err) => {
      setModalError(errorMessage(err, "Failed to create project."));
    },
  });

  const resetModalForm = () => {
    setCode("");
    setName("");
    setClientName("");
    setContractValue("");
    setCurrency("USD");
    setStartDate("");
    setExpectedEndDate("");
    setDescription("");
    setModalErrors({});
    setModalError(null);
  };

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setModalErrors({});
    setModalError(null);

    const payload: Record<string, unknown> = {
      code: code.trim().toUpperCase(),
      name: name.trim(),
      client_name: clientName.trim(),
      contract_value: contractValue.trim() || null,
      currency: currency.trim().toUpperCase(),
      start_date: startDate.trim() || null,
      expected_end_date: expectedEndDate.trim() || null,
      description: description.trim() || null,
      status: "active",
    };

    const parsed = projectCreateSchema.safeParse(payload);
    if (!parsed.success) {
      const errMap: Record<string, string> = {};
      for (const issue of parsed.error.issues) {
        const path = issue.path[0];
        if (typeof path === "string" && !errMap[path]) {
          errMap[path] = issue.message;
        }
      }
      setModalErrors(errMap);
      return;
    }

    createMutation.mutate(parsed.data);
  };

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    setActiveSearch(searchQuery);
  };

  const statusTone = (status: ProjectStatus): "success" | "warning" | "neutral" | "danger" => {
    switch (status) {
      case "active":
        return "success";
      case "on_hold":
        return "warning";
      case "completed":
        return "neutral";
      case "cancelled":
      case "archived":
        return "danger";
      default:
        return "neutral";
    }
  };

  const columns: Column<Project>[] = [
    {
      key: "code",
      header: "Project Code",
      render: (project) => (
        <Link
          href={`/projects/${project.id}`}
          className="font-mono text-xs font-semibold text-brand hover:underline"
        >
          {project.code}
        </Link>
      ),
    },
    {
      key: "name",
      header: "Project Name",
      render: (project) => (
        <div>
          <Link
            href={`/projects/${project.id}`}
            className="font-medium text-ink hover:text-brand transition-colors"
          >
            {project.name}
          </Link>
          <div className="text-xs text-ink-muted">{project.client_name}</div>
        </div>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (project) => (
        <Badge tone={statusTone(project.status)}>
          {project.status.replace("_", " ")}
        </Badge>
      ),
    },
    {
      key: "contract_value",
      header: "Contract Value",
      align: "right",
      render: (project) => (
        <div className="tabular text-sm font-medium text-ink">
          {project.contract_value
            ? `${Number(project.contract_value).toLocaleString("en-US", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })} ${project.currency}`
            : "—"}
        </div>
      ),
    },
    {
      key: "timeline",
      header: "Timeline",
      render: (project) => (
        <div className="text-xs text-ink-muted">
          {project.start_date || "—"} &rarr; {project.expected_end_date || "—"}
        </div>
      ),
    },
    {
      key: "actions",
      header: "",
      align: "right",
      render: (project) => (
        <Link href={`/projects/${project.id}`}>
          <Button variant="ghost" size="sm">
            View &rarr;
          </Button>
        </Link>
      ),
    },
  ];

  return (
    <ProtectedRoute>
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 flex flex-col gap-6">
        {/* Page Header */}
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-ink">Projects</h1>
            <p className="mt-1 text-sm text-ink-muted">
              Commercial management, change orders, and risk oversight
            </p>
          </div>
          {canCreate ? (
            <Button onClick={() => setIsCreateOpen(true)} className="sm:self-start">
              <IconPlus className="size-4" />
              <span>New Project</span>
            </Button>
          ) : null}
        </div>

        {/* Filter Controls */}
        <Card>
          <CardBody className="py-3.5">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <form onSubmit={handleSearchSubmit} className="relative flex-1 max-w-md">
                <IconSearch className="pointer-events-none absolute left-3 top-2.5 size-4 text-ink-faint" />
                <Input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search code, name, or client..."
                  className="pl-9 h-9 text-xs"
                />
              </form>

              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-ink-muted">Status:</span>
                <Select
                  value={statusFilter}
                  onChange={(e) => {
                    setStatusFilter(e.target.value);
                    setPage(1);
                  }}
                  className="h-9 text-xs w-36"
                >
                  <option value="all">All Statuses</option>
                  <option value="active">Active</option>
                  <option value="on_hold">On Hold</option>
                  <option value="completed">Completed</option>
                  <option value="cancelled">Cancelled</option>
                  <option value="archived">Archived</option>
                </Select>
              </div>
            </div>
          </CardBody>
        </Card>

        {/* Query Results / Table / States */}
        {isLoading ? (
          <LoadingSkeleton rows={5} variant="table" />
        ) : isError ? (
          <ErrorState
            title="Failed to Load Projects"
            message={errorMessage(error, "Cannot load projects right now.")}
            onRetry={() => refetch()}
          />
        ) : data && data.items.length > 0 ? (
          <div className="flex flex-col gap-4">
            <DataTable
              caption="List of construction projects"
              captionHidden
              columns={columns}
              rows={data.items}
              rowKey={(item) => item.id}
            />

            {/* Pagination */}
            {data.metadata.total_pages > 1 ? (
              <div className="flex items-center justify-between border-t border-border pt-4">
                <p className="text-xs text-ink-muted">
                  Showing page <span className="font-semibold text-ink">{data.metadata.page}</span> of{" "}
                  <span className="font-semibold text-ink">{data.metadata.total_pages}</span> (
                  {data.metadata.total_items} total)
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={!data.metadata.has_previous}
                    onClick={() => setPage((p) => Math.max(p - 1, 1))}
                  >
                    Previous
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={!data.metadata.has_next}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    Next
                  </Button>
                </div>
              </div>
            ) : null}
          </div>
        ) : (
          <EmptyState
            title="No projects found"
            description={
              activeSearch || statusFilter !== "all"
                ? "No projects match your current search and filter criteria."
                : "Get started by creating your first construction project."
            }
            action={
              canCreate ? (
                <Button onClick={() => setIsCreateOpen(true)} size="sm">
                  <IconPlus className="size-4" />
                  <span>Create Project</span>
                </Button>
              ) : undefined
            }
          />
        )}

        {/* Create Project Modal */}
        <Modal
          open={isCreateOpen}
          title="Create New Project"
          onClose={() => {
            setIsCreateOpen(false);
            resetModalForm();
          }}
          actions={
            <>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setIsCreateOpen(false);
                  resetModalForm();
                }}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                type="submit"
                form="create-project-form"
                loading={createMutation.isPending}
              >
                Create Project
              </Button>
            </>
          }
        >
          <form id="create-project-form" onSubmit={handleCreateSubmit} className="flex flex-col gap-3.5">
            {modalError ? (
              <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft p-2.5 text-xs text-danger">
                {modalError}
              </div>
            ) : null}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field id="proj-code" label="Project Code" error={modalErrors["code"]} required>
                <Input
                  id="proj-code"
                  value={code}
                  onChange={(e) => setCode(e.target.value.toUpperCase())}
                  placeholder="PRJ-2026-001"
                  invalid={!!modalErrors["code"]}
                  required
                />
              </Field>

              <Field id="proj-name" label="Project Name" error={modalErrors["name"]} required>
                <Input
                  id="proj-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="City Hospital Wing B"
                  invalid={!!modalErrors["name"]}
                  required
                />
              </Field>
            </div>

            <Field id="proj-client" label="Client / Employer" error={modalErrors["client_name"]} required>
              <Input
                id="proj-client"
                value={clientName}
                onChange={(e) => setClientName(e.target.value)}
                placeholder="Metropolitan Health Authority"
                invalid={!!modalErrors["client_name"]}
                required
              />
            </Field>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="sm:col-span-2">
                <Field id="proj-value" label="Contract Value" error={modalErrors["contract_value"]}>
                  <Input
                    id="proj-value"
                    value={contractValue}
                    onChange={(e) => setContractValue(e.target.value)}
                    placeholder="12500000.00"
                    invalid={!!modalErrors["contract_value"]}
                  />
                </Field>
              </div>

              <Field id="proj-curr" label="Currency" error={modalErrors["currency"]}>
                <Input
                  id="proj-curr"
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value.toUpperCase())}
                  placeholder="USD"
                  maxLength={3}
                  invalid={!!modalErrors["currency"]}
                />
              </Field>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Field id="proj-start" label="Start Date" error={modalErrors["start_date"]}>
                <Input
                  id="proj-start"
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  invalid={!!modalErrors["start_date"]}
                />
              </Field>

              <Field id="proj-end" label="Expected End Date" error={modalErrors["expected_end_date"]}>
                <Input
                  id="proj-end"
                  type="date"
                  value={expectedEndDate}
                  onChange={(e) => setExpectedEndDate(e.target.value)}
                  invalid={!!modalErrors["expected_end_date"]}
                />
              </Field>
            </div>

            <Field id="proj-desc" label="Description" error={modalErrors["description"]}>
              <Input
                id="proj-desc"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="High-level project scope..."
                invalid={!!modalErrors["description"]}
              />
            </Field>
          </form>
        </Modal>
      </div>
    </ProtectedRoute>
  );
}

