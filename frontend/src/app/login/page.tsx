"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card, CardBody, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/form";
import { LoadingSkeleton } from "@/components/ui/states";
import { IconShield } from "@/components/icons";
import { useAuth } from "@/lib/auth";
import { loginSchema } from "@/lib/contracts";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirectTarget = searchParams.get("redirect") || "/projects";
  const { signIn, signInDemo, status } = useAuth();

  const [tenantSlug, setTenantSlug] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (status === "authenticated") {
      router.replace(redirectTarget);
    }
  }, [status, router, redirectTarget]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setServerError(null);
    setFieldErrors({});

    const result = loginSchema.safeParse({
      tenant_slug: tenantSlug.trim(),
      email: email.trim(),
      password,
    });

    if (!result.success) {
      const errors: Record<string, string> = {};
      for (const issue of result.error.issues) {
        const key = issue.path[0];
        if (typeof key === "string" && !errors[key]) {
          errors[key] = issue.message;
        }
      }
      setFieldErrors(errors);
      return;
    }

    setIsSubmitting(true);
    try {
      const authResult = await signIn(result.data);
      if (!authResult.ok) {
        setServerError(authResult.message ?? "Authentication failed. Check your credentials.");
      } else {
        router.replace(redirectTarget);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Account Credentials</CardTitle>
      </CardHeader>
      <CardBody>
        <form id="login-form" onSubmit={handleSubmit} className="flex flex-col gap-4">
          {serverError ? (
            <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft p-3 text-xs font-medium text-danger">
              {serverError}
            </div>
          ) : null}

          <Field
            id="tenant_slug"
            label="Workspace Slug"
            hint="e.g. acme-construction"
            error={fieldErrors["tenant_slug"]}
            required
          >
            <Input
              id="tenant_slug"
              value={tenantSlug}
              onChange={(e) => setTenantSlug(e.target.value.toLowerCase())}
              placeholder="acme-construction"
              invalid={!!fieldErrors["tenant_slug"]}
              autoComplete="organization"
              required
            />
          </Field>

          <Field
            id="email"
            label="Email Address"
            error={fieldErrors["email"]}
            required
          >
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="pm@company.com"
              invalid={!!fieldErrors["email"]}
              autoComplete="email"
              required
            />
          </Field>

          <Field
            id="password"
            label="Password"
            error={fieldErrors["password"]}
            required
          >
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••"
              invalid={!!fieldErrors["password"]}
              autoComplete="current-password"
              required
            />
          </Field>
        </form>
      </CardBody>
      <CardFooter className="flex flex-col gap-3">
        <Button
          type="submit"
          form="login-form"
          fullWidth
          loading={isSubmitting}
        >
          Sign In
        </Button>

        <div className="pt-3 border-t border-border flex flex-col gap-2 w-full">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-muted text-center">
            Instant Demo Sign-In
          </span>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => signInDemo("commercial_manager")}
              className="flex items-center justify-center gap-1.5 rounded-lg border border-border bg-subtle/80 px-2.5 py-2 text-xs font-semibold text-ink hover:border-brand hover:bg-surface transition cursor-pointer"
            >
              <span>Commercial Manager</span>
            </button>
            <button
              type="button"
              onClick={() => signInDemo("project_manager")}
              className="flex items-center justify-center gap-1.5 rounded-lg border border-border bg-subtle/80 px-2.5 py-2 text-xs font-semibold text-ink hover:border-brand hover:bg-surface transition cursor-pointer"
            >
              <span>Project Manager</span>
            </button>
            <button
              type="button"
              onClick={() => signInDemo("site_engineer")}
              className="flex items-center justify-center gap-1.5 rounded-lg border border-border bg-subtle/80 px-2.5 py-2 text-xs font-semibold text-ink hover:border-brand hover:bg-surface transition cursor-pointer"
            >
              <span>Site Engineer</span>
            </button>
            <button
              type="button"
              onClick={() => signInDemo("auditor")}
              className="flex items-center justify-center gap-1.5 rounded-lg border border-border bg-subtle/80 px-2.5 py-2 text-xs font-semibold text-ink hover:border-brand hover:bg-surface transition cursor-pointer"
            >
              <span>Auditor</span>
            </button>
          </div>
        </div>

        <p className="text-center text-xs text-ink-muted">
          Don&apos;t have an organization workspace?{" "}
          <Link href="/register" className="font-medium text-brand hover:underline">
            Register here
          </Link>
        </p>
      </CardFooter>
    </Card>
  );
}

export default function LoginPage() {
  return (
    <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 flex size-12 items-center justify-center rounded-xl bg-brand text-white shadow-card">
            <IconShield className="size-6" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-ink">Sign in to ChangeGuard</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Commercial auditing & change order governance platform
          </p>
        </div>

        <Suspense fallback={<LoadingSkeleton rows={3} variant="cards" />}>
          <LoginForm />
        </Suspense>
      </div>
    </div>
  );
}
