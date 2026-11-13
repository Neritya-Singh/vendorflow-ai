import { CheckCircle2, ClipboardCheck, FileText, History, KeyRound, MessageSquareText, ShieldAlert, TriangleAlert, XCircle } from "lucide-react";
import { useState } from "react";
import { formatDateTime, formatDuration } from "../lib/format";
import type { Credentials, TimelineItem, VendorCheck, VendorView } from "../lib/types";
import { StageList } from "./StageList";
import { Alert, Card, CardHeader, CheckIcon, CopyValue, StatusBadge, cx } from "./ui";

const HERO = {
  APPROVED: {
    ring: "border-teal-200",
    band: "bg-teal-50",
    icon: CheckCircle2,
    iconColor: "text-teal-700",
    title: "Approved",
  },
  PENDING: {
    ring: "border-amber-200",
    band: "bg-amber-50",
    icon: TriangleAlert,
    iconColor: "text-amber-600",
    title: "Pending Review",
  },
  REJECTED: {
    ring: "border-red-200",
    band: "bg-red-50",
    icon: XCircle,
    iconColor: "text-red-700",
    title: "Rejected",
  },
} as const;

/** The single authoritative outcome: status, the main reasons and one next action. */
export function DecisionCard({ view }: { view: VendorView }) {
  const hero = HERO[view.status] ?? HERO.PENDING;
  const Icon = hero.icon;
  const subtitle =
    view.status === "APPROVED"
      ? view.decision_source === "MANUAL"
        ? "Approved after human review"
        : "All onboarding document checks passed"
      : view.status === "REJECTED"
        ? "Final decision by a reviewer"
        : view.processing_unavailable
          ? "Document processing temporarily unavailable"
          : view.owner === "Reviewer"
            ? "Waiting for the review team"
            : "Action needed from you";
  return (
    <Card className={cx("overflow-hidden", hero.ring)} aria-live="polite">
      <div className={cx("flex items-start gap-4 px-5 py-5 sm:px-6", hero.band)}>
        <Icon className={cx("mt-0.5 size-8 shrink-0", hero.iconColor)} aria-hidden />
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Decision</p>
          <h2 className="text-2xl font-semibold tracking-tight text-slate-900">{hero.title}</h2>
          <p className="mt-0.5 text-sm text-slate-600">{subtitle}</p>
        </div>
      </div>
      <div className="grid gap-5 px-5 py-5 sm:px-6 md:grid-cols-[1.4fr_1fr]">
        <div>
          <h3 className="text-[13px] font-semibold text-slate-900">
            {view.status === "APPROVED" ? "Why" : view.reasons.length > 1 ? "Main reasons" : "Reason"}
          </h3>
          <ul className="mt-2 space-y-2">
            {view.reasons.map((reason) => (
              <li key={reason} className="flex gap-2 text-sm leading-relaxed text-slate-700">
                <span aria-hidden className={cx("mt-2 size-1.5 shrink-0 rounded-full", view.status === "APPROVED" ? "bg-teal-500" : view.status === "REJECTED" ? "bg-red-500" : "bg-amber-500")} />
                {reason}
              </li>
            ))}
          </ul>
        </div>
        <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Next step</p>
          <p className="mt-1 text-sm font-semibold text-slate-900">{view.heading}</p>
          <p className="mt-1 text-[13px] leading-relaxed text-slate-600">{view.next_step}</p>
        </div>
      </div>
      {view.reviewer_note ? (
        <div className="border-t border-slate-200 px-5 py-4 sm:px-6">
          <div className="flex gap-3">
            <MessageSquareText className="mt-0.5 size-4 shrink-0 text-navy-600" aria-hidden />
            <div>
              <p className="text-[13px] font-semibold text-slate-900">
                {view.reviewer_note.title}
                <span className="font-normal text-slate-500"> · {formatDateTime(view.reviewer_note.at)}</span>
              </p>
              <p className="mt-1 text-sm text-slate-700">“{view.reviewer_note.message}”</p>
            </div>
          </div>
        </div>
      ) : null}
    </Card>
  );
}

export function CredentialsCard({ creds, mode }: { creds: Credentials; mode: "before" | "receipt" }) {
  return (
    <Card className="border-navy-200">
      <div className="flex items-start gap-3 px-5 pt-4">
        <KeyRound className="mt-0.5 size-5 shrink-0 text-navy-700" aria-hidden />
        <div>
          <h2 className="text-[15px] font-semibold text-slate-900">
            {mode === "before" ? "Save your recovery details now" : "Your application receipt"}
          </h2>
          <p className="mt-0.5 text-[13px] text-slate-600">
            {mode === "before"
              ? "These identify this application. If anything interrupts submission, use them to resume the same application."
              : "You need both to track or correct this application."}
          </p>
        </div>
      </div>
      <div className="grid gap-3 px-5 py-4 sm:grid-cols-2">
        <CopyValue label="Application ID" value={creds.application_id} />
        <CopyValue label="Private tracking code" value={creds.tracking_code} secret />
      </div>
      <p className="flex items-start gap-2 border-t border-slate-100 bg-slate-50 px-5 py-2.5 text-xs text-slate-600">
        <ShieldAlert className="mt-px size-3.5 shrink-0 text-amber-600" aria-hidden />
        The tracking code is shown only in this session and is stored by us as a one-way hash — it cannot be recovered
        or resent. Keep it private, like a password.
      </p>
    </Card>
  );
}

