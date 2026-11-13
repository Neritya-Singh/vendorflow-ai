import * as Dialog from "@radix-ui/react-dialog";
import { ArrowLeft, CheckCircle2, ChevronDown, ChevronLeft, ChevronRight, Eye, EyeOff, FileText, Keyboard, X } from "lucide-react";
import { Fragment, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { DECISIONS, DecisionDialog, type Decision } from "../../components/admin/DecisionDialog";
import { DocumentViewer, type ViewerDoc } from "../../components/admin/DocumentViewer";
import { StageList } from "../../components/StageList";
import { Alert, Button, CheckIcon, OwnerPill, Pill, RiskTag, Spinner, StatusBadge, cx } from "../../components/ui";
import { api } from "../../lib/api";
import { formatAge, formatDateTime, formatDuration } from "../../lib/format";
import type { AdminCase as Case, ComparisonRow, LinkedRecord, RunDetail } from "../../lib/types";
import { useShortcuts } from "../../lib/useShortcuts";
import { useAdmin } from "./AdminLayout";
import { TAB_IDS, type Tab, useOverview } from "./queueState";

const CASE_ID = /\bVF-[0-9A-F]{12}\b/g;

/** Turns case IDs inside staff evidence text into links to those cases. */
function Linkified({ text, tab }: { text: string; tab: Tab }) {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(CASE_ID)) {
    parts.push(text.slice(last, match.index));
    parts.push(
      <Link key={match.index} to={`/admin/cases/${match[0]}?tab=${tab}`} className="font-semibold text-navy-700 underline-offset-2 hover:underline">
        {match[0]}
      </Link>,
    );
    last = (match.index ?? 0) + match[0].length;
  }
  parts.push(text.slice(last));
  return <>{parts}</>;
}

