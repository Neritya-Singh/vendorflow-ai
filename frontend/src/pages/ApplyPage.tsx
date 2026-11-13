import { ArrowLeft, ArrowRight, Check, Pencil, Plus, Search, Send } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { PageHeader } from "../components/AppShell";
import { FilePicker } from "../components/FilePicker";
import { CredentialsCard, DecisionCard, SavedStages, ScopeNote } from "../components/Outcome";
import { ProcessingPanel } from "../components/ProcessingPanel";
import { BankSection, BusinessSection, missingDetails, type FieldErrors } from "../components/VendorFormSections";
import { Alert, Button, Card, KeyValue, Spinner, cx } from "../components/ui";
import { api, type WorkflowPayload } from "../lib/api";
import { EMAIL_PATTERN, formatBytes, mask } from "../lib/format";
import type { VendorFields } from "../lib/types";
import { useWorkflowRun } from "../lib/useWorkflowRun";
import { useAppState } from "../state";

const STEPS = ["Business", "Banking and PDFs", "Review and submit"];

function Stepper({ step, onJump }: { step: number; onJump: (i: number) => void }) {
  return (
    <nav aria-label="Application progress">
      <ol className="flex items-center gap-2 sm:gap-3">
        {STEPS.map((label, i) => {
          const done = i < step;
          const current = i === step;
          return (
            <li key={label} className="flex flex-1 items-center gap-2 sm:gap-3">
              <button
                type="button"
                disabled={!done}
                onClick={() => onJump(i)}
                aria-current={current ? "step" : undefined}
                className={cx("flex min-w-0 items-center gap-2 rounded-md text-left", done && "hover:text-navy-800")}
              >
                <span
                  className={cx(
                    "grid size-7 shrink-0 place-items-center rounded-full text-xs font-semibold ring-1 ring-inset",
                    done ? "bg-teal-600 text-white ring-teal-600" : current ? "bg-navy-900 text-white ring-navy-900" : "bg-white text-slate-500 ring-slate-300",
                  )}
                >
                  {done ? <Check className="size-4" aria-hidden /> : i + 1}
                </span>
                <span className={cx("hidden truncate text-sm font-medium sm:block", current ? "text-slate-900" : "text-slate-500")}>{label}</span>
                <span className="sr-only">{done ? "(completed)" : current ? "(current step)" : ""}</span>
              </button>
              {i < STEPS.length - 1 ? <span aria-hidden className={cx("h-px flex-1", done ? "bg-teal-500" : "bg-slate-200")} /> : null}
            </li>
          );
        })}
      </ol>
      <p className="mt-2 text-[13px] text-slate-500 sm:hidden">
        Step {step + 1} of 3 · <span className="font-medium text-slate-700">{STEPS[step]}</span>
      </p>
    </nav>
  );
}

function validateBusiness(f: VendorFields): FieldErrors {
  const errors: FieldErrors = {};
  if (!f.legal_name.trim()) errors.legal_name = "Enter the legal business name.";
  if (!f.contact_email.trim()) errors.contact_email = "Enter a contact email.";
  else if (!EMAIL_PATTERN.test(f.contact_email.trim())) errors.contact_email = "Enter a valid email, such as accounts@example.com.";
  return errors;
}

