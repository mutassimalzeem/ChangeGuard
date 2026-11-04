"use client";

import { useEffect, useRef, type ReactNode } from "react";

import { Button } from "./button";

/**
 * A modal built on `<dialog>`, which the browser supplies focus trapping and
 * focus return to. The polish it lacks is the top layer on Escape: listening for
 * `cancel` keeps React the only owner of `open`, so a parent can never think the
 * dialog is showing when it is not.
 */
export interface ModalProps {
  readonly open: boolean;
  readonly title: string;
  readonly onClose: () => void;
  readonly children: ReactNode;
  /** Footer controls, typically a cancel and a confirm button. */
  readonly actions?: ReactNode;
}

export function Modal({ open, title, onClose, children, actions }: ModalProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog === null) return;
    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog === null) return;
    const handleCancel = (event: Event) => {
      event.preventDefault();
      onClose();
    };
    dialog.addEventListener("cancel", handleCancel);
    return () => dialog.removeEventListener("cancel", handleCancel);
  }, [onClose]);

  return (
    <dialog
      ref={dialogRef}
      aria-labelledby="modal-title"
      className="w-full max-w-lg rounded-[--radius-card] border border-border bg-surface p-0 shadow-overlay backdrop:bg-ink/40"
    >
      {open ? (
        <div className="flex flex-col">
          <header className="flex items-start justify-between gap-3 border-b border-border px-5 py-4">
            <h2 id="modal-title" className="text-base font-semibold text-ink">
              {title}
            </h2>
            <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close dialog">
              Cancel
            </Button>
          </header>
          <div className="px-5 py-4 text-sm text-ink">{children}</div>
          {actions ? (
            <footer className="flex items-center justify-end gap-2 border-t border-border px-5 py-3">{actions}</footer>
          ) : null}
        </div>
      ) : null}
    </dialog>
  );
}
