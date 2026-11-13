import { Eye, EyeOff, FileText, LogOut, RefreshCw, RotateCcw, Search } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { PageHeader, VendorFrame } from "../components/AppShell";
import { DecisionCard, SavedStages, ScopeNote, VendorTimeline } from "../components/Outcome";
import { MessageLog } from "../components/MessageLog";
import { ProcessingPanel } from "../components/ProcessingPanel";
import { FixPanel } from "../components/vendor/FixPanel";
import { Alert, Button, Card, CardHeader, Field, Input, Spinner } from "../components/ui";
import { ApiError, api } from "../lib/api";
import { EMPTY_FIELDS, type Credentials, type VendorFields, type VendorView } from "../lib/types";
import { useWorkflowRun } from "../lib/useWorkflowRun";
import { useAppState } from "../state";

function toFields(submitted: Partial<VendorFields>): VendorFields {
  const out = { ...EMPTY_FIELDS };
  for (const key of Object.keys(EMPTY_FIELDS) as (keyof VendorFields)[]) out[key] = String(submitted[key] ?? "");
  out.business_state = out.business_state.toUpperCase();
  return out;
}

function SignIn({ onFound, initial }: { onFound: (c: Credentials, v: VendorView) => void; initial: Credentials | null }) {
  const [id, setId] = useState(initial?.application_id ?? "");
  const [code, setCode] = useState(initial?.tracking_code ?? "");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const lookup = useCallback(
    async (creds: Credentials) => {
      setBusy(true);
      setError(null);
      try {
        onFound(creds, await api.track(creds));
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");
      } finally {
        setBusy(false);
      }
    },
    [onFound],
  );

  return (
    <Card className="mx-auto max-w-md">
      <form
        className="grid gap-5 p-6"
        onSubmit={(e) => {
          e.preventDefault();
          void lookup({ application_id: id.trim().toUpperCase(), tracking_code: code.trim() });
        }}
      >
        <Field label="Application ID" htmlFor="track-id" hint="Starts with VF-, shown on your receipt.">
          <Input id="track-id" value={id} onChange={(e) => setId(e.target.value)} placeholder="VF-XXXXXXXXXXXX" className="font-mono uppercase" autoComplete="off" spellCheck={false} required />
        </Field>
        <Field label="Private tracking code" htmlFor="track-code">
          <div className="relative">
            <Input id="track-code" type={show ? "text" : "password"} value={code} onChange={(e) => setCode(e.target.value)} className="pr-10 font-mono" autoComplete="off" spellCheck={false} required />
            <button
              type="button"
              onClick={() => setShow((s) => !s)}
              className="absolute inset-y-0 right-0 grid w-10 place-items-center rounded-r-lg text-slate-500 hover:text-slate-800"
              aria-label={show ? "Hide tracking code" : "Show tracking code"}
            >
              {show ? <EyeOff className="size-4" aria-hidden /> : <Eye className="size-4" aria-hidden />}
            </button>
          </div>
        </Field>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <Button type="submit" size="lg" icon={Search} loading={busy} disabled={!id.trim() || !code.trim()}>
          Find application
        </Button>
        <p className="text-center text-xs text-slate-500">
          Lost your code? It can't be recovered — <Link to="/apply" className="font-medium text-navy-700 hover:underline">start a new application</Link>.
        </p>
      </form>
    </Card>
  );
}

/** After a reading outage the same details and documents can be checked again. */
function RetryCard({ view, creds, onSaved }: { view: VendorView; creds: Credentials; onSaved: (v: VendorView) => void }) {
  const { state: run, start, reset } = useWorkflowRun();
  const retry = async () => {
    const result = await start({
      creds,
      fields: toFields(view.submitted),
      gst: null,
      bank: null,
      expected: { revision: view.revision ?? 0, latest_run_id: view.latest_run_id ?? "" },
    });
    if (result) onSaved(result);
  };
  if (run.phase !== "idle") {
    return (
      <div className="grid gap-3">
        <ProcessingPanel run={run} title="Retrying the document check" />
        {run.phase === "failed" || run.phase === "interrupted" ? (
          <div className="flex gap-2">
            <Button variant="secondary" icon={RotateCcw} onClick={reset}>Back</Button>
            {run.error?.status === 409 ? (
              <Button variant="secondary" icon={RefreshCw} onClick={() => window.location.reload()}>Reload page</Button>
            ) : null}
          </div>
        ) : null}
      </div>
    );
  }
  return (
    <Card className="border-amber-200">
      <div className="flex flex-wrap items-center justify-between gap-4 px-5 py-4">
        <div>
          <h2 className="text-[15px] font-semibold text-slate-900">Try the check again</h2>
          <p className="mt-0.5 text-[13px] text-slate-600">Runs the same details and documents again. Nothing needs to change.</p>
        </div>
        <Button icon={RotateCcw} onClick={() => void retry()}>Retry check now</Button>
      </div>
    </Card>
  );
}

