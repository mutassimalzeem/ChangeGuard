"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { ProtectedRoute } from "@/components/protected-route";
import { IconCheck, IconLogOut, IconSettings } from "@/components/icons";
import { formatRole, roleBadgeTone } from "@/components/app-header";
import { systemApi } from "@/lib/api/resources";
import { useAuth, useRole } from "@/lib/auth";
import { config } from "@/lib/config";
import { hasPermission, type Permission } from "@/lib/rbac";

export default function SettingsPage() {
  const { session, signOut } = useAuth();
  const role = useRole();

  const [activeTab, setActiveTab] = useState<"profile" | "permissions" | "system">("profile");

  const {
    data: health,
    isLoading: isHealthLoading,
    isError: isHealthError,
    refetch: refetchHealth,
  } = useQuery({
    queryKey: ["system-health"],
    queryFn: () => systemApi.health(),
    retry: 1,
  });

  const permissionGroups: { title: string; items: Permission[] }[] = [
    {
      title: "Project Management",
      items: [
        "project.read",
        "project.create",
        "project.update",
        "project.delete",
        "project.members.manage",
      ],
    },
    {
      title: "Documents & Evidence",
      items: ["documents.read", "documents.write"],
    },
    {
      title: "Contracts & Scope",
      items: ["contracts.read", "contracts.write", "contracts.commit", "rfis.write"],
    },
    {
      title: "Change Orders & Approvals",
      items: ["change_orders.write", "change_orders.submit", "approvals.decide"],
    },
    {
      title: "Risk Governance",
      items: ["risks.write", "risks.accept"],
    },
    {
      title: "Commercial & Financial",
      items: ["financial.read", "financial.write", "financial.release"],
    },
    {
      title: "Tenant & Administration",
      items: ["tenant.read", "tenant.manage", "users.manage", "audit.read"],
    },
  ];

  return (
    <ProtectedRoute>
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 flex flex-col gap-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2.5">
              <div className="flex size-8 items-center justify-center rounded-lg bg-subtle text-ink">
                <IconSettings className="size-5" />
              </div>
              <h1 className="text-2xl font-bold tracking-tight text-ink">Settings & Governance</h1>
            </div>
            <p className="mt-1 text-sm text-ink-muted">
              Manage your session, view assigned RBAC role permissions, and check system connectivity
            </p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => signOut()}
            className="text-danger hover:bg-danger-soft hover:text-danger"
          >
            <IconLogOut className="size-4" />
            <span>Sign Out</span>
          </Button>
        </div>

        {/* Navigation Tabs */}
        <div className="flex items-center gap-2 border-b border-border">
          <button
            type="button"
            onClick={() => setActiveTab("profile")}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              activeTab === "profile"
                ? "border-brand text-brand font-semibold"
                : "border-transparent text-ink-muted hover:text-ink"
            }`}
          >
            User Profile & Session
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("permissions")}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              activeTab === "permissions"
                ? "border-brand text-brand font-semibold"
                : "border-transparent text-ink-muted hover:text-ink"
            }`}
          >
            Role Permissions Matrix
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("system")}
            className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              activeTab === "system"
                ? "border-brand text-brand font-semibold"
                : "border-transparent text-ink-muted hover:text-ink"
            }`}
          >
            API & Environment Status
          </button>
        </div>

        {/* Tab 1: Profile & Session */}
        {activeTab === "profile" && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Session Identity</CardTitle>
              </CardHeader>
              <CardBody className="flex flex-col gap-4 text-sm">
                <div>
                  <span className="text-xs text-ink-muted font-semibold uppercase">User Subject (UUID)</span>
                  <p className="font-mono text-ink mt-0.5 break-all">{session?.userId || "—"}</p>
                </div>
                <div className="border-t border-border pt-3">
                  <span className="text-xs text-ink-muted font-semibold uppercase">Assigned Roles</span>
                  <div className="mt-1 flex flex-wrap gap-2">
                    {session?.roles && session.roles.length > 0 ? (
                      session.roles.map((r) => (
                        <Badge key={r} tone={roleBadgeTone(r)}>
                          {formatRole(r)}
                        </Badge>
                      ))
                    ) : (
                      <Badge tone="neutral">No roles assigned</Badge>
                    )}
                  </div>
                </div>
                <div className="border-t border-border pt-3">
                  <span className="text-xs text-ink-muted font-semibold uppercase">Tenant / Workspace ID</span>
                  <p className="font-mono text-ink mt-0.5">{session?.tenantId || "None (Global context)"}</p>
                </div>
                <div className="border-t border-border pt-3">
                  <span className="text-xs text-ink-muted font-semibold uppercase">Token Expiration</span>
                  <p className="text-ink mt-0.5">
                    {session?.expiresAt
                      ? new Date(session.expiresAt).toLocaleString()
                      : "Managed in memory"}
                  </p>
                </div>
              </CardBody>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Governance Model</CardTitle>
              </CardHeader>
              <CardBody className="flex flex-col gap-3 text-xs text-ink leading-relaxed">
                <p>
                  ChangeGuard implements audited, role-based access control with tamper-evident audit
                  event recording.
                </p>
                <ul className="list-disc pl-4 flex flex-col gap-1 text-ink-muted">
                  <li>Actions are verified on the backend for every API invocation.</li>
                  <li>Overriding risk severity or schedule impact requires audited justification.</li>
                  <li>
                    Change orders cannot transition directly from variance to approved commitment
                    without documented commercial review.
                  </li>
                </ul>
              </CardBody>
            </Card>
          </div>
        )}

        {/* Tab 2: Permissions Matrix */}
        {activeTab === "permissions" && (
          <div className="flex flex-col gap-6">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-semibold text-ink">
                  Permissions Matrix for {formatRole(role)}
                </h2>
                <p className="text-xs text-ink-muted">
                  Client-side capabilities enforced by ChangeGuard RBAC policy
                </p>
              </div>
              <Badge tone={roleBadgeTone(role)}>{formatRole(role)}</Badge>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {permissionGroups.map((group) => (
                <Card key={group.title} className="flex flex-col">
                  <CardHeader className="py-3 px-4">
                    <CardTitle className="text-xs uppercase text-ink-muted tracking-wider">
                      {group.title}
                    </CardTitle>
                  </CardHeader>
                  <CardBody className="py-2 px-4 flex flex-col divide-y divide-border">
                    {group.items.map((perm) => {
                      const granted = role ? hasPermission(role, perm) : false;
                      return (
                        <div key={perm} className="flex items-center justify-between py-2 text-xs">
                          <span className="font-mono text-ink">{perm}</span>
                          {granted ? (
                            <span className="flex items-center gap-1 text-success font-semibold">
                              <IconCheck className="size-3.5" />
                              <span>Granted</span>
                            </span>
                          ) : (
                            <span className="text-ink-faint">—</span>
                          )}
                        </div>
                      );
                    })}
                  </CardBody>
                </Card>
              ))}
            </div>
          </div>
        )}

        {/* Tab 3: System Status */}
        {activeTab === "system" && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Environment & API Configuration</CardTitle>
              </CardHeader>
              <CardBody className="flex flex-col gap-4 text-sm">
                <div>
                  <span className="text-xs text-ink-muted font-semibold uppercase">API Base URL</span>
                  <p className="font-mono text-ink mt-0.5 break-all">{config.apiBaseUrl}</p>
                </div>
                <div className="border-t border-border pt-3">
                  <span className="text-xs text-ink-muted font-semibold uppercase">Query Stale Time</span>
                  <p className="text-ink mt-0.5">{config.queryStaleTimeMs / 1000} seconds</p>
                </div>
                <div className="border-t border-border pt-3">
                  <span className="text-xs text-ink-muted font-semibold uppercase">Request Timeout</span>
                  <p className="text-ink mt-0.5">{config.requestTimeoutMs / 1000} seconds</p>
                </div>
              </CardBody>
            </Card>

            <Card>
              <CardHeader>
                <div className="flex items-center justify-between w-full">
                  <CardTitle>Live Backend Connectivity</CardTitle>
                  <Button variant="ghost" size="sm" onClick={() => refetchHealth()}>
                    Check Now
                  </Button>
                </div>
              </CardHeader>
              <CardBody className="flex flex-col gap-4 text-sm">
                <div>
                  <span className="text-xs text-ink-muted font-semibold uppercase">Health Endpoint</span>
                  <p className="font-mono text-ink mt-0.5">{config.apiBaseUrl}/health</p>
                </div>
                <div className="border-t border-border pt-3">
                  <span className="text-xs text-ink-muted font-semibold uppercase">Status</span>
                  <div className="mt-1">
                    {isHealthLoading ? (
                      <Badge tone="neutral">Checking...</Badge>
                    ) : isHealthError ? (
                      <Badge tone="danger">Disconnected / Unreachable</Badge>
                    ) : (
                      <Badge tone="success">
                        Operational ({health?.status ?? "online"})
                      </Badge>
                    )}
                  </div>
                </div>
              </CardBody>
            </Card>
          </div>
        )}
      </div>
    </ProtectedRoute>
  );
}

