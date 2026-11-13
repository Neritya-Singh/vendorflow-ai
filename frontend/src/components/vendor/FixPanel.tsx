import { CheckCircle2, Circle, RefreshCw, RotateCcw, Send } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { api, submitFix } from "../../lib/api";
import { createSaveQueue, type SaveBody } from "../../lib/saveQueue";
import type { Contact, Credentials, DraftFieldKey, FixItem, FixView, Slot, VendorView } from "../../lib/types";
import { useSlotReading } from "../../lib/useSlotReading";
import { useWorkflowRun } from "../../lib/useWorkflowRun";
import { useAppState } from "../../state";
import { ProcessingPanel } from "../ProcessingPanel";
import { Alert, Button, Spinner } from "../ui";
import { Card, ContactInput, FieldRow } from "./DetailsCards";
import { DocumentSlot } from "./DocumentSlot";

function itemDone(item: FixItem, view: FixView): boolean {
  if (item.kind === "document") {
    const file = view.files[item.slot];
    return !!file && !file.on_file && (file.status === "read" || file.status === "unavailable");
  }
  if (item.field === "contact") return !view.contact_errors.email && !view.contact_errors.phone && !!view.contact.email && !!view.contact.phone && !!view.contact.name;
  const field = view.fields.find((f) => f.key === item.field);
  return !!field?.value && !field.error;
}

/**
 * Fix a submitted application (V2_02 §8): only the requested items, each an upload slot
 * (same live reading and wrong-slot warning as the first upload) or a field with its
 * source tag. Re-check reuses every reading already made; no full typed form.
 */
export function FixPanel({ creds, onSaved, prefetched }: {
  creds: Credentials;
  onSaved: (v: VendorView) => void;
  /** Started together with the status request, so the page needn't wait for one then the other. */
  prefetched?: Promise<FixView> | null;
}) {
  const { meta } = useAppState();
  const { state: run, start, reset } = useWorkflowRun();
  const [view, setView] = useState<FixView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [waiting, setWaiting] = useState(false);
  const contactRef = useRef<Contact | null>(null);
  const headingId = useId();
  const fieldsId = useId();
  const maxBytes = meta?.max_pdf_bytes ?? 5 * 1024 * 1024;

  const adopt = useCallback((v: FixView) => {
    setView((current) => (current && current.rev > v.rev ? current : v));
    if (!contactRef.current) contactRef.current = v.contact;
  }, []);
  const { activity, slotErrors, upload, move, retry, busy } = useSlotReading<FixView>({ creds, base: "/api/vendor/fix", maxBytes, adopt });

  useEffect(() => {
    let cancelled = false;
    (prefetched ?? api.openFix(creds)).then((v) => !cancelled && adopt(v)).catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [creds, adopt, prefetched]);

  // Saves go one at a time, in order; those that pile up while one is in flight are merged.
  const queue = useRef(createSaveQueue(async (body: SaveBody) => {
    await api.saveFix(creds, body).then(adopt).catch((e: Error) => setError(e.message));
  }));
  const save = (body: SaveBody) => queue.current.push(body);
  const saveField = (key: DraftFieldKey, value: string) => void save({ changes: { [key]: value } });
  const resetField = (key: DraftFieldKey) => void save({ reset: [key] });
  const saveContact = (patch: Partial<Contact>) => {
    const merged = { ...(contactRef.current ?? { name: "", email: "", phone: "" }), ...patch };
    contactRef.current = merged;
    void save({ contact: merged });
  };

  const recheck = async () => {
    (document.activeElement as HTMLElement | null)?.blur?.();
    await new Promise((r) => setTimeout(r, 0));
    setWaiting(true);
    try {
      await queue.current.idle();
    } finally {
      setWaiting(false);
    }
    const result = await start((cb) => submitFix(creds, cb));
    if (result) onSaved(result);
  };

  if (run.phase !== "idle") {
    return (
      <div className="grid gap-3">
        <ProcessingPanel run={run} title="Re-checking your application" />
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

  if (!view) {
    return error ? <Alert tone="error">{error}</Alert> : <Spinner label="Opening the items to fix…" />;
  }

  const fields = view.fields.filter((f) => view.shown_fields.includes(f.key));
  const onFile = (slot: Slot) => {
    const file = view.files[slot];
    return file?.on_file ? `On file now: ${file.filename}. Upload a new one.` : undefined;
  };
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-4 rounded-2xl border border-line bg-white px-4 py-4 sm:rounded-[20px] sm:px-6 sm:py-5" data-fix-panel>
      <div className="flex flex-col gap-1">
        <h2 id={headingId} className="text-base font-semibold text-ink sm:text-lg">Fix {view.items.length === 1 ? "this item" : "these items"}</h2>
        <p className="text-[13px] text-muted">Only what's listed here. Everything else stays as you submitted it, and your application ID stays the same.</p>
      </div>
      <ul className="flex flex-col gap-1.5" aria-label="Items to fix">
        {view.items.map((item) => {
          const done = itemDone(item, view);
          return (
            <li key={item.id} className="flex items-start gap-2 text-sm text-ink" data-item={item.id} data-done={done}>
              {done ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-teal-700" aria-label="Done" /> : <Circle className="mt-0.5 size-4 shrink-0 text-[#98A2B3]" aria-label="To do" />}
              {item.text}
            </li>
          );
        })}
      </ul>

      {view.show_slots.map((slot) => {
        const file = view.files[slot];
        return (
          <DocumentSlot
            key={slot}
            slot={slot}
            file={file?.on_file ? null : file}
            activity={activity[slot] ?? null}
            error={slotErrors[slot] ?? null}
            maxBytes={maxBytes}
            onFile={(f) => void upload(slot, f)}
            onMove={() => void move(slot, view)}
            onRetry={retry(slot)}
            note={onFile(slot)}
          />
        );
      })}

      {fields.length ? (
        <Card id={fieldsId} title="Details to check" source="Correct the value if needed, then re-check">
          <dl>
            {fields.map((field) => (
              <FieldRow key={field.key} field={field} editing states={meta?.states ?? []} onSave={saveField} onReset={resetField} />
            ))}
          </dl>
        </Card>
      ) : null}

      {view.show_contact ? (
        <div className="flex flex-col gap-3 rounded-2xl border border-line px-4 py-3.5">
          <h3 className="text-[15px] font-semibold text-ink">Your contact</h3>
          <ContactInput label="Contact name" type="text" autoComplete="name" value={view.contact.name} onCommit={(name) => saveContact({ name })} />
          <ContactInput label="Phone" type="tel" autoComplete="tel" value={view.contact.phone} error={view.contact_errors.phone} onCommit={(phone) => saveContact({ phone })} />
          <ContactInput label="Email" type="email" autoComplete="email" value={view.contact.email} error={view.contact_errors.email} onCommit={(email) => saveContact({ email })} />
        </div>
      ) : null}

      {error ? <Alert tone="error">{error}</Alert> : null}
      <div className="flex flex-col gap-3 border-t border-line-soft pt-4 sm:flex-row sm:items-center sm:justify-between">
        <span className="text-[13px] text-muted" aria-live="polite">
          {busy ? "Reading your document…" : waiting ? "Saving your changes…" : view.ready ? "Ready to check again." : view.blockers[0]}
        </span>
        <Button size="lg" icon={Send} disabled={!view.ready || busy} loading={waiting} onClick={() => void recheck()}>Re-check</Button>
      </div>
    </section>
  );
}