export function VendorChecks({ checks }: { checks: VendorCheck[] }) {
  const attention = checks.filter((c) => c.state !== "PASS");
  const [showPassed, setShowPassed] = useState(attention.length === 0);
  const passed = checks.filter((c) => c.state === "PASS");
  return (
    <Card>
      <CardHeader
        title="Checks"
        description={`${passed.length} passed · ${attention.length} need attention`}
        action={<ClipboardCheck className="size-4 text-slate-400" aria-hidden />}
      />
      <ul className="divide-y divide-slate-100">
        {attention.map((c) => (
          <li key={c.label} className="flex gap-3 px-5 py-3">
            <CheckIcon state={c.state} />
            <div className="min-w-0">
              <p className="text-sm font-medium text-slate-900">{c.label}</p>
              <p className="mt-0.5 text-[13px] text-slate-600">{c.detail}</p>
            </div>
          </li>
        ))}
        {attention.length === 0 ? (
          <li className="px-5 py-3 text-sm text-slate-600">No checks need attention.</li>
        ) : null}
      </ul>
      {passed.length ? (
        <div className="border-t border-slate-100 px-5 py-3">
          <button
            type="button"
            className="text-[13px] font-medium text-navy-700 hover:underline"
            aria-expanded={showPassed}
            onClick={() => setShowPassed((v) => !v)}
          >
            {showPassed ? "Hide" : "Show"} {passed.length} passed checks
          </button>
          {showPassed ? (
            <ul className="mt-2 grid gap-x-6 gap-y-1.5 sm:grid-cols-2">
              {passed.map((c) => (
                <li key={c.label} className="flex items-center gap-2 text-[13px] text-slate-700">
                  <CheckIcon state="PASS" /> {c.label}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}

export function VendorTimeline({ items }: { items: TimelineItem[] }) {
  return (
    <Card>
      <CardHeader title="History" description="Every saved check and reviewer action, newest first" action={<History className="size-4 text-slate-400" aria-hidden />} />
      <ol className="px-5 py-4">
        {items.map((item, i) => (
          <li key={`${item.kind}-${item.at}-${i}`} className="relative flex gap-3 pb-4 last:pb-0">
            {i < items.length - 1 ? <span aria-hidden className="absolute left-[7px] top-5 bottom-0 w-px bg-slate-200" /> : null}
            <span
              aria-hidden
              className={cx(
                "mt-1 size-[15px] shrink-0 rounded-full border-2 bg-white",
                item.kind === "review" ? "border-navy-500" : item.status === "APPROVED" ? "border-teal-500" : item.status === "REJECTED" ? "border-red-500" : "border-amber-500",
              )}
            />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <p className="text-sm font-medium text-slate-900">{item.title}</p>
                {item.kind === "run" ? <StatusBadge status={item.status} /> : null}
              </div>
              <p className="mt-0.5 text-xs text-slate-500">
                {formatDateTime(item.at)}
                {item.kind === "run" && item.elapsed_ms != null ? ` · automated check took ${formatDuration(item.elapsed_ms)}` : ""}
              </p>
              {item.message ? <p className="mt-1 text-[13px] text-slate-700">“{item.message}”</p> : null}
              {item.documents?.length ? (
                <p className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
                  <FileText className="size-3.5" aria-hidden />
                  {item.documents.map((d) => `${d.doc_type === "GST" ? "GST certificate" : "Bank proof"} v${d.version}`).join(" · ")}
                </p>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}

export function SavedStages({ view }: { view: VendorView }) {
  return (
    <Card>
      <CardHeader
        title="How this decision was made"
        description={view.elapsed_ms != null ? `Latest automated check · ${formatDuration(view.elapsed_ms)} measured on the server` : "Latest automated check"}
      />
      <div className="px-5 py-4">
        <StageList rows={view.stages} />
      </div>
    </Card>
  );
}

export function ScopeNote() {
  return (
    <Alert tone="info" className="text-[13px]">
      A decision reflects whether your submitted details agree with your uploaded PDFs under our onboarding checks.
      It is not a government GST lookup or a confirmation of bank-account ownership by a bank.
    </Alert>
  );
}
