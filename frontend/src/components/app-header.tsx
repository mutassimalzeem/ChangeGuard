"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuth, useRole } from "@/lib/auth";
import { hasAnyPermission, type Permission } from "@/lib/rbac";
import {
  IconLogOut,
  IconProjects,
  IconReview,
  IconSettings,
  IconShield,
} from "./icons";

export function formatRole(role: string | null): string {
  if (!role) return "Visitor";
  return role
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function roleBadgeTone(
  role: string | null,
): "brand" | "info" | "warning" | "success" | "danger" | "neutral" {
  switch (role) {
    case "owner":
    case "admin":
      return "brand";
    case "commercial_manager":
      return "info";
    case "project_manager":
      return "brand";
    case "site_engineer":
      return "warning";
    case "auditor":
      return "success";
    default:
      return "neutral";
  }
}

export function AppHeader() {
  const pathname = usePathname();
  const { session, signOut, status } = useAuth();
  const role = useRole();

  if (status !== "authenticated" || !session) {
    return null;
  }

  // Navigation items with role-aware visibility
  const navItems = [
    {
      label: "Projects",
      href: "/projects",
      icon: IconProjects,
      visible: true,
      active: pathname.startsWith("/projects"),
    },
    {
      label: "Review Queue",
      href: "/review-queue",
      icon: IconReview,
      // Visible to users who have review/decision/write actions
      visible: role
        ? hasAnyPermission(role, [
            "approvals.decide",
            "risks.accept",
            "change_orders.submit",
            "change_orders.write",
            "risks.write",
            "documents.write",
            "project.read",
          ] as readonly Permission[])
        : true,
      active: pathname.startsWith("/review-queue"),
    },
    {
      label: "Settings",
      href: "/settings",
      icon: IconSettings,
      visible: true,
      active: pathname.startsWith("/settings"),
    },
  ];

  return (
    <header className="sticky top-0 z-30 border-b border-border bg-surface/95 backdrop-blur-sm">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        {/* Brand & Main Nav */}
        <div className="flex items-center gap-8">
          <Link href="/projects" className="flex items-center gap-2.5 group">
            <div className="flex size-9 items-center justify-center rounded-lg bg-brand text-white shadow-sm transition-transform group-hover:scale-105">
              <IconShield className="size-5" />
            </div>
            <div className="flex flex-col">
              <span className="text-base font-bold tracking-tight text-ink">ChangeGuard</span>
              <span className="text-[10px] uppercase font-semibold tracking-wider text-ink-faint">
                Commercial Audit
              </span>
            </div>
          </Link>

          <nav className="hidden md:flex items-center gap-1">
            {navItems
              .filter((item) => item.visible)
              .map((item) => {
                const Icon = item.icon;
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                      item.active
                        ? "bg-brand-soft text-brand-strong font-semibold"
                        : "text-ink-muted hover:bg-subtle hover:text-ink"
                    }`}
                  >
                    <Icon className="size-4" />
                    <span>{item.label}</span>
                  </Link>
                );
              })}
          </nav>
        </div>

        {/* User Info & Actions */}
        <div className="flex items-center gap-3">
          <div className="hidden sm:flex flex-col items-end">
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-ink max-w-[180px] truncate">
                {session.userId}
              </span>
              <Badge tone={roleBadgeTone(role)}>{formatRole(role)}</Badge>
            </div>
            {session.tenantId ? (
              <span className="text-[11px] text-ink-muted">
                Workspace: <span className="font-mono text-ink-faint">{session.tenantId.slice(0, 8)}</span>
              </span>
            ) : null}
          </div>

          <Button
            variant="ghost"
            size="sm"
            onClick={() => signOut()}
            aria-label="Sign out"
            className="text-ink-muted hover:text-danger"
          >
            <IconLogOut className="size-4" />
            <span className="hidden sm:inline">Sign Out</span>
          </Button>
        </div>
      </div>
    </header>
  );
}

