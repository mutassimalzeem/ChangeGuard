"use client";

import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { Suspense, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ProtectedRoute } from "@/components/protected-route";
import { Button } from "@/components/ui/button";
import { Input, Select } from "@/components/ui/form";
import { useRole } from "@/lib/auth";
import { hasPermission } from "@/lib/rbac";
import { pilotApi, type PilotDocument } from "@/lib/api/pilot";

const types = [
  "contract",
  "boq",
  "drawing",
  "rfi",
  "daily_report",
  "change_order",
  "site_photo",
  "email",
  "quotation",
  "other",
];
const percentage = (n: number | null) =>
  n === null ? "Unknown" : `${(n * 100).toFixed(1)}%`;

function FactEditor({
  value,
  onChange,
  label,
}: {
  value: unknown;
  onChange: (value: unknown) => void;
  label: string;
}) {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    const record = value as Record<string, unknown>;
    if ("missing" in record && "value" in record) {
      const emptyValue = [
        "contract_value",
        "amount",
        "stated_total",
        "unit_rate",
      ].includes(label)
        ? { amount: "", currency: "USD" }
        : label === "quantity"
          ? { amount: "", unit: "each" }
          : "";
      return (
        <fieldset className="grid gap-2 rounded border border-border p-3">
          <legend className="px-1 font-medium">
            {label.replaceAll("_", " ")}
          </legend>
          <label className="flex gap-2">
            <input
              type="checkbox"
              checked={record.missing === true}
              onChange={(e) =>
                onChange(
                  e.target.checked
                    ? {
                        ...record,
                        missing: true,
                        value: null,
                        confidence: 0,
                        source_page: null,
                        source_text_snippet: null,
                      }
                    : {
                        ...record,
                        missing: false,
                        value: emptyValue,
                        source_text_snippet: "",
                      },
                )
              }
            />
            Evidence missing
          </label>
          {!record.missing && (
            <>
              <FactEditor
                label="Value"
                value={record.value}
                onChange={(next) => onChange({ ...record, value: next })}
              />
              <label>
                Source page
                <Input
                  type="number"
                  min={1}
                  value={
                    typeof record.source_page === "number"
                      ? record.source_page
                      : ""
                  }
                  onChange={(e) =>
                    onChange({
                      ...record,
                      source_page: e.target.value
                        ? Number(e.target.value)
                        : null,
                    })
                  }
                />
              </label>
              <label>
                Source quotation
                <textarea
                  className="block w-full rounded border border-border bg-surface p-2"
                  value={String(record.source_text_snippet ?? "")}
                  maxLength={2000}
                  onChange={(e) =>
                    onChange({ ...record, source_text_snippet: e.target.value })
                  }
                />
              </label>
              <p className="text-xs text-ink-muted">
                Original confidence:{" "}
                {percentage(
                  typeof record.confidence === "number"
                    ? record.confidence
                    : null,
                )}
              </p>
            </>
          )}
        </fieldset>
      );
    }
    return (
      <div className="grid gap-3">
        {Object.entries(record).map(([key, entry]) => (
          <FactEditor
            key={key}
            label={key}
            value={entry}
            onChange={(next) => onChange({ ...record, [key]: next })}
          />
        ))}
      </div>
    );
  }
  if (Array.isArray(value))
    return (
      <div className="grid gap-3">
        {value.map((entry, index) => (
          <FactEditor
            key={index}
            label={`${label} ${index + 1}`}
            value={entry}
            onChange={(next) =>
              onChange(value.map((item, i) => (i === index ? next : item)))
            }
          />
        ))}
      </div>
    );
  return (
    <label>
      {label.replaceAll("_", " ")}
      <Input
        value={value === null ? "" : String(value)}
        onChange={(e) =>
          onChange(
            typeof value === "number" ? Number(e.target.value) : e.target.value,
          )
        }
      />
    </label>
  );
}

function ReviewDocument({
  doc,
  saved,
}: {
  doc: PilotDocument;
  saved: () => void;
}) {
  const [type, setType] = useState(doc.document_type ?? "other");
  const [fields, setFields] = useState<unknown>(doc.extraction?.fields ?? {});
  const [reason, setReason] = useState("");
  const mutation = useMutation({
    mutationFn: async () => {
      const original = JSON.stringify(doc.extraction?.fields ?? {});
      await pilotApi.review(
        doc,
        type,
        JSON.stringify(fields) !== original ? fields : undefined,
        reason,
      );
    },
    onSuccess: saved,
  });
  return (
    <details className="mt-3">
      <summary className="cursor-pointer text-brand">
        Review type and extracted facts
      </summary>
      <form
        className="mt-3 grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate();
        }}
      >
        <label>
          Correct document type
          <Select value={type} onChange={(e) => setType(e.target.value)}>
            {types.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </Select>
        </label>
        <p className="text-sm text-ink-muted">
          Compare facts with the original. Include the source page and quotation
          for every corrected fact. Corrections are saved as human review;
          downstream financial records need separate review.
        </p>
        {doc.extraction && (
          <FactEditor
            label="Extracted facts"
            value={fields}
            onChange={setFields}
          />
        )}
        <label>
          Reason for review
          <Input
            required
            maxLength={2000}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
        {mutation.isError && <p role="alert">{mutation.error.message}</p>}
        <Button loading={mutation.isPending} type="submit">
          Save review
        </Button>
      </form>
    </details>
  );
}

