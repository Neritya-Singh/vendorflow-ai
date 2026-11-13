import { ArrowLeft, ArrowRight, FileText, Plus, Search, Send } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { VendorFrame } from "../components/AppShell";
import { CredentialsCard, DecisionCard, SavedStages, ScopeNote } from "../components/Outcome";
import { ProcessingPanel } from "../components/ProcessingPanel";
import { DetailsCards } from "../components/vendor/DetailsCards";
import { DocumentSlot, SLOT_SHORT } from "../components/vendor/DocumentSlot";
import { Alert, Button, CopyValue, Spinner, cx } from "../components/ui";
import { api, submitDraft } from "../lib/api";
import type { Contact, DraftFieldKey, DraftView, Slot } from "../lib/types";
import { useSlotReading } from "../lib/useSlotReading";
import { useWorkflowRun } from "../lib/useWorkflowRun";
import { useAppState } from "../state";

const SLOTS: Slot[] = ["GST", "BANK"];

/** A rounded content card used for every vendor step (V2_03 §6). */
function Panel({ children, className, labelledBy }: { children: ReactNode; className?: string; labelledBy?: string }) {
  return (
    <section aria-labelledby={labelledBy} className={cx("flex min-h-0 flex-col rounded-2xl border border-line bg-white sm:rounded-[20px]", className)}>
      {children}
    </section>
  );
}

function StepTitle({ id, title, text }: { id: string; title: string; text: string }) {
  return (
    <div className="flex flex-col gap-1">
      <h1 id={id} tabIndex={-1} className="text-[22px] font-bold tracking-[-0.01em] text-ink focus:outline-none sm:text-[26px]">{title}</h1>
      <p className="text-sm text-muted sm:text-[15px]">{text}</p>
    </div>
  );
}

function Recovery({ creds, compact }: { creds: { application_id: string; tracking_code: string }; compact?: boolean }) {
  if (compact) {
    return (
      <details className="rounded-xl text-[13px] text-muted">
        <summary className="cursor-pointer font-medium text-navy-700">Save your code to come back later</summary>
        <div className="mt-2 grid gap-2">
          <CopyValue label="Application ID" value={creds.application_id} />
          <CopyValue label="Private tracking code" value={creds.tracking_code} secret />
        </div>
      </details>
    );
  }
  return (
    <Panel className="gap-3 px-6 py-5">
      <h2 className="text-base font-semibold text-ink">Come back later</h2>
      <p className="text-[13px] text-muted">Your progress is saved. Keep these two to open your application again.</p>
      <CopyValue label="Application ID" value={creds.application_id} />
      <CopyValue label="Private tracking code" value={creds.tracking_code} secret />
    </Panel>
  );
}