export function ApplyPage() {
  const { draft, updateDraft, resetDraft, meta, setHandoff } = useAppState();
  const navigate = useNavigate();
  const { state: run, start, reset } = useWorkflowRun();
  const [errors, setErrors] = useState<FieldErrors>({});
  const [ack, setAck] = useState(false);
  const [credError, setCredError] = useState<string | null>(null);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const { fields, step } = draft;
  const setFields = (patch: Partial<VendorFields>) => updateDraft({ fields: { ...fields, ...patch } });

  useEffect(() => {
    headingRef.current?.focus();
  }, [step]);

  // Credentials are issued before submission so an interrupted save can be resumed.
  useEffect(() => {
    if (step !== 2 || draft.creds) return;
    let cancelled = false;
    api
      .intake()
      .then((creds) => !cancelled && updateDraft({ creds }))
      .catch((e: Error) => !cancelled && setCredError(e.message));
    return () => {
      cancelled = true;
    };
  }, [step, draft.creds, updateDraft]);

  const goTo = (next: number) => {
    if (next > 0) {
      const found = validateBusiness(fields);
      setErrors(found);
      if (Object.keys(found).length) {
        updateDraft({ step: 0 });
        return;
      }
    }
    updateDraft({ step: next });
    window.scrollTo({ top: 0 });
  };

  const payload = (): WorkflowPayload | null =>
    draft.creds ? { creds: draft.creds, fields, gst: draft.gst, bank: draft.bank } : null;

  const submit = async () => {
    const p = payload();
    if (!p) return;
    window.scrollTo({ top: 0 });
    const view = await start(p);
    if (view) updateDraft({ receipt: { creds: p.creds, view } });
  };

  const checkStatus = () => {
    if (draft.creds) setHandoff(draft.creds);
    navigate("/track");
  };

  const startAnother = () => {
    resetDraft();
    reset();
    setAck(false);
    window.scrollTo({ top: 0 });
  };

  // ------------------------------------------------------------ receipt
  if (draft.receipt) {
    const { creds, view } = draft.receipt;
    return (
      <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
        <PageHeader
          eyebrow={`Application ${creds.application_id}`}
          title="Your result"
          description="This decision has been saved. Keep your receipt to track or correct this application later."
        />
        <div className="mt-6 grid gap-5">
          <DecisionCard view={view} />
          <CredentialsCard creds={creds} mode="receipt" />
          <SavedStages view={view} />
          <ScopeNote />
          <div className="flex flex-wrap gap-3">
            <Button
              size="lg"
              icon={Search}
              onClick={() => {
                setHandoff(creds);
                navigate("/track");
              }}
            >
              {view.editable ? "Fix items" : "Open my application"}
            </Button>
            <Button size="lg" variant="secondary" icon={Plus} onClick={startAnother}>
              Start another application
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // ------------------------------------------------------------ processing
  if (run.phase !== "idle" && draft.creds) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
        <PageHeader eyebrow={`Application ${draft.creds.application_id}`} title="Checking your application" description="Stay on this page — your result appears here as soon as the decision is saved." />
        <div className="mt-6 grid items-start gap-5 lg:grid-cols-[1.35fr_1fr]">
          <ProcessingPanel run={run} title="Live processing" onRetry={submit} onCheckStatus={checkStatus} />
          <div className="grid gap-5">
            <CredentialsCard creds={draft.creds} mode="before" />
            {run.phase === "failed" ? (
              <Button variant="secondary" icon={ArrowLeft} onClick={() => reset()}>Back to review</Button>
            ) : null}
          </div>
        </div>
      </div>
    );
  }

  // ------------------------------------------------------------ steps
  const missing = missingDetails(fields);
  const missingDocs = [!draft.gst && "GST certificate", !draft.bank && "bank proof"].filter(Boolean) as string[];

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <PageHeader eyebrow="New application" title="Apply as a vendor" />
      <div className="mt-6">
        <Stepper step={step} onJump={goTo} />
      </div>

      <Card className="mt-6">
        <form
          noValidate
          onSubmit={(e) => {
            e.preventDefault();
            if (step < 2) goTo(step + 1);
            else if (ack && draft.creds) void submit();
          }}
        >
          <div className="border-b border-line px-5 py-4 sm:px-6">
            <h2 ref={headingRef} tabIndex={-1} className="text-[17px] font-semibold text-slate-900 focus:outline-none">
              {step === 0 ? "Business details" : step === 1 ? "Banking details and documents" : "Review and submit"}
            </h2>
            <p className="mt-0.5 text-[13px] text-slate-500">
              {step === 0
                ? "Legal name and contact email are required. Other gaps won't block you, but will need review."
                : step === 1
                  ? "Enter bank details exactly as printed on your bank document."
                  : "Check everything once. You can go back to edit any section."}
            </p>
          </div>

          <div className="px-5 py-6 sm:px-6">
            {step === 0 ? (
              <BusinessSection values={fields} onChange={setFields} errors={errors} states={meta?.states ?? []} />
            ) : null}

            {step === 1 ? (
              <div className="grid gap-7">
                <BankSection values={fields} onChange={setFields} />
                <div className="border-t border-line pt-6">
                  <h3 className="text-sm font-semibold text-slate-900">Supporting documents</h3>
                  <p className="mt-0.5 text-[13px] text-slate-500">
                    PDFs with selectable text work best. Photos or scans may not be readable and will go to a reviewer.
                  </p>
                  <div className="mt-4 grid gap-5">
                    <FilePicker
                      label="GST registration certificate"
                      description="Shows your legal name, GSTIN and state."
                      file={draft.gst}
                      onChange={(gst) => updateDraft({ gst })}
                    />
                    <FilePicker
                      label="Bank letter or cancelled cheque"
                      description="Shows the account holder, account number and IFSC."
                      file={draft.bank}
                      onChange={(bank) => updateDraft({ bank })}
                    />
                  </div>
                </div>
              </div>
            ) : null}

            {step === 2 ? (
              <div className="grid gap-6">
                <div className="grid gap-4 sm:grid-cols-2">
                  <section className="rounded-lg border border-line px-4 py-2">
                    <div className="flex items-center justify-between pt-2">
                      <h3 className="text-[13px] font-semibold text-slate-900">Business</h3>
                      <button type="button" onClick={() => goTo(0)} className="inline-flex items-center gap-1 text-[13px] font-medium text-navy-700 hover:underline">
                        <Pencil className="size-3.5" aria-hidden /> Edit
                      </button>
                    </div>
                    <dl className="divide-y divide-slate-100">
                      <KeyValue label="Legal name" value={fields.legal_name || "—"} />
                      <KeyValue label="Contact" value={[fields.contact_name, fields.contact_email].filter(Boolean).join(" · ") || "—"} />
                      <KeyValue label="State" value={meta?.states.find((s) => s.toUpperCase() === fields.business_state) ?? (fields.business_state || "Not supplied")} />
                      <KeyValue label="PAN" value={fields.pan || "Not supplied"} mono />
                      <KeyValue label="GSTIN" value={fields.gstin || "Not supplied"} mono />
                    </dl>
                  </section>
                  <section className="rounded-lg border border-line px-4 py-2">
                    <div className="flex items-center justify-between pt-2">
                      <h3 className="text-[13px] font-semibold text-slate-900">Banking and PDFs</h3>
                      <button type="button" onClick={() => goTo(1)} className="inline-flex items-center gap-1 text-[13px] font-medium text-navy-700 hover:underline">
                        <Pencil className="size-3.5" aria-hidden /> Edit
                      </button>
                    </div>
                    <dl className="divide-y divide-slate-100">
                      <KeyValue label="Account holder" value={fields.bank_holder || "Not supplied"} />
                      <KeyValue label="Account number" value={fields.account_number ? mask(fields.account_number) : "Not supplied"} mono />
                      <KeyValue label="IFSC" value={fields.ifsc || "Not supplied"} mono />
                      <KeyValue label="GST certificate" value={draft.gst ? `${draft.gst.name} · ${formatBytes(draft.gst.size)}` : "Not attached"} />
                      <KeyValue label="Bank proof" value={draft.bank ? `${draft.bank.name} · ${formatBytes(draft.bank.size)}` : "Not attached"} />
                    </dl>
                  </section>
                </div>

                {missing.length || missingDocs.length ? (
                  <Alert tone="warning" title="Some details are missing">
                    {[missing.length ? `Not entered: ${missing.join(", ")}.` : "", missingDocs.length ? `Not attached: ${missingDocs.join(" and ")}.` : ""]
                      .filter(Boolean)
                      .join(" ")}{" "}
                    You can still submit, and we'll tell you exactly what's still needed.
                  </Alert>
                ) : null}

                {credError ? (
                  <Alert tone="error" title="Couldn't prepare your application">{credError}</Alert>
                ) : draft.creds ? (
                  <CredentialsCard creds={draft.creds} mode="before" />
                ) : (
                  <Spinner label="Preparing your application ID…" />
                )}

                <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-line bg-slate-50 px-4 py-3">
                  <input
                    type="checkbox"
                    checked={ack}
                    onChange={(e) => setAck(e.target.checked)}
                    className="mt-0.5 size-4 rounded border-slate-300 accent-navy-900"
                  />
                  <span className="text-sm text-slate-700">
                    I've saved my application ID and private tracking code, and confirm these details and documents are
                    for my business.
                  </span>
                </label>
              </div>
            ) : null}
          </div>

          <div className="flex items-center justify-between gap-3 border-t border-line bg-slate-50/60 px-5 py-4 sm:px-6">
            {step > 0 ? (
              <Button type="button" variant="secondary" icon={ArrowLeft} onClick={() => goTo(step - 1)}>Back</Button>
            ) : (
              <span />
            )}
            {step < 2 ? (
              <Button type="submit">
                Continue <ArrowRight className="size-4" aria-hidden />
              </Button>
            ) : (
              <Button type="submit" size="lg" icon={Send} disabled={!ack || !draft.creds}>
                Submit for checking
              </Button>
            )}
          </div>
        </form>
      </Card>
      <p className="mt-4 text-center text-xs text-slate-500">Your draft stays in this browser tab only and is cleared when you reload.</p>
    </div>
  );
}
