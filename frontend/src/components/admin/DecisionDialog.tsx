import * as Dialog from "@radix-ui/react-dialog";
import { CheckCircle2, MessageSquareWarning, RefreshCw, X, XCircle } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { ApiError, api } from "../../lib/api";
import type { AdminCase } from "../../lib/types";
import { Alert, Button, Textarea, cx } from "../ui";

export type Decision = "APPROVE" | "REQUEST_CORRECTION" | "REJECT";

export const DECISIONS: Record<Decision, {
  title: string; verb: string; key: string; icon: typeof CheckCircle2; variant: "success" | "primary" | "danger";
  reasonLabel: string; reasonHint: string; chips: string[];
}> = {
  APPROVE: {
    title: "Approve application", verb: "Approve", key: "A", icon: CheckCircle2, variant: "success",
    reasonLabel: "Reason for approving", reasonHint: "Kept in the audit trail. Not shown to the vendor.",
    chips: [
      "Documents consistent after manual check",
      "Name difference explained: trade name or legal-suffix variant",
      "Bank account ownership confirmed with the vendor",
    ],
  },
  REQUEST_CORRECTION: {
    title: "Request a correction", verb: "Send request", key: "C", icon: MessageSquareWarning, variant: "primary",
    reasonLabel: "Message to the vendor", reasonHint: "Drafted from the flagged items. Edit it before sending.",
    chips: [],
  },
  REJECT: {
    title: "Reject application", verb: "Reject", key: "R", icon: XCircle, variant: "danger",
    reasonLabel: "Reason (shown to the vendor)", reasonHint: "Final. Write it so the vendor understands the decision.",
    chips: [
      "Bank account not owned by the business",
      "Documents do not belong to this business",
      "Business details could not be confirmed from the documents",
    ],
  },
};

/** The exact message the vendor will see (mirrors backend message_log templates). */
export function vendorPreview(action: Decision, reason: string, buyer = "Zamp AI"): string | null {
  const text = reason.trim().replace(/\.$/, "");
  if (action === "REQUEST_CORRECTION") return `Our team needs one change: ${text || "…"}. Open your application page to make it.`;
  if (action === "REJECT") return `We couldn't approve your application: ${text || "…"}. Questions: contact ${buyer}'s finance team.`;
  return `Your business is approved as a supplier to ${buyer}.`;
}

