"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Card, CardBody, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/form";
import { LoadingSkeleton } from "@/components/ui/states";
import { IconCheck, IconShield } from "@/components/icons";
import { authApi } from "@/lib/api/resources";
import { errorMessage } from "@/lib/api/errors";

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [token, setToken] = useState<string>("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  useEffect(() => {
    // 1. Check URL hash first (standard secure pattern: #token=...)
    if (typeof window !== "undefined" && window.location.hash) {
      const hashParams = new URLSearchParams(window.location.hash.substring(1));
      const hashToken = hashParams.get("token");
      if (hashToken) {
        setToken(hashToken);
        return;
      }
    }
    // 2. Fall back to searchParams (?token=...)
    const queryToken = searchParams.get("token");
    if (queryToken) {
      setToken(queryToken);
    }
  }, [searchParams]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setServerError(null);
    setFieldErrors({});

    const errors: Record<string, string> = {};
    if (!token) {
      setServerError("Reset token is missing or invalid. Please check your reset link.");
      return;
    }

    if (password.length < 12) {
      errors["password"] = "Password must be at least 12 characters long.";
    }

    if (password !== confirmPassword) {
      errors["confirmPassword"] = "Passwords do not match.";
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setIsSubmitting(true);
    try {
      await authApi.confirmPasswordReset({ token, password });
      setIsSuccess(true);
    } catch (err) {
      setServerError(errorMessage(err) || "Failed to reset password. The link may have expired.");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isSuccess) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Password Reset Complete</CardTitle>
        </CardHeader>
        <CardBody className="flex flex-col items-center gap-4 text-center">
          <div className="flex size-12 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-600">
            <IconCheck className="size-6" />
          </div>
          <p className="text-sm text-ink-muted">
            Your password has been successfully updated. You can now sign in with your new credentials.
          </p>
        </CardBody>
        <CardFooter>
          <Button fullWidth onClick={() => router.push("/login")}>
            Sign In
          </Button>
        </CardFooter>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Set New Password</CardTitle>
      </CardHeader>
      <CardBody>
        <form id="reset-password-form" onSubmit={handleSubmit} className="flex flex-col gap-4">
          {serverError ? (
            <div
              role="alert"
              className="rounded-lg border border-danger/30 bg-danger-soft p-3 text-xs font-medium text-danger"
            >
              {serverError}
            </div>
          ) : null}

          {!token ? (
            <div
              role="alert"
              className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs font-medium text-amber-700 dark:text-amber-400"
            >
              No reset token detected in URL. Please make sure you clicked the full link from your email.
            </div>
          ) : null}

          <Field
            id="password"
            label="New Password"
            hint="Minimum 12 characters"
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
              autoComplete="new-password"
              required
            />
          </Field>

          <Field
            id="confirmPassword"
            label="Confirm New Password"
            error={fieldErrors["confirmPassword"]}
            required
          >
            <Input
              id="confirmPassword"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="••••••••••••"
              invalid={!!fieldErrors["confirmPassword"]}
              autoComplete="new-password"
              required
            />
          </Field>
        </form>
      </CardBody>
      <CardFooter className="flex flex-col gap-3">
        <Button
          type="submit"
          form="reset-password-form"
          fullWidth
          loading={isSubmitting}
          disabled={!token}
        >
          Reset Password
        </Button>
        <p className="text-center text-xs text-ink-muted">
          Remember your password?{" "}
          <Link href="/login" className="font-medium text-brand hover:underline">
            Back to Sign In
          </Link>
        </p>
      </CardFooter>
    </Card>
  );
}

export default function ResetPasswordPage() {
  return (
    <div className="flex min-h-[calc(100vh-4rem)] items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-3 flex size-12 items-center justify-center rounded-xl bg-brand text-white shadow-card">
            <IconShield className="size-6" />
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-ink">Reset Your Password</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Enter a new password for your ChangeGuard account
          </p>
        </div>

        <Suspense fallback={<LoadingSkeleton rows={3} variant="cards" />}>
          <ResetPasswordForm />
        </Suspense>
      </div>
    </div>
  );
}