export function ApplyPage() {
  const { apply, updateApply, resetApply, meta, setHandoff } = useAppState();
  const navigate = useNavigate();
  const { state: run, start, reset } = useWorkflowRun();
  const [view, setView] = useState<DraftView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [ack, setAck] = useState(false);
  const [showBlockers, setShowBlockers] = useState(false);
  const saving = useRef<Promise<unknown>>(Promise.resolve());
  const contactRef = useRef<Contact | null>(null);
  const { creds } = apply;
  const maxBytes = meta?.max_pdf_bytes ?? 5 * 1024 * 1024;

  // Credentials first: nothing is stored until the first file arrives.
  useEffect(() => {
    if (creds || apply.receipt) return;
    let cancelled = false;
    api.intake().then((c) => !cancelled && updateApply({ creds: c, resume: false })).catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [creds, apply.receipt, updateApply]);

  // Reopen a saved draft (from the track page).
  useEffect(() => {
    if (!creds || !apply.resume || view) return;
    setLoading(true);
    api
      .openDraft(creds)
      .then((v) => {
        setView(v);
        contactRef.current = v.contact;
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [creds, apply.resume, view]);

  // Until a draft exists only the documents step makes sense.
  const step = view ? apply.step : 0;
  useEffect(() => {
    document.getElementById(`step-${step}-h`)?.focus();
  }, [step]);

  const adopt = useCallback((v: DraftView) => {
    // Two uploads run in parallel; keep whichever saved draft is newest.
    setView((current) => (current && current.rev > v.rev ? current : v));
    if (!contactRef.current) contactRef.current = v.contact;
  }, []);
  const { activity, slotErrors, upload, move, retry } = useSlotReading<DraftView>({ creds, base: "/api/vendor/draft", maxBytes, adopt });

  const save = (body: Parameters<typeof api.saveDraft>[1]) => {
    if (!creds) return Promise.resolve();
    // Serialise saves so a later edit never lands before an earlier one.
    const next = saving.current.then(() =>
      api.saveDraft(creds, body).then(adopt).catch((e: Error) => setError(e.message)),
    );
    saving.current = next;
    return next;
  };
  const saveField = (key: DraftFieldKey, value: string) => void save({ changes: { [key]: value } });
  const resetField = (key: DraftFieldKey) => void save({ reset: [key] });
  const saveContact = (patch: Partial<Contact>) => {
    const merged = { ...(contactRef.current ?? { name: "", email: "", phone: "" }), ...patch };
    contactRef.current = merged;
    void save({ contact: merged });
  };

  const goTo = async (next: number) => {
    setShowBlockers(false);
    if (next > step) {
      (document.activeElement as HTMLElement | null)?.blur?.(); // commits the field being edited
      await new Promise((r) => setTimeout(r, 0));
      await saving.current;
    }
    updateApply({ step: next });
    window.scrollTo({ top: 0 });
  };

  const submit = async () => {
    if (!creds) return;
    window.scrollTo({ top: 0 });
    const result = await start((cb) => submitDraft(creds, cb));
    if (result) updateApply({ receipt: { creds, view: result } });
  };

  const startAnother = () => {
    resetApply();
    reset();
    setView(null);
    contactRef.current = null;
    setAck(false);
    window.scrollTo({ top: 0 });
  };

  // ------------------------------------------------------------ result
  if (apply.receipt) {
    const { creds: c, view: result } = apply.receipt;
    return (
      <VendorFrame step={3}>
        <div className="grid min-h-0 flex-1 gap-4 fit:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          <div className="flex min-h-0 flex-col gap-4 fit:overflow-y-auto [&>*]:shrink-0">
            <h1 id="step-3-h" tabIndex={-1} className="sr-only">Your result</h1>
            <DecisionCard view={result} />
            <div className="flex flex-wrap gap-3">
              <Button size="lg" icon={Search} onClick={() => { setHandoff(c); navigate("/track"); }}>
                {result.editable ? "Fix items" : "Open my application"}
              </Button>
              <Button size="lg" variant="secondary" icon={Plus} onClick={startAnother}>Start another application</Button>
            </div>
          </div>
          <div className="flex min-h-0 flex-col gap-4 fit:overflow-y-auto [&>*]:shrink-0">
            <CredentialsCard creds={c} mode="receipt" />
            <SavedStages view={result} />
            <ScopeNote />
          </div>
        </div>
      </VendorFrame>
    );
  }

  // ------------------------------------------------------------ live check
  if (run.phase !== "idle" && creds) {
    return (
      <VendorFrame step={3}>
        <div className="grid min-h-0 flex-1 items-start gap-4 fit:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          <div className="flex min-h-0 flex-col gap-4 fit:max-h-full fit:overflow-y-auto [&>*]:shrink-0">
            <StepTitle id="step-3-h" title="Checking your application" text="Stay on this page. Your result appears here as soon as it's saved." />
            <ProcessingPanel run={run} title="Live check" onRetry={submit} onCheckStatus={() => { setHandoff(creds); navigate("/track"); }} />
            {run.phase === "failed" ? <Button variant="secondary" icon={ArrowLeft} onClick={() => reset()}>Back to review</Button> : null}
          </div>
          <CredentialsCard creds={creds} mode="before" />
        </div>
      </VendorFrame>
    );
  }

  if (!creds || loading) {
    return (
      <VendorFrame step={step}>
        {error ? <Alert tone="error" title="Couldn't start your application">{error}</Alert> : <Spinner label="Preparing your application…" />}
      </VendorFrame>
    );
  }

  // ------------------------------------------------------------ 1 documents
  if (step === 0) {
    const ready = !!view?.documents_ready && !Object.keys(activity).length;
    return (
      <VendorFrame step={0}>
        <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <Panel labelledBy="step-0-h" className="gap-3 p-4 sm:gap-[18px] sm:px-8 sm:py-7">
            <StepTitle id="step-0-h" title="Upload your documents" text="We read the details for you, so you won't need to type them. PDF, JPG or PNG up to 5 MB. A clear phone photo works." />
            <div className="flex min-h-0 flex-1 flex-col gap-3 fit:overflow-y-auto">
              {SLOTS.map((slot) => (
                <DocumentSlot
                  key={slot}
                  slot={slot}
                  file={view?.files[slot] ?? null}
                  activity={activity[slot] ?? null}
                  error={slotErrors[slot] ?? null}
                  maxBytes={maxBytes}
                  onFile={(f) => void upload(slot, f)}
                  onMove={() => view && void move(slot, view)}
                  onRetry={retry(slot)}
                />
              ))}
              {error ? <Alert tone="error">{error}</Alert> : null}
            </div>
            <div className="lg:hidden"><Recovery creds={creds} compact /></div>
            <div className="flex flex-col gap-3 border-t border-line-soft pt-3 sm:flex-row sm:items-center sm:justify-between sm:pt-4">
              <span className="hidden text-[13px] text-muted sm:block">Your progress is saved automatically.</span>
              <Button size="lg" className="min-h-[52px] rounded-[14px] text-base sm:min-h-11 sm:rounded-xl sm:px-7" disabled={!ready} onClick={() => void goTo(1)}>
                Continue <ArrowRight className="size-4" aria-hidden />
              </Button>
            </div>
          </Panel>
          <aside className="hidden min-h-0 flex-col gap-4 lg:flex">
            <Panel className="gap-3 px-6 py-5">
              <h2 className="text-base font-semibold text-ink">What you need</h2>
              <ul className="flex flex-col gap-2.5 text-sm text-ink">
                {SLOTS.map((s) => (
                  <li key={s} className="flex items-center gap-2.5">
                    <span aria-hidden className={cx("size-2 rounded-full", view?.files[s]?.status === "read" ? "bg-teal-600" : activity[s] ? "bg-navy-600" : "bg-[#98A2B3]")} />
                    {s === "GST" ? "GST registration certificate" : "Cancelled cheque or bank letter"}
                  </li>
                ))}
              </ul>
              <span className="text-[13px] text-muted">Takes about 5 minutes.</span>
            </Panel>
            <Panel className="gap-3.5 px-6 py-5">
              <h2 className="text-base font-semibold text-ink">What happens next</h2>
              <ol className="flex flex-col gap-3.5 text-sm text-[#344054]">
                {["You check the details we read from your documents.", "We check your application automatically.",
                  "You see the result right away, and exactly what to fix if anything is needed."].map((t, i) => (
                  <li key={t} className="flex gap-3">
                    <span aria-hidden className="grid size-6 shrink-0 place-items-center rounded-lg bg-[#F2F4F7] text-xs font-semibold">{i + 1}</span>
                    {t}
                  </li>
                ))}
              </ol>
            </Panel>
            <Recovery creds={creds} />
          </aside>
        </div>
      </VendorFrame>
    );
  }

  if (!view) return null;

  // ------------------------------------------------------------ 2 details
  if (step === 1) {
    return (
      <VendorFrame step={1}>
        <div className="flex min-h-0 flex-1 flex-col gap-3 sm:gap-4">
          <div className="px-1 sm:px-2">
            <StepTitle id="step-1-h" title="Check your details" text="We read these from your documents. Fix anything that looks wrong, then continue." />
          </div>
          {error ? <Alert tone="error">{error}</Alert> : null}
          <div className="grid min-h-0 flex-1 gap-3 sm:gap-4 lg:grid-cols-3">
            <DetailsCards view={view} states={meta?.states ?? []} onSave={saveField} onReset={resetField} onContact={saveContact} />
          </div>
          {showBlockers && view.blockers.length ? (
            <Alert tone="warning" title="Before you continue">
              <ul className="list-disc pl-5">{view.blockers.map((b) => <li key={b}>{b}</li>)}</ul>
            </Alert>
          ) : null}
          <div className="sticky bottom-0 z-10 -mx-3 flex items-center gap-2.5 bg-canvas px-3 pb-1 pt-1 sm:static sm:mx-0 sm:justify-between sm:rounded-2xl sm:border sm:border-line sm:bg-white sm:py-3 sm:pl-6 sm:pr-4">
            <span className="hidden text-[13px] text-muted sm:block">If you change a value we read, our team will compare it with your document.</span>
            <div className="flex flex-1 gap-2.5 sm:flex-none">
              <Button size="lg" variant="secondary" className="min-h-[52px] rounded-[14px] sm:min-h-11 sm:rounded-xl" onClick={() => void goTo(0)}>Back</Button>
              <Button
                size="lg"
                className="min-h-[52px] flex-1 rounded-[14px] text-base sm:min-h-11 sm:flex-none sm:rounded-xl sm:px-7"
                onClick={async () => {
                  (document.activeElement as HTMLElement | null)?.blur?.();
                  await new Promise((r) => setTimeout(r, 0));
                  await saving.current;
                  setShowBlockers(true);
                }}
                data-ready={view.details_ready}
              >
                Continue <ArrowRight className="size-4" aria-hidden />
              </Button>
            </div>
          </div>
          <ContinueWhenReady show={showBlockers} ready={view.details_ready} onReady={() => void goTo(2)} />
        </div>
      </VendorFrame>
    );
  }

  // ------------------------------------------------------------ 3 submit
  const field = (key: DraftFieldKey) => view.fields.find((f) => f.key === key)!;
  const rows: [string, string][] = [
    ["Legal name", field("legal_name").value], ["GSTIN", field("gstin").value], ["PAN", view.pan.value],
    ["State", field("business_state").value], ["Account holder", field("bank_holder").value],
    ["Account number", field("account_number").value], ["IFSC", field("ifsc").value],
    ["Contact", [view.contact.name, view.contact.phone, view.contact.email].filter(Boolean).join(" · ")],
  ];
  return (
    <VendorFrame step={2}>
      <div className="grid min-h-0 flex-1 gap-3 sm:gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Panel labelledBy="step-2-h" className="gap-4 p-4 sm:px-8 sm:py-7">
          <StepTitle id="step-2-h" title="Review and submit" text="One last look. You can go back to change anything." />
          <dl className="grid min-h-0 gap-x-6 fit:overflow-y-auto sm:grid-cols-2">
            {rows.map(([label, value]) => (
              <div key={label} className="border-t border-[#F2F4F7] py-2.5">
                <dt className="text-xs text-muted">{label}</dt>
                <dd className="mt-0.5 break-words text-[15px] font-medium text-ink">{value || "—"}</dd>
              </div>
            ))}
            <div className="border-t border-[#F2F4F7] py-2.5 sm:col-span-2">
              <dt className="text-xs text-muted">Documents</dt>
              <dd className="mt-0.5 flex flex-wrap gap-x-4 gap-y-1 text-[15px] font-medium text-ink">
                {SLOTS.map((s) => (
                  <span key={s} className="inline-flex items-center gap-1.5"><FileText className="size-4 text-muted" aria-hidden />{SLOT_SHORT[s]}: {view.files[s]?.filename ?? "—"}</span>
                ))}
              </dd>
            </div>
          </dl>
          {view.flagged.length ? (
            <Alert tone="info">
              You changed or typed {view.flagged.length === 1 ? "one value" : `${view.flagged.length} values`} that we couldn't take from your documents. Our team will compare {view.flagged.length === 1 ? "it" : "them"} with your documents before deciding.
            </Alert>
          ) : null}
        </Panel>
        <div className="flex min-h-0 flex-col gap-3 sm:gap-4 fit:overflow-y-auto [&>*]:shrink-0">
          <CredentialsCard creds={creds} mode="before" />
          <Panel className="gap-4 px-5 py-5 sm:px-6">
            <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-line bg-slate-50 px-4 py-3">
              <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} className="mt-0.5 size-5 shrink-0 accent-navy-600" />
              <span className="text-sm text-ink">These details are correct and belong to my business.</span>
            </label>
            <div className="flex gap-2.5">
              <Button size="lg" variant="secondary" className="min-h-[52px] rounded-[14px] sm:min-h-11 sm:rounded-xl" onClick={() => void goTo(1)}>Back</Button>
              <Button size="lg" icon={Send} className="min-h-[52px] flex-1 rounded-[14px] text-base sm:min-h-11 sm:rounded-xl" disabled={!ack || !view.details_ready} onClick={() => void submit()}>
                Submit for checking
              </Button>
            </div>
          </Panel>
        </div>
      </div>
    </VendorFrame>
  );
}

/** Moves on once the latest saved draft says the details are complete. */
function ContinueWhenReady({ show, ready, onReady }: { show: boolean; ready: boolean; onReady: () => void }) {
  useEffect(() => {
    if (show && ready) onReady();
  }, [show, ready, onReady]);
  return null;
}