export function TrackPage() {
  const { handoff, setHandoff, updateApply } = useAppState();
  const navigate = useNavigate();
  const [creds, setCreds] = useState<Credentials | null>(null);
  const [view, setView] = useState<VendorView | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [autoError, setAutoError] = useState<string | null>(null);
  const [autoLoading, setAutoLoading] = useState(false);
  const [formKey, setFormKey] = useState(0);

  // A receipt can hand its credentials to this page in memory (never via URL or storage).
  useEffect(() => {
    if (!handoff) return;
    const c = handoff;
    setHandoff(null);
    setAutoLoading(true);
    api
      .track(c)
      .then((v) => {
        setCreds(c);
        setView(v);
      })
      .catch((e: Error) => setAutoError(e.message))
      .finally(() => setAutoLoading(false));
  }, [handoff, setHandoff]);

  // A draft (not submitted yet) continues in the upload-first flow.
  useEffect(() => {
    if (view && creds && view.owner === "DRAFT") {
      updateApply({ creds, step: 0, resume: true, receipt: null });
      navigate("/apply");
    }
  }, [view, creds, updateApply, navigate]);

  const signOut = () => {
    setCreds(null);
    setView(null);
    setNotice(null);
  };

  if (!view || !creds) {
    return (
      <VendorFrame>
        <div className="mx-auto w-full max-w-md py-4 sm:py-8">
        <PageHeader title="Open your application" description="Enter the application ID and private tracking code you saved." />
        <div className="mt-6">
          {autoLoading ? (
            <Spinner label="Opening your application…" />
          ) : (
            <>
              {autoError ? <Alert tone="error" className="mx-auto mb-4 max-w-md">{autoError}</Alert> : null}
              <SignIn onFound={(c, v) => { setCreds(c); setView(v); }} initial={null} />
            </>
          )}
        </div>
        </div>
      </VendorFrame>
    );
  }

  const onSaved = (v: VendorView) => {
    setView(v);
    setFormKey((k) => k + 1);
    setNotice("Your update was checked and saved. The latest decision is shown below.");
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  if (view.owner === "DRAFT") return <VendorFrame><Spinner label="Opening your application…" /></VendorFrame>;

  return (
    <VendorFrame>
      <div className="flex min-h-0 flex-1 flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3 px-1 sm:px-2">
        <div className="min-w-0">
          <h1 className="truncate text-[22px] font-bold tracking-[-0.01em] text-ink sm:text-[26px]">{view.submitted.legal_name || "Your application"}</h1>
          <p className="font-mono text-[13px] text-muted">{view.application_id}</p>
        </div>
        <Button variant="secondary" icon={LogOut} onClick={signOut}>Sign out</Button>
      </div>
      <div className="grid min-h-0 flex-1 gap-4 fit:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)] lg:grid-cols-[1.5fr_1fr]">
          <div className="flex min-h-0 flex-col gap-4 fit:overflow-y-auto [&>*]:shrink-0">
            {notice ? <Alert tone="success">{notice}</Alert> : null}
            <DecisionCard view={view} />
            {view.editable ? (
              <FixPanel key={formKey} creds={creds} onSaved={onSaved} />
            ) : view.retry_available ? (
              <RetryCard key={formKey} view={view} creds={creds} onSaved={onSaved} />
            ) : null}
            {view.stages.some((s) => s.state !== "NOT_RUN") ? <SavedStages view={view} /> : null}
          </div>
          <div className="flex min-h-0 flex-col gap-4 fit:overflow-y-auto [&>*]:shrink-0">
            <MessageLog messages={view.messages} />
            {view.timeline.length ? <VendorTimeline items={view.timeline} /> : null}
            {view.documents.length ? (
              <Card>
                <CardHeader title="Documents on file" description="Used in the latest saved check" />
                <ul className="divide-y divide-slate-100">
                  {view.documents.map((d) => (
                    <li key={d.doc_type} className="flex items-center gap-3 px-5 py-3 text-sm">
                      <FileText className="size-4 text-slate-400" aria-hidden />
                      <span className="flex-1 text-slate-800">{d.doc_type === "GST" ? "GST certificate" : "Bank proof"}</span>
                      <span className="text-xs text-slate-500">Version {d.version}</span>
                    </li>
                  ))}
                </ul>
              </Card>
            ) : null}
            {view.status !== "PENDING" ? (
              <Alert tone="info" title="Final decision">This application can no longer be changed.</Alert>
            ) : null}
            <ScopeNote />
          </div>
      </div>
      </div>
    </VendorFrame>
  );
}