export function DecisionDialog({ c, action, onClose, onSaved, onUnauthorized, buyer }: {
  c: AdminCase;
  action: Decision | null;
  onClose: () => void;
  onSaved: (next: AdminCase) => void;
  onUnauthorized: (e: unknown) => boolean;
  buyer?: string;
}) {
  const def = action ? DECISIONS[action] : null;
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; stale: boolean } | null>(null);
  const reasonId = useId();
  const needsConfirmation = action === "APPROVE" && c.requires_confirmation;

  useEffect(() => {
    if (!action) return;
    setReason(action === "REQUEST_CORRECTION" ? c.correction_draft : "");
    setConfirmed(false);
    setError(null);
  }, [action, c.correction_draft]);

  const ready = reason.trim().length >= 3 && (!needsConfirmation || confirmed) && !!c.latest_run_id;

  const save = async () => {
    if (!action || !c.latest_run_id || !ready) return;
    setBusy(true);
    setError(null);
    try {
      const next = await api.review(c.application_id, {
        action,
        reason: reason.trim(),
        expected_revision: c.revision,
        expected_latest_run_id: c.latest_run_id,
        ...(needsConfirmation ? { confirmation: c.confirmation_text } : {}),
      });
      onSaved(next);
    } catch (e) {
      if (onUnauthorized(e)) return;
      setError({ message: e instanceof Error ? e.message : "Decision not saved.", stale: e instanceof ApiError && e.status === 409 });
    } finally {
      setBusy(false);
    }
  };

  const preview = action ? vendorPreview(action, reason, buyer) : null;
  const Icon = def?.icon ?? CheckCircle2;
  return (
    <Dialog.Root open={!!action} onOpenChange={(open) => !open && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-slate-900/40" />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 z-50 flex max-h-[calc(100dvh-2rem)] w-[calc(100vw-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 flex-col rounded-2xl border border-line bg-white shadow-xl focus:outline-none"
          onOpenAutoFocus={(e) => {
            e.preventDefault();
            document.getElementById(reasonId)?.focus();
          }}
        >
          <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
            <div className="flex gap-3">
              <Icon className={cx("mt-0.5 size-5 shrink-0", action === "APPROVE" ? "text-teal-700" : action === "REJECT" ? "text-red-700" : "text-navy-700")} aria-hidden />
              <div>
                <Dialog.Title className="text-base font-semibold text-slate-900">{def?.title}</Dialog.Title>
                <Dialog.Description className="mt-0.5 text-[13px] text-slate-500">
                  {c.business || "Unnamed business"} · <span className="font-mono">{c.application_id}</span>
                </Dialog.Description>
              </div>
            </div>
            <Dialog.Close className="rounded-md p-1 text-slate-500 hover:bg-slate-100" aria-label="Close"><X className="size-4" aria-hidden /></Dialog.Close>
          </div>

          <div className="grid gap-4 overflow-y-auto px-5 py-4">
            {def?.chips.length ? (
              <div>
                <p className="text-[13px] font-medium text-slate-800">Quick reasons</p>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {def.chips.map((chip) => (
                    <button
                      key={chip}
                      type="button"
                      onClick={() => setReason((r) => (r.trim() ? `${r.trim().replace(/\.$/, "")}. ${chip}` : chip))}
                      className="rounded-full border border-slate-300 bg-white px-3 py-1 text-[13px] text-slate-700 hover:border-navy-500 hover:text-navy-800"
                    >
                      {chip}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
            <div>
              <label htmlFor={reasonId} className="text-[13px] font-medium text-slate-800">{def?.reasonLabel}</label>
              <Textarea id={reasonId} className="mt-1.5" maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} />
              <p className="mt-1 flex justify-between gap-3 text-xs text-slate-500">
                <span>{def?.reasonHint}</span>
                <span className="tabular">{reason.length}/1000</span>
              </p>
            </div>
            {needsConfirmation ? (
              <div className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3">
                <p className="text-[13px] font-semibold text-amber-950">This case matches an existing record.</p>
                <p className="mt-0.5 text-[13px] text-amber-900">Approving it needs a confirmed call-back before the bank details are accepted.</p>
                <label className="mt-2 flex items-start gap-2.5 text-sm text-slate-800">
                  <input type="checkbox" className="mt-0.5 size-4 accent-navy-900" checked={confirmed} onChange={(e) => setConfirmed(e.target.checked)} />
                  {c.confirmation_text}
                </label>
              </div>
            ) : null}
            {preview ? (
              <div>
                <p className="text-[13px] font-medium text-slate-800">Message the vendor will see</p>
                <p className="mt-1.5 rounded-xl border border-line bg-slate-50 px-3 py-2 text-sm text-slate-700">{preview}</p>
                <p className="mt-1 text-xs text-slate-500">Added to the vendor's application page. No email is sent in this demo.</p>
              </div>
            ) : null}
            {error ? (
              <Alert tone="error" title="Decision not saved">
                {error.message}
                {error.stale ? <div className="mt-2"><Button size="sm" variant="secondary" icon={RefreshCw} onClick={() => window.location.reload()}>Reload case</Button></div> : null}
              </Alert>
            ) : null}
          </div>

          <div className="flex items-center justify-between gap-2 border-t border-line bg-slate-50 px-5 py-3">
            <p className="text-xs text-slate-500">Saved against revision {c.revision}.</p>
            <div className="flex gap-2">
              <Dialog.Close asChild><Button variant="secondary">Cancel</Button></Dialog.Close>
              <Button variant={def?.variant ?? "primary"} loading={busy} disabled={!ready} onClick={save}>{def?.verb}</Button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