function Panel({ title, action, children, className, id }: { title: ReactNode; action?: ReactNode; children: ReactNode; className?: string; id: string }) {
  return (
    <section aria-labelledby={id} className={cx("flex flex-col gap-2.5 rounded-[20px] border border-line bg-white px-5 py-4", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id={id} className="text-[15px] font-semibold text-ink">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

// ---------------------------------------------------------------- left column

function WhyItsHere({ c, tab }: { c: Case; tab: Tab }) {
  const top = c.flags[0];
  const evidence = top ? c.checks.find((ch) => ch.rule_id === top.rule_id)?.evidence : undefined;
  const vendorSaw = c.messages[0]?.text;
  const tone = c.status === "APPROVED" ? "border-teal-200 bg-teal-50" : c.status === "REJECTED" ? "border-red-200 bg-[#FEF3F2]" : "border-[#FEDF89] bg-[#FFFAEB]";
  return (
    <section aria-labelledby="why-h" className={cx("flex flex-col gap-2 rounded-[20px] border px-5 py-4", tone)}>
      <h2 id="why-h" className="text-[13px] font-semibold uppercase tracking-[0.04em] text-[#93370D]">
        {c.status === "PENDING" ? "Why it's here" : "Decision"}
      </h2>
      {c.status !== "PENDING" ? (
        <ul className="space-y-1 text-[15px] text-ink">{c.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
      ) : (
        <>
          <p className="text-[15px] font-semibold leading-snug text-ink">{c.primary_issue}</p>
          {evidence ? <p className="text-[15px] leading-relaxed text-ink"><Linkified text={evidence} tab={tab} /></p> : null}
          {c.flags.length > 1 ? <p className="text-[13px] text-[#93370D]">Also flagged: {c.flags.slice(1).map((f) => f.reason).join(" · ")}</p> : null}
          {c.owner === "VENDOR" && c.vendor_items.length ? (
            <div className="text-[13px] text-ink">
              <p className="font-medium">The vendor was asked to:</p>
              <ul className="mt-0.5 list-disc pl-5">{c.vendor_items.map((i) => <li key={i.text}>{i.text}</li>)}</ul>
            </div>
          ) : null}
          {vendorSaw ? <p className="text-[13px] text-[#93370D]">The vendor was shown: “{vendorSaw}”</p> : null}
        </>
      )}
    </section>
  );
}

function LinkedRecordPanel({ record, tab }: { record: LinkedRecord; tab: Tab }) {
  return (
    <Panel
      id={`linked-${record.application_id}`}
      title={
        <span className="inline-flex flex-wrap items-center gap-2">
          Linked record
          <Link to={`/admin/cases/${record.application_id}?tab=${tab}`} className="text-[13px] font-semibold text-navy-700 hover:underline">
            Open {record.application_id}
          </Link>
          <StatusBadge status={record.status} />
        </span>
      }
    >
      <p className="-mt-1 text-xs text-muted">{record.match.join(" · ")} — {record.business || "Unnamed business"}</p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] border-collapse text-sm tabular">
          <thead className="text-left text-xs text-muted">
            <tr>
              <th scope="col" className="py-1.5 font-semibold">Field</th>
              <th scope="col" className="px-2 py-1.5 font-semibold">This application</th>
              <th scope="col" className="py-1.5 font-semibold">{record.status_label} {record.application_id}</th>
            </tr>
          </thead>
          <tbody>
            {record.comparison.map((row) => (
              <tr key={row.field} className={cx("border-t border-[#F2F4F7]", !row.same && "bg-[#FEF3F2]")}>
                <th scope="row" className={cx("py-2 text-left", row.same ? "font-medium text-[#344054]" : "pl-2 font-semibold text-[#B42318]")}>{row.field}</th>
                <td className={cx("px-2 py-2", !row.same && "font-semibold")}>{row.this}</td>
                <td className="py-2">
                  {row.other}{" "}
                  {row.same ? <span className="text-teal-700" aria-label="Same">✓</span> : <span className="text-xs font-semibold text-[#B42318]">Differs</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function ComparedValues({ c }: { c: Case }) {
  const { onUnauthorized } = useAdmin();
  const [revealed, setRevealed] = useState<ComparisonRow[] | null>(null);
  const [busy, setBusy] = useState(false);
  if (!c.comparison.length) return null;
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
  return (
    <Panel
      id="cmp-h"
      title="Compared values"
      action={
        <Button size="sm" variant="ghost" icon={revealed ? EyeOff : Eye} loading={busy} onClick={toggle}>
          {revealed ? "Mask" : "Show full values"}
        </Button>
      }
    >
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] border-collapse text-sm tabular">
          <thead className="text-left text-xs text-muted">
            <tr>
              <th scope="col" className="py-1.5 font-semibold">Field</th>
              <th scope="col" className="px-2 py-1.5 font-semibold">Submitted</th>
              <th scope="col" className="py-1.5 font-semibold">In the document</th>
            </tr>
          </thead>
          <tbody>
            {c.comparison.map((row, i) => {
              const shown = revealed?.[i] ?? row;
              const bad = row.Kind === "flag";
              return (
                <tr key={row.Field} className={cx("border-t border-[#F2F4F7]", bad && "bg-[#FEF3F2]", row.Kind === "missing" && "bg-[#FFFAEB]")}>
                  <th scope="row" className={cx("py-2 text-left", bad ? "pl-2 font-semibold text-[#B42318]" : "font-medium text-[#344054]")}>{row.Field.replace(" (masked)", "")}</th>
                  <td className="px-2 py-2">
                    {shown.Submitted}
                    {c.provenance?.[i]?.status === "edited" ? <span className="ml-1.5 rounded-full bg-[#FEF0C7] px-2 py-0.5 text-[11px] font-semibold text-[#93370D]">Changed by vendor</span> : null}
                    {c.provenance?.[i]?.status === "vendor" ? <span className="ml-1.5 rounded-full bg-[#FEF0C7] px-2 py-0.5 text-[11px] font-semibold text-[#93370D]">Entered by vendor, not on document</span> : null}
                  </td>
                  <td className="py-2">
                    {shown["From PDF"]}{" "}
                    {row.Kind === "ok" ? <span className="text-teal-700" aria-label="Consistent">✓</span> : <span className="text-xs font-semibold text-[#B42318]">{row.Assessment}</span>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted">“✓” means the two sources agree. It is not a GST registry or bank-ownership verification.</p>
    </Panel>
  );
}

type HistoryItem =
  | { kind: "run"; at: string | null; run: RunDetail }
  | { kind: "message"; at: string | null; title: string; text: string; source: string }
  | { kind: "review"; at: string | null; label: string; reason: string; confirmation: string | null; actor: string };

function RunDetails({ run, appId }: { run: RunDetail; appId: string }) {
  return (
    <div className="mt-2 grid gap-4 rounded-xl border border-line-soft bg-[#F9FAFB] p-3 md:grid-cols-[1.2fr_1fr]">
      <StageList rows={run.stages} compact />
      <div className="grid content-start gap-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted">Exact documents used</p>
        {run.documents.length ? (
          run.documents.map((d) => (
            <a key={d.doc_type} href={api.documentUrl(appId, run.id, d.doc_type)} target="_blank" rel="noopener noreferrer"
              className="flex items-center gap-2 rounded-lg border border-line bg-white px-2.5 py-1.5 text-[13px] hover:border-navy-300">
              <FileText className="size-4 text-muted" aria-hidden />
              <span className="flex-1">{d.doc_type === "GST" ? "GST certificate" : "Bank proof"} · v{d.version}</span>
              <span className="font-mono text-[11px] text-muted">{d.sha256_prefix.slice(0, 8)}…</span>
            </a>
          ))
        ) : (
          <p className="text-[13px] text-muted">No documents attached.</p>
        )}
      </div>
    </div>
  );
}

function ChecksAndHistory({ c, className }: { c: Case; className?: string }) {
  const [showAll, setShowAll] = useState(false);
  const [openRun, setOpenRun] = useState<string | null>(null);
  const attention = c.checks.filter((ch) => ch.state !== "PASS");
  const passed = c.checks.length - attention.length;
  const history = useMemo<HistoryItem[]>(() => {
    const items: HistoryItem[] = [
      ...c.runs.map((run) => ({ kind: "run" as const, at: run.created_at, run })),
      ...c.messages.map((m) => ({ kind: "message" as const, at: m.at, title: m.title, text: m.text, source: m.source })),
      ...c.reviews.map((r) => ({ kind: "review" as const, at: r.created_at, label: r.label, reason: r.reason, confirmation: r.confirmation, actor: r.actor })),
    ];
    // Newest first; at equal times show the action, then its message, then the run.
    const order = { review: 0, message: 1, run: 2 };
    return items.sort((a, b) => (b.at ?? "").localeCompare(a.at ?? "") || order[a.kind] - order[b.kind]);
  }, [c]);

  return (
    <Panel
      id="hist-h"
      title="Checks and history"
      className={cx("min-h-[240px]", className)}
      action={
        c.checks.length ? (
          <button type="button" className="text-[13px] font-semibold text-navy-700 hover:underline" aria-expanded={showAll} onClick={() => setShowAll((v) => !v)}>
            {showAll ? "Hide passed checks" : `Show all ${c.checks.length} checks`}
          </button>
        ) : null
      }
    >
      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1">
        {(showAll ? c.checks : attention).length ? (
          <ul className="grid gap-2">
            {(showAll ? c.checks : attention).map((ch) => (
              <li key={ch.rule_id} className="flex gap-2.5 text-[13px]">
                <CheckIcon state={ch.state} />
                <div className="min-w-0">
                  <p className="font-medium text-ink">{ch.label} <span className="font-mono text-[11px] font-normal text-muted">{ch.rule_id}</span></p>
                  {ch.state !== "PASS" || showAll ? <p className="text-muted">{ch.evidence}</p> : null}
                </div>
              </li>
            ))}
          </ul>
        ) : null}
        {!showAll && passed ? (
          <p className="flex items-center gap-2 text-sm text-teal-700">
            <CheckCircle2 className="size-4" aria-hidden />
            {attention.length ? `${passed} other checks passed` : `All ${passed} checks passed`}
          </p>
        ) : null}
        <ol className="grid gap-2 border-t border-line-soft pt-3 text-[13px] text-[#344054]" aria-label="History">
          {history.map((item, i) => (
            <li key={`${item.kind}-${item.at}-${i}`} className="grid grid-cols-[112px_1fr] gap-2.5">
              <span className="text-muted tabular">{formatDateTime(item.at).replace(/ \d{4},/, ",").replace(" IST", "")}</span>
              <div className="min-w-0">
                {item.kind === "run" ? (
                  <>
                    <button type="button" className="inline-flex items-center gap-1 text-left hover:text-ink" aria-expanded={openRun === item.run.id}
                      onClick={() => setOpenRun((o) => (o === item.run.id ? null : item.run.id))}>
                      {item.run.trigger === "submission" ? "Automated check" : "Re-check after changes"} · {formatDuration(item.run.elapsed_ms)} ·{" "}
                      {item.run.status === "APPROVED" ? "approved" : item.run.extraction_error ? "reading unavailable" : "pending"}
                      <ChevronDown className={cx("size-3.5 text-muted", openRun === item.run.id && "rotate-180")} aria-hidden />
                    </button>
                    {openRun === item.run.id ? <RunDetails run={item.run} appId={c.application_id} /> : null}
                  </>
                ) : item.kind === "message" ? (
                  <span>Message added for vendor: <span className="text-ink">{item.title}</span> <span className="text-muted">(application page, no email)</span></span>
                ) : (
                  <span>
                    <span className="font-medium text-ink">{item.label}</span> · “{item.reason}”
                    {item.confirmation ? <span className="block text-xs text-teal-700">✓ {item.confirmation}</span> : null}
                  </span>
                )}
              </div>
            </li>
          ))}
        </ol>
      </div>
    </Panel>
  );
}

// ---------------------------------------------------------------- shortcuts

const CASE_SHORTCUTS: [string, string][] = [
  ["A", "Approve"], ["C", "Request correction"], ["R", "Reject"], ["?", "Show this list"], ["Esc", "Close a dialog"],
];

function ShortcutHelp({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-slate-900/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100vw-2rem)] max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-line bg-white p-5 shadow-raised focus:outline-none">
          <div className="flex items-start justify-between">
            <Dialog.Title className="text-base font-semibold text-ink">Keyboard shortcuts</Dialog.Title>
            <Dialog.Close className="rounded-md p-1 text-muted hover:bg-slate-100" aria-label="Close"><X className="size-4" aria-hidden /></Dialog.Close>
          </div>
          <Dialog.Description className="mt-1 text-[13px] text-muted">Shortcuts are off while you type in a field.</Dialog.Description>
          <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            {CASE_SHORTCUTS.map(([key, label]) => (
              <Fragment key={key}>
                <dt><kbd className="rounded-md border border-line bg-[#F9FAFB] px-1.5 py-0.5 text-xs">{key}</kbd></dt>
                <dd className="text-[#344054]">{label}</dd>
              </Fragment>
            ))}
          </dl>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

// ---------------------------------------------------------------- page

export function AdminCase() {
  const { id = "" } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { onUnauthorized, toast } = useAdmin();
  const requested = params.get("tab") as Tab | null;
  const tab: Tab = requested && TAB_IDS.includes(requested) ? requested : "NEEDS_REVIEW";
  const [c, setC] = useState<Case | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [action, setAction] = useState<Decision | null>(null);
  const [help, setHelp] = useState(false);
  const { data: overview } = useOverview();

  const load = useCallback(() => {
    setC(null);
    setError(null);
    api
      .adminCase(id)
      .then(setC)
      .catch((e: Error) => {
        if (!onUnauthorized(e)) setError(e.message);
      });
  }, [id, onUnauthorized]);
  useEffect(load, [load]);

  const inTab = useCallback(
    (rows: { application_id: string; tab: string }[]) => rows.filter((r) => tab === "ALL" || r.tab === tab).map((r) => r.application_id),
    [tab],
  );
  const list = useMemo(() => inTab(overview?.queue ?? []), [overview, inTab]);
  const index = list.indexOf(id);
  const prevId = index > 0 ? list[index - 1] : null;
  const nextId = index >= 0 && index < list.length - 1 ? list[index + 1] : null;
  const caseUrl = (target: string) => `/admin/cases/${target}${tab === "NEEDS_REVIEW" ? "" : `?tab=${tab}`}`;
  const queueUrl = `/admin${tab === "NEEDS_REVIEW" ? "" : `?tab=${tab}`}`;

  const open = (decision: Decision) => {
    if (c?.can_review) setAction(decision);
  };
  useShortcuts({ a: () => open("APPROVE"), c: () => open("REQUEST_CORRECTION"), r: () => open("REJECT"), "?": () => setHelp(true) }, !!c);

  const docs = useMemo<ViewerDoc[]>(() => {
    if (!c) return [];
    const latest = c.runs[0];
    const own: ViewerDoc[] = (latest?.pdf_types ?? []).map((t) => ({
      key: `own-${t}`, label: t === "GST" ? "GST certificate" : "Bank proof", applicationId: c.application_id, runId: latest.id, docType: t,
    }));
    const linked: ViewerDoc[] = c.linked_records.flatMap((r) =>
      r.latest_run_id && r.documents.includes("BANK")
        ? [{ key: `linked-${r.application_id}`, label: `${r.application_id} bank proof`, applicationId: r.application_id, runId: r.latest_run_id, docType: "BANK" as const }]
        : [],
    );
    return [...own, ...linked];
  }, [c]);

  const onSaved = async (saved: Case) => {
    setAction(null);
    setC(saved);
    toast("Decision saved · Message added for vendor");
    // Auto-advance: the next case in the same queue tab, keeping the queue order.
    try {
      const fresh = inTab((await api.overview()).queue).filter((other) => other !== id);
      const target = fresh[Math.min(Math.max(index, 0), fresh.length - 1)];
      navigate(target ? caseUrl(target) : queueUrl);
    } catch (e) {
      onUnauthorized(e);
    }
  };

  if (error) {
    return (
      <div className="mx-auto max-w-3xl py-8">
        <Alert tone="error" title="Case unavailable">{error}</Alert>
        <Link to={queueUrl} className="mt-4 inline-block text-sm font-medium text-navy-700 hover:underline">← Back to applications</Link>
      </div>
    );
  }
  if (!c) return <div className="p-8"><Spinner label="Loading case…" /></div>;

  const linkedIds = c.linked_records.map((r) => r.application_id).join(", ");
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      {/* Header card */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl border border-line bg-white px-4 py-3">
        <Link to={queueUrl} className="inline-flex items-center gap-1.5 rounded-[10px] border border-[#D0D5DD] px-3 py-2 text-sm font-medium text-[#344054] hover:bg-slate-50">
          <ArrowLeft className="size-4" aria-hidden /> Queue
        </Link>
        <div className="min-w-0">
          <h1 className="text-xl font-bold text-ink">{c.business || "Unnamed business"}</h1>
          <p className="text-xs text-muted tabular">
            {c.application_id}{c.gstin ? ` · GSTIN ${c.gstin}` : ""}{c.contact.state ? ` · ${c.contact.state}` : ""} · Submitted {formatDateTime(c.created_at)}
          </p>
        </div>
        {c.status === "PENDING" ? <OwnerPill owner={c.owner} label={c.owner === "TEAM" ? "With our team" : c.owner_label} className="text-[13px]" /> : <StatusBadge status={c.status} />}
        {c.status === "PENDING" && c.risk ? <RiskTag risk={c.risk} suffix=" risk" /> : null}
        {c.status === "PENDING" ? <span className="text-[13px] text-muted">Waiting {formatAge(c.updated_at)}</span> : null}
        {c.decision_source === "MANUAL" ? <Pill>Reviewer decision</Pill> : null}
        <div className="flex-1" />
        {index >= 0 ? <span className="text-[13px] text-muted tabular">{index + 1} of {list.length}</span> : null}
        <button type="button" aria-label="Previous case" disabled={!prevId} onClick={() => prevId && navigate(caseUrl(prevId))}
          className="grid size-10 place-items-center rounded-[10px] border border-[#D0D5DD] bg-white disabled:opacity-40">
          <ChevronLeft className="size-4" aria-hidden />
        </button>
        <button type="button" aria-label="Next case" disabled={!nextId} onClick={() => nextId && navigate(caseUrl(nextId))}
          className="grid size-10 place-items-center rounded-[10px] border border-[#D0D5DD] bg-white disabled:opacity-40">
          <ChevronRight className="size-4" aria-hidden />
        </button>
        <button type="button" aria-label="Keyboard shortcuts" onClick={() => setHelp(true)}
          className="grid size-10 place-items-center rounded-[10px] border border-[#D0D5DD] bg-white text-muted">
          <Keyboard className="size-4" aria-hidden />
        </button>
      </div>

      {/* Evidence (left) + documents (right) */}
      <div className="grid gap-3 fit:min-h-0 fit:flex-1 lg:grid-cols-[minmax(0,5fr)_minmax(0,6fr)]">
        <div className="flex flex-col gap-3 fit:min-h-0 fit:overflow-y-auto">
          <WhyItsHere c={c} tab={tab} />
          {c.linked_records.map((r) => <LinkedRecordPanel key={r.application_id} record={r} tab={tab} />)}
          <ComparedValues c={c} />
          <ChecksAndHistory c={c} className="fit:min-h-[240px] fit:flex-1" />
        </div>
        <DocumentViewer key={c.application_id} docs={docs} onUnauthorized={onUnauthorized} className="min-h-[560px] fit:min-h-0" />
      </div>

      {/* Action bar: always visible */}
      <footer className="sticky bottom-0 z-10 flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-white px-4 py-3">
        <span className="min-w-[240px] flex-1 text-[13px] text-muted">
          {!c.can_review
            ? c.status === "PENDING" ? "A decision is possible once a completed check exists." : "Final decision recorded. This case is read-only."
            : c.requires_confirmation
              ? `Approving this case needs a bank-change confirmation: a call-back to the contact on ${linkedIds || "the existing record"}.`
              : c.owner === "VENDOR" ? "Waiting on the vendor. You can still decide now if the evidence is enough." : "Each decision needs a reason. The vendor gets a message on their application page."}
        </span>
        {c.can_review ? (
          <>
            <button type="button" onClick={() => open("APPROVE")} className="rounded-xl border border-[#D0D5DD] bg-white px-[18px] py-2.5 text-sm font-semibold text-[#344054] hover:bg-slate-50">
              Approve <kbd className="ml-1.5 rounded-[5px] border border-[#D0D5DD] px-1.5 text-[11px] text-muted">{DECISIONS.APPROVE.key}</kbd>
            </button>
            <button type="button" onClick={() => open("REQUEST_CORRECTION")} className="rounded-xl bg-navy-50 px-[18px] py-2.5 text-sm font-semibold text-navy-600 hover:bg-navy-100">
              Request correction <kbd className="ml-1.5 rounded-[5px] border border-navy-200 px-1.5 text-[11px]">{DECISIONS.REQUEST_CORRECTION.key}</kbd>
            </button>
            <button type="button" onClick={() => open("REJECT")} className="rounded-xl bg-[#B42318] px-[18px] py-2.5 text-sm font-semibold text-white hover:bg-red-800">
              Reject <kbd className="ml-1.5 rounded-[5px] border border-white/50 px-1.5 text-[11px]">{DECISIONS.REJECT.key}</kbd>
            </button>
          </>
        ) : null}
      </footer>

      <DecisionDialog c={c} action={action} onClose={() => setAction(null)} onSaved={onSaved} onUnauthorized={onUnauthorized} />
      <ShortcutHelp open={help} onOpenChange={setHelp} />
    </div>
  );
}
