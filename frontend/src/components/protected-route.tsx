"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter, usePathname } from "next/navigation";

import { ErrorState, LoadingSkeleton } from "@/components/ui/states";
import { Button } from "@/components/ui/button";
import { useAuth, useRole } from "@/lib/auth";
import { hasPermission, type Permission, type Role } from "@/lib/rbac";
import { formatRole } from "./app-header";

export interface ProtectedRouteProps {
  children: ReactNode;
  requiredPermission?: Permission;
  requiredRole?: Role;
}

export function ProtectedRoute({
  children,
  requiredPermission,
  requiredRole,
}: ProtectedRouteProps) {
  const router = useRouter();
  const pathname = usePathname();
  const { status } = useAuth();
  const role = useRole();

  useEffect(() => {
    if (status === "anonymous") {
      const returnUrl = encodeURIComponent(pathname);
      router.replace(`/login?redirect=${returnUrl}`);
    }
  }, [status, router, pathname]);

  if (status === "loading") {
    return (
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <LoadingSkeleton rows={5} variant="cards" />
      </div>
    );
  }

  if (status === "anonymous") {
    return null;
  }

  if (requiredRole && role !== requiredRole) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12">
        <ErrorState
          title="Role Restriction"
          message={`This area requires the ${formatRole(requiredRole)} role. You are currently signed in as ${formatRole(role)}.`}
          detail="Contact your organization administrator to adjust your assigned role."
          onRetry={() => router.push("/projects")}
        />
      </div>
    );
  }

  if (requiredPermission && role && !hasPermission(role, requiredPermission)) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12 flex flex-col gap-4">
        <ErrorState
          title="Access Restricted"
          message={`Your role (${formatRole(role)}) does not have permission for '${requiredPermission}'.`}
          detail="If you believe this is in error, verify your project permissions with your commercial manager."
        />
        <div>
          <Button variant="secondary" onClick={() => router.push("/projects")}>
            Return to Projects
          </Button>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

