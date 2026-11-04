"use client";

import { useState } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card, CardBody, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/form";
import { IconCheck, IconShield } from "@/components/icons";
import { authApi } from "@/lib/api/resources";
import { errorMessage } from "@/lib/api/errors";
import { registerSchema } from "@/lib/contracts";

export default function RegisterPage() {
  const [tenantName, setTenantName] = useState("");
  const [tenantSlug, setTenantSlug] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [registeredMessage, setRegisteredMessage] = useState<string | null>(null);

  const handleTenantNameChange = (val: string) => {
    setTenantName(val);
    // Auto-suggest slug if user hasn't typed custom slug yet
    const slug = val
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
    setTenantSlug(slug);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setServerError(null);
    setFieldErrors({});

    const result = registerSchema.safeParse({
      tenant_name: tenantName.trim(),
      tenant_slug: tenantSlug.trim(),
      full_name: fullName.trim(),
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
      const res = await authApi.register(result.data);
      setRegisteredMessage(res.message || "Registration received. You can now sign in.");
    } catch (err) {
      setServerError(errorMessage(err, "Registration failed. Try again with a different slug or email."));
    } finally {
      setIsSubmitting(false);
    }
  };

  if (registeredMessage) {
    return (
      <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center p-4">
        <div className="w-full max-w-md">
          <Card>
            <CardBody className="py-8 text-center flex flex-col items-center gap-4">
              <div className="flex size-12 items-center justify-center rounded-full bg-success-soft text-success">
                <IconCheck className="size-6" />
              </div>
              <h2 className="text-xl font-bold text-ink">Registration Received</h2>
              <p className="text-sm text-ink-muted">{registeredMessage}</p>
              <div className="mt-4 w-full">
                <Link href="/login" className="w-full">
                  <Button fullWidth>Proceed to Sign In</Button>
                </Link>
              </div>
            </CardBody>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 flex size-12 items-center justify-center rounded-xl bg-brand text-white shadow-card">
            <IconShield className="size-6" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-ink">Create Workspace</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Register your organization on ChangeGuard
          </p>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Organization & Admin Details</CardTitle>
          </CardHeader>
          <CardBody>
            <form id="register-form" onSubmit={handleSubmit} className="flex flex-col gap-4">
              {serverError ? (
                <div role="alert" className="rounded-lg border border-danger/30 bg-danger-soft p-3 text-xs font-medium text-danger">
                  {serverError}
                </div>
              ) : null}

              <Field
                id="tenant_name"
                label="Organization / Company Name"
                error={fieldErrors["tenant_name"]}
                required
              >
                <Input
                  id="tenant_name"
                  value={tenantName}
                  onChange={(e) => handleTenantNameChange(e.target.value)}
                  placeholder="Apex Construction Ltd"
                  invalid={!!fieldErrors["tenant_name"]}
                  required
                />
              </Field>

              <Field
                id="tenant_slug"
                label="Workspace URL Slug"
                hint="Used to identify your organization in URLs"
                error={fieldErrors["tenant_slug"]}
                required
              >
                <Input
                  id="tenant_slug"
                  value={tenantSlug}
                  onChange={(e) => setTenantSlug(e.target.value.toLowerCase())}
                  placeholder="apex-construction"
                  invalid={!!fieldErrors["tenant_slug"]}
                  required
                />
              </Field>

              <Field
                id="full_name"
                label="Your Full Name"
                error={fieldErrors["full_name"]}
                required
              >
                <Input
                  id="full_name"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="Jane Doe"
                  invalid={!!fieldErrors["full_name"]}
                  autoComplete="name"
                  required
                />
              </Field>

              <Field
                id="email"
                label="Work Email"
                error={fieldErrors["email"]}
                required
              >
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="jane@apexconstruction.com"
                  invalid={!!fieldErrors["email"]}
                  autoComplete="email"
                  required
                />
              </Field>

              <Field
                id="password"
                label="Password"
                hint="Minimum 12 characters"
                error={fieldErrors["password"]}
                required
              >
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="At least 12 characters"
                  invalid={!!fieldErrors["password"]}
                  autoComplete="new-password"
                  required
                />
              </Field>
            </form>
          </CardBody>
          <CardFooter className="flex flex-col gap-3">
            <Button
              type="submit"
              form="register-form"
              fullWidth
              loading={isSubmitting}
            >
              Create Organization Account
            </Button>
            <p className="text-center text-xs text-ink-muted">
              Already have an account?{" "}
              <Link href="/login" className="font-medium text-brand hover:underline">
                Sign in
              </Link>
            </p>
          </CardFooter>
        </Card>
      </div>
    </div>
  );
}

