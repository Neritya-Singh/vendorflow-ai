import * as Dialog from "@radix-ui/react-dialog";
import {
  ArrowLeft, CheckCircle2, ChevronDown, Eye, EyeOff, FileText, Gavel, MessageSquareWarning, RefreshCw, ShieldCheck, X, XCircle,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { StageList } from "../../components/StageList";
import { Alert, Button, Card, CardHeader, CheckIcon, KeyValue, Pill, RiskTag, Spinner, StatusBadge, Textarea, cx } from "../../components/ui";
import { ApiError, api } from "../../lib/api";
import { formatDateTime, formatDuration } from "../../lib/format";
import type { AdminCase as Case, ComparisonRow, RunDetail } from "../../lib/types";
import { useAdmin } from "./AdminLayout";

type Action = "REQUEST_CORRECTION" | "APPROVE" | "REJECT";
const ACTIONS: { id: Action; label: string; verb: string; icon: typeof Gavel; tone: string; help: string }[] = [
  { id: "REQUEST_CORRECTION", label: "Request correction", verb: "Send correction request", icon: MessageSquareWarning, tone: "amber", help: "Vendor gets a message and the case moves to Waiting on vendor." },
  { id: "APPROVE", label: "Approve", verb: "Approve application", icon: CheckCircle2, tone: "teal", help: "Final. Records a manual approval." },
  { id: "REJECT", label: "Reject", verb: "Reject application", icon: XCircle, tone: "red", help: "Final. The vendor sees your reason." },
];

function Issues({ c }: { c: Case }) {
  const all = [...c.issues.failed, ...c.issues.unverified];
  return (
    <Card>
      <CardHeader
        title="Checks needing attention"
        description={all.length ? `${c.issues.failed.length} need correction · ${c.issues.unverified.length} not verified` : undefined}
      />
      {all.length === 0 ? (
        <p className="flex items-center gap-2 px-5 py-4 text-sm text-teal-800"><CheckCircle2 className="size-4" aria-hidden /> All automated checks passed.</p>
      ) : (
        <ul className="divide-y divide-slate-100">
          {all.map((issue) => (
            <li key={issue.rule_id} className="flex gap-3 px-5 py-3">
              <CheckIcon state={issue.state} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-medium text-slate-900">{issue.label}</p>
                  <Pill tone={issue.state === "FAIL" ? "red" : "amber"}>{issue.state === "FAIL" ? "Correction needed" : "Not verified"}</Pill>
                  <span className="font-mono text-[11px] text-slate-400">{issue.rule_id}</span>
                </div>
                <p className="mt-0.5 text-[13px] text-slate-600">{issue.note}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function Comparison({ c }: { c: Case }) {
  const { onUnauthorized } = useAdmin();
  const [revealed, setRevealed] = useState<ComparisonRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  const toggle = async () => {
    if (revealed) return setRevealed(null);
    setBusy(true);
    try {
      setRevealed((await api.reveal(c.application_id)).rows);
    } catch (e) {
      onUnauthorized(e);
    } finally {
      setBusy(false);
    }
  };
  if (!c.comparison.length) return null;
  return (
    <Card>
      <CardHeader
        title="Submitted vs. PDF evidence"
        description="From the latest saved run. Sensitive identifiers are masked by default."
        action={
          <Button size="sm" variant="secondary" icon={revealed ? EyeOff : Eye} loading={busy} onClick={toggle}>
            {revealed ? "Mask values" : "Show full values"}
          </Button>
        }
      />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[560px] text-left text-sm">
          <thead className="bg-slate-50 text-xs font-medium text-slate-500">
            <tr>
              <th scope="col" className="px-5 py-2">Field</th>
              <th scope="col" className="px-3 py-2">Submitted by vendor</th>
              <th scope="col" className="px-3 py-2">Found in PDF</th>
              <th scope="col" className="px-5 py-2 text-right">Comparison</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {c.comparison.map((row, i) => {
              const shown = revealed?.[i] ?? row;
              return (
                <tr key={row.Field} className={cx(row.Kind === "flag" && "bg-red-50/40", row.Kind === "missing" && "bg-amber-50/40")}>
                  <th scope="row" className="px-5 py-2.5 font-medium text-slate-700">{row.Field.replace(" (masked)", "")}</th>
                  <td className="px-3 py-2.5 font-mono text-[13px] text-slate-900">{shown.Submitted}</td>
                  <td className="px-3 py-2.5 font-mono text-[13px] text-slate-900">{shown["From PDF"]}</td>
                  <td className="px-5 py-2.5 text-right">
                    <Pill tone={row.Kind === "ok" ? "teal" : row.Kind === "flag" ? "red" : "amber"}>{row.Assessment}</Pill>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="border-t border-slate-100 px-5 py-2.5 text-xs text-slate-500">
        “Consistent” means the two sources agree. It does not verify a real GST registration or bank-account ownership.
      </p>
    </Card>
  );
}

function RunCard({ run, appId, open, onToggle, latest }: { run: RunDetail; appId: string; open: boolean; onToggle: () => void; latest: boolean }) {
  return (
    <li className="border-b border-slate-100 last:border-0">
      <button type="button" onClick={onToggle} aria-expanded={open} className="flex w-full items-center gap-3 px-5 py-3 text-left hover:bg-slate-50">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium text-slate-900">{run.trigger === "submission" ? "Initial submission" : "Resubmission"}</p>
            <StatusBadge status={run.status} />
            {latest ? <Pill tone="navy">Latest</Pill> : null}
            {run.extraction_error ? <Pill tone="amber">Extraction failed</Pill> : null}
          </div>
          <p className="mt-0.5 text-xs text-slate-500">
            <span className="font-mono">{run.id}</span> · {formatDateTime(run.created_at)} · {formatDuration(run.elapsed_ms)}
          </p>
        </div>
        <ChevronDown className={cx("size-4 text-slate-400 transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      {open ? (
        <div className="grid gap-5 px-5 pb-5 md:grid-cols-[1.2fr_1fr]">
          <div>
            <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Saved stage events</p>
            <StageList rows={run.stages} />
          </div>
          <div className="grid content-start gap-4">
            <div>
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Exact PDFs evaluated</p>
              {run.documents.length ? (
                <ul className="grid gap-2">
                  {run.documents.map((d) => (
                    <li key={d.doc_type} className="flex items-center gap-3 rounded-lg border border-slate-200 px-3 py-2">
                      <FileText className="size-4 text-slate-400" aria-hidden />
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium text-slate-900">{d.doc_type === "GST" ? "GST certificate" : "Bank proof"} · v{d.version}</p>
                        <p className="truncate font-mono text-[11px] text-slate-500">sha256 {d.sha256_prefix}…</p>
                      </div>
                      <a
                        href={api.documentUrl(appId, run.id, d.doc_type)}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-[13px] font-medium text-navy-700 hover:underline"
                      >
                        Open
                      </a>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-[13px] text-slate-500">No PDFs were attached to this run.</p>
              )}
            </div>
            <div>
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Automated reasons</p>
              <ul className="list-disc space-y-1 pl-4 text-[13px] text-slate-700">
                {run.reasons.map((r) => <li key={r}>{r}</li>)}
              </ul>
            </div>
          </div>
        </div>
      ) : null}
    </li>
  );
}

function DecisionPanel({ c, onDone }: { c: Case; onDone: (next: Case, message: string) => void }) {
  const { onUnauthorized } = useAdmin();
  const [action, setAction] = useState<Action | null>(null);
  const [reason, setReason] = useState("");
  const [open, setOpen] = useState(false);
  const [confirmId, setConfirmId] = useState(false);
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; stale: boolean } | null>(null);
  const chosen = ACTIONS.find((a) => a.id === action);
  const reasonOk = reason.trim().length >= 3;

  const save = async () => {
    if (!action || !c.latest_run_id) return;
    setBusy(true);
    setError(null);
    try {
      const next = await api.review(c.application_id, {
        action,
        reason: reason.trim(),
        expected_revision: c.revision,
        expected_latest_run_id: c.latest_run_id,
      });
      setOpen(false);
      onDone(next, `${chosen?.label ?? "Decision"} recorded for ${c.application_id}.`);
    } catch (e) {
      if (onUnauthorized(e)) return;
      setOpen(false);
      setError({ message: e instanceof Error ? e.message : "Decision not saved.", stale: e instanceof ApiError && e.status === 409 });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="border-navy-200">
      <CardHeader title="Record a decision" description="Your reason is saved to the audit trail and shown to the vendor." />
      <div className="grid gap-4 px-5 py-4">
        <fieldset>
          <legend className="sr-only">Decision</legend>
          <div className="grid gap-2">
            {ACTIONS.map((a) => {
              const Icon = a.icon;
              const selected = action === a.id;
              return (
                <label
                  key={a.id}
                  className={cx(
                    "flex cursor-pointer items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors",
                    selected
                      ? a.tone === "teal" ? "border-teal-500 bg-teal-50" : a.tone === "red" ? "border-red-500 bg-red-50" : "border-amber-500 bg-amber-50"
                      : "border-slate-200 hover:border-slate-300",
                  )}
                >
                  <input type="radio" name="decision" className="sr-only" checked={selected} onChange={() => setAction(a.id)} />
                  <Icon className={cx("mt-0.5 size-4 shrink-0", a.tone === "teal" ? "text-teal-700" : a.tone === "red" ? "text-red-700" : "text-amber-600")} aria-hidden />
                  <span>
                    <span className="block text-sm font-medium text-slate-900">{a.label}</span>
                    <span className="block text-xs text-slate-500">{a.help}</span>
                  </span>
                </label>
              );
            })}
          </div>
        </fieldset>
        <div>
          <label htmlFor="review-reason" className="text-[13px] font-medium text-slate-800">
            {action === "REQUEST_CORRECTION" ? "What should the vendor change?" : "Reason for the vendor and audit trail"}
          </label>
          <Textarea
            id="review-reason"
            className="mt-1.5"
            maxLength={1000}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder={action === "REQUEST_CORRECTION" ? "e.g. Upload a bank letter that shows the company's legal name as account holder." : "State the evidence you reviewed."}
          />
          <p className="mt-1 text-right text-xs text-slate-400 tabular">{reason.length}/1000</p>
        </div>
        {error ? (
          <Alert tone="error" title="Decision not saved">
            {error.message}
            {error.stale ? <div className="mt-2"><Button size="sm" variant="secondary" icon={RefreshCw} onClick={() => window.location.reload()}>Reload case</Button></div> : null}
          </Alert>
        ) : null}
        <Dialog.Root
          open={open}
          onOpenChange={(o) => {
            setOpen(o);
            if (o) {
              setConfirmId(false);
              setReviewed(false);
            }
          }}
        >
          <Dialog.Trigger asChild>
            <Button disabled={!action || !reasonOk} variant={action === "REJECT" ? "danger" : action === "APPROVE" ? "success" : "primary"} icon={Gavel}>
              {chosen ? `${chosen.verb}…` : "Choose a decision"}
            </Button>
          </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-40 bg-slate-900/40" />
            <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100vw-2rem)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl bg-white shadow-xl focus:outline-none">
              <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4">
                <div>
                  <Dialog.Title className="text-[15px] font-semibold text-slate-900">{chosen?.verb}?</Dialog.Title>
                  <Dialog.Description className="mt-0.5 text-[13px] text-slate-500">
                    {action === "REQUEST_CORRECTION" ? "The vendor will see your message and can resubmit." : "This is a final decision and makes the application read-only."}
                  </Dialog.Description>
                </div>
                <Dialog.Close className="rounded-md p-1 text-slate-500 hover:bg-slate-100" aria-label="Close"><X className="size-4" aria-hidden /></Dialog.Close>
              </div>
              <div className="grid gap-3 px-5 py-4">
                <dl className="rounded-lg bg-slate-50 px-3 py-1">
                  <KeyValue label="Application" value={c.application_id} mono />
                  <KeyValue label="Business" value={c.business} />
                  <KeyValue label="Reviewed run" value={c.latest_run_id ?? "—"} mono />
                </dl>
                <p className="rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-700">“{reason.trim()}”</p>
                <label className="flex items-start gap-2.5 text-sm text-slate-700">
                  <input type="checkbox" className="mt-0.5 size-4 accent-navy-900" checked={confirmId} onChange={(e) => setConfirmId(e.target.checked)} />
                  This decision applies to <span className="font-mono">{c.application_id}</span>.
                </label>
                {action === "APPROVE" ? (
                  <label className="flex items-start gap-2.5 text-sm text-slate-700">
                    <input type="checkbox" className="mt-0.5 size-4 accent-navy-900" checked={reviewed} onChange={(e) => setReviewed(e.target.checked)} />
                    I reviewed the evidence and understand this is not official GST or bank verification.
                  </label>
                ) : null}
              </div>
              <div className="flex justify-end gap-2 border-t border-slate-200 bg-slate-50 px-5 py-3">
                <Dialog.Close asChild><Button variant="secondary">Cancel</Button></Dialog.Close>
                <Button
                  variant={action === "REJECT" ? "danger" : action === "APPROVE" ? "success" : "primary"}
                  loading={busy}
                  disabled={!confirmId || (action === "APPROVE" && !reviewed)}
                  onClick={save}
                >
                  {chosen?.verb}
                </Button>
              </div>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
        <p className="text-xs text-slate-500">
          Saved against revision {c.revision}. If the vendor resubmits meanwhile, the server rejects this decision as stale.
        </p>
      </div>
    </Card>
  );
}

export function AdminCase() {
  const { id = "" } = useParams();
  const { onUnauthorized } = useAdmin();
  const [c, setC] = useState<Case | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [openRun, setOpenRun] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .adminCase(id)
      .then((data) => {
        setC(data);
        setOpenRun((r) => r ?? data.runs[0]?.id ?? null);
      })
      .catch((e: Error) => {
        if (!onUnauthorized(e)) setError(e.message);
      });
  }, [id, onUnauthorized]);
  useEffect(load, [load]);

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-8">
        <Alert tone="error" title="Case unavailable">{error}</Alert>
        <Link to="/admin" className="mt-4 inline-block text-sm font-medium text-navy-700 hover:underline">← Back to queue</Link>
      </div>
    );
  }
  if (!c) return <div className="p-8"><Spinner label="Loading case…" /></div>;

  const latestRun = c.runs[0];
  return (
    <div className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6">
      <Link to="/admin" className="inline-flex items-center gap-1 text-[13px] font-medium text-slate-600 hover:text-navy-800">
        <ArrowLeft className="size-3.5" aria-hidden /> Review queue
      </Link>
      <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">{c.business || "Unnamed business"}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-[13px] text-slate-500">
            <span className="font-mono text-slate-700">{c.application_id}</span>
            <StatusBadge status={c.status} />
            {c.status === "PENDING" ? <Pill tone={c.owner === "VENDOR" ? "amber" : "navy"}>{c.owner_label}</Pill> : null}
            {c.risk && c.status === "PENDING" ? <RiskTag risk={c.risk} /> : null}
            {c.decision_source === "MANUAL" ? <Pill>Reviewer decision</Pill> : <Pill>Automated decision</Pill>}
            <span>Revision {c.revision}</span>
            <span>· Submitted {formatDateTime(c.created_at)}</span>
          </div>
        </div>
      </div>

      {notice ? <Alert tone="success" className="mt-4">{notice}</Alert> : null}

      <Card className={cx("mt-4 px-5 py-4", c.status === "PENDING" ? "border-amber-200 bg-amber-50/50" : c.status === "APPROVED" ? "border-teal-200 bg-teal-50/50" : "border-red-200 bg-red-50/50")}>
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
          {c.status === "PENDING" ? "Why it's here" : "Decision basis"}
        </p>
        {c.status === "PENDING" ? (
          <>
            <p className="mt-1 text-[15px] font-semibold text-slate-900">{c.primary_issue}</p>
            {c.flags.length > 1 ? (
              <ul className="mt-1.5 space-y-0.5 text-[13px] text-slate-700">
                {c.flags.slice(1).map((f) => <li key={f.rule_id}>Also: {f.reason}</li>)}
              </ul>
            ) : null}
            {c.owner === "VENDOR" && c.vendor_items.length ? (
              <div className="mt-2 text-[13px] text-slate-700">
                <p className="font-medium text-slate-800">The vendor was asked to:</p>
                <ul className="mt-0.5 list-disc pl-5">{c.vendor_items.map((i) => <li key={i.text}>{i.text}</li>)}</ul>
              </div>
            ) : null}
          </>
        ) : (
          <ul className="mt-1.5 space-y-1 text-sm text-slate-800">
            {c.reasons.map((r) => <li key={r}>{r}</li>)}
          </ul>
        )}
        {c.active_correction_request ? <p className="mt-2 text-[13px] font-medium text-navy-800">Correction requested — waiting for the vendor to resubmit.</p> : null}
      </Card>

      <div className="mt-5 grid items-start gap-5 lg:grid-cols-[1fr_380px]">
        <div className="grid min-w-0 gap-5">
          {latestRun ? (
            <>
              <Issues c={c} />
              <Comparison c={c} />
            </>
          ) : (
            <Alert tone="warning" title="No completed check">The vendor's first submission was interrupted. They must resume it before a decision is possible.</Alert>
          )}
          {c.runs.length ? (
            <Card>
              <CardHeader title="Run history" description={`${c.runs.length} saved ${c.runs.length === 1 ? "evaluation" : "evaluations"} with the exact PDF versions used`} />
              <ul>
                {c.runs.map((run, i) => (
                  <RunCard key={run.id} run={run} appId={c.application_id} latest={i === 0} open={openRun === run.id} onToggle={() => setOpenRun((o) => (o === run.id ? null : run.id))} />
                ))}
              </ul>
            </Card>
          ) : null}
          {c.checks.length ? (
            <details className="group rounded-xl border border-slate-200 bg-white shadow-card">
              <summary className="flex cursor-pointer list-none items-center justify-between px-5 py-4 text-[15px] font-semibold text-slate-900">
                All rule results ({c.checks.length})
                <ChevronDown className="size-4 text-slate-400 transition-transform group-open:rotate-180" aria-hidden />
              </summary>
              <div className="overflow-x-auto border-t border-slate-200">
                <table className="w-full min-w-[560px] text-left text-sm">
                  <tbody className="divide-y divide-slate-100">
                    {c.checks.map((ch) => (
                      <tr key={ch.rule_id}>
                        <td className="w-14 px-5 py-2.5 font-mono text-xs text-slate-500">{ch.rule_id}</td>
                        <td className="px-2 py-2.5"><span className="inline-flex items-center gap-2 font-medium text-slate-800"><CheckIcon state={ch.state} />{ch.label}</span></td>
                        <td className="px-5 py-2.5 text-[13px] text-slate-600">{ch.evidence}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          ) : null}
        </div>

        <aside className="grid gap-5 lg:sticky lg:top-20">
          {c.can_review ? (
            <DecisionPanel
              key={`${c.revision}`}
              c={c}
              onDone={(next, message) => {
                setC(next);
                setNotice(message);
                window.scrollTo({ top: 0, behavior: "smooth" });
              }}
            />
          ) : (
            <Card className="px-5 py-4">
              <p className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                <ShieldCheck className="size-4 text-slate-500" aria-hidden />
                {c.status === "PENDING" ? "Waiting for the vendor" : "Final decision recorded"}
              </p>
              <p className="mt-1 text-[13px] text-slate-600">
                {c.status === "PENDING" ? "A decision is possible once a completed check exists." : "This case is read-only."}
              </p>
            </Card>
          )}
          <Card>
            <CardHeader title="Reviewer actions" />
            {c.reviews.length ? (
              <ol className="divide-y divide-slate-100">
                {c.reviews.map((r, i) => (
                  <li key={`${r.created_at}-${i}`} className="px-5 py-3">
                    <div className="flex items-center justify-between gap-2">
                      <Pill tone={r.action === "APPROVE" ? "teal" : r.action === "REJECT" ? "red" : "amber"}>{r.label}</Pill>
                      <span className="text-xs text-slate-500">{formatDateTime(r.created_at)}</span>
                    </div>
                    <p className="mt-1.5 text-[13px] text-slate-700">“{r.reason}”</p>
                    <p className="mt-1 text-xs text-slate-500">{r.actor} · run <span className="font-mono">{r.reviewed_run_id}</span></p>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="px-5 py-4 text-[13px] text-slate-500">No reviewer actions yet.</p>
            )}
          </Card>
          <Card className="px-5 py-2">
            <dl className="divide-y divide-slate-100">
              <KeyValue label="Contact" value={c.contact.name || "Not supplied"} />
              <KeyValue label="Email" value={c.contact.email || "—"} />
              <KeyValue label="State" value={c.contact.state || "Not supplied"} />
              <KeyValue label="Last updated" value={formatDateTime(c.updated_at)} />
            </dl>
          </Card>
        </aside>
      </div>
    </div>
  );
}
