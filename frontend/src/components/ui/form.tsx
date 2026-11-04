"use client";

import { forwardRef, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/**
 * `Field` wraps a control with its label, hint and error. The error is wired to
 * the control through `aria-describedby` by the caller, so a screen reader
 * announces the problem with the input that caused it.
 */
export interface FieldProps {
  readonly id: string;
  readonly label: string;
  readonly hint?: string;
  readonly error?: string;
  readonly required?: boolean;
  readonly children: ReactNode;
  readonly className?: string;
}

export function Field({ id, label, hint, error, required, children, className }: FieldProps) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
        {required ? <span className="ml-0.5 text-danger" aria-hidden> *</span> : null}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-xs text-danger">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-xs text-ink-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

/** Ids the control should point at, given what `Field` is rendering. */
export function describedBy(id: string, error?: string, hint?: string): string | undefined {
  if (error) return `${id}-error`;
  if (hint) return `${id}-hint`;
  return undefined;
}

const control =
  "w-full rounded-lg border bg-surface px-3 text-sm text-ink shadow-card " +
  "placeholder:text-ink-faint transition-colors " +
  "focus:outline-none focus:ring-2 focus:ring-brand/30 focus:border-brand " +
  "disabled:cursor-not-allowed disabled:bg-subtle disabled:text-ink-muted";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { className, invalid = false, ...props },
  ref,
) {
  return (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(control, "h-10", invalid ? "border-danger" : "border-border", className)}
      {...props}
    />
  );
});

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  invalid?: boolean;
}

export function Select({ className, invalid = false, children, ...props }: SelectProps) {
  return (
    <select
      aria-invalid={invalid || undefined}
      className={cn(control, "h-10 cursor-pointer pr-8", invalid ? "border-danger" : "border-border", className)}
      {...props}
    >
      {children}
    </select>
  );
}
