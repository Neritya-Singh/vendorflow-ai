import { CheckCircle2, CircleDashed, FileText, History, KeyRound, MessageSquareText, ShieldAlert, TriangleAlert, Users, XCircle } from "lucide-react";
import { formatDateTime, formatDuration } from "../lib/format";
import type { Credentials, TimelineItem, VendorView } from "../lib/types";
import { StageList } from "./StageList";
import { Alert, Card, CardHeader, CopyValue, StatusBadge, cx } from "./ui";

type HeroKey = "APPROVED" | "REJECTED" | "VENDOR" | "TEAM" | "DRAFT";
const HERO: Record<HeroKey, { ring: string; band: string; icon: typeof CheckCircle2; iconColor: string; dot: string }> = {
  APPROVED: { ring: "border-teal-200", band: "bg-teal-50", icon: CheckCircle2, iconColor: "text-teal-700", dot: "bg-teal-500" },
  REJECTED: { ring: "border-red-200", band: "bg-red-50", icon: XCircle, iconColor: "text-red-700", dot: "bg-red-500" },
  VENDOR: { ring: "border-amber-200", band: "bg-amber-50", icon: TriangleAlert, iconColor: "text-amber-600", dot: "bg-amber-500" },
  TEAM: { ring: "border-team-200", band: "bg-team-50", icon: Users, iconColor: "text-team-700", dot: "bg-team-500" },
  DRAFT: { ring: "border-line", band: "bg-slate-50", icon: CircleDashed, iconColor: "text-slate-500", dot: "bg-slate-400" },
};

export function heroKey(view: Pick<VendorView, "status" | "owner">): HeroKey {
  if (view.status === "APPROVED" || view.status === "REJECTED") return view.status;
  return view.owner === "VENDOR" || view.owner === "DRAFT" ? view.owner : "TEAM";
}

/** The single authoritative outcome: status, who acts next, exactly what is needed. */
export function DecisionCard({ view }: { view: VendorView }) {
  const hero = HERO[heroKey(view)];
  const Icon = hero.icon;
  return (
    <Card className={cx("overflow-hidden rounded-[20px]", hero.ring)} aria-live="polite" data-status={view.status} data-owner={view.owner}>
      <div className={cx("flex items-start gap-4 px-5 py-5 sm:px-6", hero.band)}>
        <Icon className={cx("mt-0.5 size-8 shrink-0", hero.iconColor)} aria-hidden />
        <div className="min-w-0">
          {/* The status is said once: no eyebrow when it would repeat the heading. */}
          {view.status_label && !view.heading.startsWith(view.status_label) ? (
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{view.status_label}</p>
          ) : null}
          <h2 className="text-2xl font-semibold tracking-tight text-slate-900">{view.heading}</h2>
          {view.reasons.map((reason) => (
            <p key={reason} className="mt-1 text-[15px] leading-relaxed text-slate-700">{reason}</p>
          ))}
        </div>
      </div>
      {view.todo.length ? (
        <div className="border-t border-line px-5 py-4 sm:px-6">
          <h3 className="text-[13px] font-semibold text-slate-900">
            What we need from you ({view.todo.length} {view.todo.length === 1 ? "item" : "items"})
          </h3>
          <ol className="mt-2 space-y-2">
            {view.todo.map((item, i) => (
              <li key={item.key} className="flex gap-3 text-[15px] leading-relaxed text-slate-800">
                <span aria-hidden className="grid size-6 shrink-0 place-items-center rounded-full bg-amber-100 text-xs font-semibold text-amber-800">
                  {i + 1}
                </span>
                {item.text}
              </li>
            ))}
          </ol>
        </div>
      ) : null}
      <div className="border-t border-line px-5 py-4 sm:px-6">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">What happens next</p>
        <p className="mt-1 text-sm leading-relaxed text-slate-700">{view.next_step}</p>
      </div>
      {view.reviewer_note && view.status !== "REJECTED" ? (
        <div className="border-t border-line px-5 py-4 sm:px-6">
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

/** Vendor-facing status pill: says who acts next on a pending application. */
export function VendorStatusPill({ view }: { view: Pick<VendorView, "status" | "owner" | "status_label"> }) {
  const hero = HERO[heroKey(view)];
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-white px-2 py-0.5 text-xs font-medium text-slate-700 ring-1 ring-inset ring-slate-300">
      <span aria-hidden className={cx("size-2 rounded-full", hero.dot)} />
      {view.status_label}
    </span>
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

export function VendorTimeline({ items }: { items: TimelineItem[] }) {
  return (
    <Card>
      <CardHeader title="History" description="Every check and message from our team, newest first" action={<History className="size-4 text-slate-400" aria-hidden />} />
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
                {item.kind === "run" && item.status !== "PENDING" ? <StatusBadge status={item.status} /> : null}
              </div>
              <p className="mt-0.5 text-xs text-slate-500">
                {formatDateTime(item.at)}
                {item.kind === "run" && item.elapsed_ms != null ? ` · took ${formatDuration(item.elapsed_ms)}` : ""}
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
        title="How we checked your application"
        description={view.elapsed_ms != null ? `Latest check · took ${formatDuration(view.elapsed_ms)}` : "Latest check"}
      />
      <div className="px-5 py-4">
        <StageList rows={view.stages} audience="vendor" />
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