function PilotFlow() {
  const router = useRouter();
  const projectId = useSearchParams().get("project");
  const role = useRole();
  const write = role ? hasPermission(role, "documents.write") : false;
  const finance = role ? hasPermission(role, "financial.read") : false;
  const create = role ? hasPermission(role, "project.create") : false;
  const cache = useQueryClient();
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [file, setFile] = useState<File | null>(null);
  const refresh = () => {
    void cache.invalidateQueries({ queryKey: ["pilot", projectId] });
  };
  const pilots = useQuery({
    queryKey: ["pilot-list"],
    queryFn: pilotApi.list,
    enabled: !projectId,
  });
  const docs = useQuery({
    queryKey: ["pilot", projectId, "documents"],
    queryFn: () => pilotApi.documents(projectId!),
    enabled: !!projectId,
    refetchInterval: 5000,
  });
  const checklist = useQuery({
    queryKey: ["pilot", projectId, "checklist"],
    queryFn: () => pilotApi.checklist(projectId!),
    enabled: !!projectId,
  });
  const report = useQuery({
    queryKey: ["pilot", projectId, "report"],
    queryFn: () => pilotApi.report(projectId!),
    enabled: !!projectId && finance,
    refetchInterval: 10000,
  });
  const creation = useMutation({
    mutationFn: () => pilotApi.create(name, currency),
    onSuccess: (result) => router.push(`/pilot?project=${result.project_id}`),
  });
  const upload = useMutation({
    mutationFn: () => pilotApi.upload(projectId!, file!),
    onSuccess: refresh,
  });
  const check = useMutation({
    mutationFn: (completed: string[]) =>
      pilotApi.saveChecklist(projectId!, completed),
    onSuccess: refresh,
  });
  const pdf = useMutation({ mutationFn: () => pilotApi.pdf(projectId!) });
  return (
    <main className="mx-auto grid max-w-5xl gap-6 px-4 py-8">
      <header>
        <p className="text-sm font-semibold text-brand">
          GET STARTED WITH CHANGEGUARD
        </p>
        <h1 className="text-3xl font-bold">Pilot onboarding</h1>
        <p className="mt-2 text-ink-muted">
          Bring your project evidence together, review the results and prepare
          for your pilot review.
        </p>
      </header>
      {!projectId ? (
        <section className="rounded-xl border border-border bg-surface p-6">
          <h2 className="text-xl font-semibold">1. Create your pilot</h2>
          <p className="my-3">
            Construction template · Contract, BOQ and drawing evidence · No
            sample documents
          </p>
          {create ? (
            <form
              className="grid gap-4"
              onSubmit={(e) => {
                e.preventDefault();
                creation.mutate();
              }}
            >
              <label>
                Project name
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  maxLength={255}
                />
              </label>
              <label>
                Project currency
                <Input
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value.toUpperCase())}
                  required
                  pattern="[A-Z]{3}"
                  maxLength={3}
                />
              </label>
              <Button loading={creation.isPending} type="submit">
                Create from construction template
              </Button>
            </form>
          ) : (
            <p>
              Your project manager can create a pilot. Open the pilot link
              shared by your team.
            </p>
          )}
        </section>
      ) : (
        <>
          <Link
            className="text-brand underline"
            href={`/projects/${projectId}`}
          >
            Open project workspace
          </Link>
          <section className="rounded-xl border border-border bg-surface p-6">
            <h2 className="text-xl font-semibold">Your onboarding checklist</h2>
            {checklist.isPending && <p>Loading checklist…</p>}
            {checklist.data && (
              <ul className="mt-4 grid gap-3">
                {Object.entries(checklist.data.steps).map(([id, label]) => (
                  <li key={id}>
                    <label className="flex gap-3">
                      <input
                        type="checkbox"
                        disabled={!write || check.isPending}
                        checked={checklist.data.completed.includes(id)}
                        onChange={(e) =>
                          check.mutate(
                            e.target.checked
                              ? [...checklist.data.completed, id]
                              : checklist.data.completed.filter(
                                  (step) => step !== id,
                                ),
                          )
                        }
                      />
                      {label}
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className="rounded-xl border border-border bg-surface p-6">
            <h2 className="text-xl font-semibold">2. Upload your evidence</h2>
            <p className="my-3 text-sm text-ink-muted">
              ZIP up to 50 MiB, 100 entries and 200 MiB expanded. PDF, Office
              documents, images and emails. No nested archives. Keep this page
              open until the import finishes; retrying skips duplicates.
            </p>
            {write && (
              <form
                className="flex flex-wrap items-end gap-3"
                onSubmit={(e) => {
                  e.preventDefault();
                  upload.mutate();
                }}
              >
                <label>
                  Document ZIP
                  <input
                    className="block"
                    type="file"
                    accept=".zip"
                    required
                    disabled={upload.isPending}
                    onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  />
                </label>
                <Button
                  type="submit"
                  disabled={!file}
                  loading={upload.isPending}
                >
                  Import documents
                </Button>
              </form>
            )}
            {upload.data && (
              <ul className="mt-3">
                {upload.data.items.map((item, i) => (
                  <li key={i}>
                    {item.file_name}:{" "}
                    {item.status === 201
                      ? "Queued"
                      : item.status === 409
                        ? "Duplicate — skipped"
                        : (item.error ?? "Quarantined")}
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section className="rounded-xl border border-border bg-surface p-6">
            <h2 className="text-xl font-semibold">3. Processing and review</h2>
            <p className="my-3 text-sm text-ink-muted">
              Updates every five seconds. Review each classification, including
              correct predictions, to measure accuracy.
            </p>
            {docs.isPending && <p>Loading documents…</p>}
            {docs.data?.length === 0 && (
              <p>No documents yet. Import your first ZIP above.</p>
            )}
            <ul className="divide-y divide-border">
              {docs.data?.map((doc) => (
                <li className="py-4" key={`${doc.document_id}-${doc.version}`}>
                  <div className="flex flex-wrap justify-between gap-2">
                    <strong>{doc.file_name}</strong>
                    <span>
                      {doc.status.replaceAll("_", " ")} ·{" "}
                      {doc.document_type ?? "Awaiting classification"}{" "}
                      {doc.reviewed ? "· Reviewed" : ""}
                    </span>
                  </div>
                  {doc.error && <p className="text-sm">{doc.error}</p>}
                  {write &&
                    ["linked", "review_required"].includes(doc.status) && (
                      <ReviewDocument doc={doc} saved={refresh} />
                    )}
                </li>
              ))}
            </ul>
          </section>
          <section className="rounded-xl border border-border bg-surface p-6">
            <h2 className="text-xl font-semibold">4. Pilot readiness</h2>
            {!finance && (
              <p>
                A commercial or project manager can view the financial readiness
                report.
              </p>
            )}
            {finance && report.isPending && <p>Preparing report…</p>}
            {report.data && (
              <>
                <h3 className="my-3 font-semibold">
                  {report.data.project_name}
                </h3>
                <dl className="grid gap-4 sm:grid-cols-2">
                  {Object.entries({
                    "Documents processed": `${report.data.documents_processed} / ${report.data.documents_total}`,
                    "Classification accuracy": percentage(
                      report.data.classification_accuracy,
                    ),
                    "Classifications reviewed":
                      report.data.classification_reviewed,
                    "Extraction confidence": percentage(
                      report.data.extraction_confidence,
                    ),
                    "Open risks detected": report.data.risks_detected,
                    "Missing evidence":
                      report.data.missing_evidence.join(", ") || "None",
                    "Overdue approvals": report.data.overdue_approvals,
                    "Pending exposure":
                      Object.entries(report.data.pending_exposure)
                        .map(([c, a]) => `${c} ${a}`)
                        .join(", ") || "No known amounts",
                    "Changes with unknown exposure":
                      report.data.unknown_exposure_count,
                  }).map(([label, value]) => (
                    <div key={label}>
                      <dt className="text-sm text-ink-muted">{label}</dt>
                      <dd className="font-semibold">{value}</dd>
                    </div>
                  ))}
                </dl>
                <p className="my-4 text-sm text-ink-muted">
                  {report.data.notes}
                </p>
                <Button onClick={() => pdf.mutate()} loading={pdf.isPending}>
                  Export readiness PDF
                </Button>
              </>
            )}
          </section>
        </>
      )}
      {!projectId && (
        <section className="rounded-xl border border-border bg-surface p-6">
          <h2 className="text-xl font-semibold">Continue a pilot</h2>
          {pilots.isPending && <p>Loading pilots…</p>}
          {pilots.data?.length === 0 && <p>No pilots yet.</p>}
          <ul className="mt-3 grid gap-3">
            {pilots.data?.map((pilot) => (
              <li key={pilot.project_id}>
                <Link
                  className="text-brand underline"
                  href={`/pilot?project=${pilot.project_id}`}
                >
                  {pilot.name}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}
      {[creation, upload, check, pdf].map(
        (m, i) =>
          m.isError && (
            <p key={i} role="alert" className="text-danger">
              {m.error.message}
            </p>
          ),
      )}
      {[docs, checklist, report, pilots].map(
        (q, i) =>
          q.isError && (
            <div key={i} role="alert">
              <p>{q.error.message}</p>
              <Button variant="secondary" onClick={() => q.refetch()}>
                Retry
              </Button>
            </div>
          ),
      )}
    </main>
  );
}

export default function PilotPage() {
  return (
    <ProtectedRoute>
      <Suspense fallback={<p>Loading pilot…</p>}>
        <PilotFlow />
      </Suspense>
    </ProtectedRoute>
  );
}
