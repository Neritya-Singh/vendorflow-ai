import { CircleAlert, Pencil, Undo2 } from "lucide-react";
import { useEffect, useId, useState, type ReactNode } from "react";
import type { Contact, DraftField, DraftFieldKey, DraftView, Slot } from "../../lib/types";
import { cx } from "../ui";

const DOC_WORD: Record<Slot, string> = { GST: "GST certificate", BANK: "bank document" };
const PLACEHOLDER: Partial<Record<DraftFieldKey, string>> = {
  gstin: "e.g. 27ABCDE1234F1Z0",
  ifsc: "e.g. SBIN0001234",
  account_number: "Type the full account number",
};

const inputClass = (warn: boolean, invalid: boolean) =>
  cx(
    "w-full rounded-[10px] border bg-white px-3 text-base text-ink outline-none min-h-12 sm:min-h-10 sm:text-[15px]",
    "focus:border-navy-500 focus:ring-2 focus:ring-navy-100",
    invalid ? "border-[#F04438]" : warn ? "border-[1.5px] border-[#F79009] bg-[#FFFCF5]" : "border-[#D0D5DD]",
  );

function Card({ id, title, source, action, children }: {
  id: string;
  title: string;
  source?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="flex min-h-0 flex-col gap-2 rounded-2xl border border-line bg-white px-4 py-3.5 sm:rounded-[20px] sm:px-6 sm:py-5">
      <div className="flex items-center justify-between gap-3">
        <div className="flex flex-col">
          <h2 id={id} className="text-[15px] font-semibold text-ink sm:text-base">{title}</h2>
          {source ? <span className="text-xs text-muted">{source}</span> : null}
        </div>
        {action}
      </div>
      <div className="min-h-0 fit:overflow-y-auto">{children}</div>
    </section>
  );
}

function FieldRow({ field, editing, states, onSave, onReset }: {
  field: DraftField;
  editing: boolean;
  states: string[];
  onSave: (key: DraftFieldKey, value: string) => void;
  onReset: (key: DraftFieldKey) => void;
}) {
  const id = useId();
  const masked = field.key === "account_number";
  const needsInput = editing || field.status === "missing" || field.status === "unread" || !!field.error;
  const [value, setValue] = useState(masked ? "" : field.value);
  useEffect(() => setValue(masked ? "" : field.value), [field.value, masked]);
  const note =
    field.status === "missing"
      ? `Not found on your ${DOC_WORD[field.document]}. Type it, or upload a clearer copy.`
      : field.status === "unread"
        ? `We couldn't read your ${DOC_WORD[field.document]} just now. Type it from your document.`
        : null;
  const commit = () => {
    const next = value.trim();
    if (masked ? next !== "" : next !== field.value) onSave(field.key, next);
  };

  const tag =
    field.status === "edited" ? (
      <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-[#93370D]" data-tag="changed">
        <span className="rounded-full bg-[#FEF0C7] px-2 py-0.5 font-semibold">Changed by you</span>
        Our team will compare it with your document{field.document_value ? ` (it shows ${field.document_value})` : ""}.
        <button type="button" onClick={() => onReset(field.key)} className="inline-flex items-center gap-1 font-semibold text-navy-700 hover:underline">
          <Undo2 className="size-3" aria-hidden /> Use document value
        </button>
      </p>
    ) : field.status === "vendor" ? (
      <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-[#93370D]" data-tag="entered">
        <span className="rounded-full bg-[#FEF0C7] px-2 py-0.5 font-semibold">Entered by you</span>
        Not on your document. Our team will check it.
      </p>
    ) : null;

  if (!needsInput) {
    return (
      <div className="border-t border-[#F2F4F7] py-2.5 sm:py-3" data-field={field.key}>
        <dt className="text-xs text-muted">{field.label}</dt>
        <dd className={cx("mt-0.5 text-[15px] font-medium text-ink", ["gstin", "ifsc", "account_number"].includes(field.key) && "tabular tracking-[0.02em]")}>
          {field.value || "—"}
        </dd>
        {tag}
      </div>
    );
  }

  const control =
    field.key === "business_state" && states.length ? (
      <select
        id={id}
        className={inputClass(!!note, !!field.error)}
        value={states.find((s) => s.toUpperCase() === value.toUpperCase()) ?? ""}
        onChange={(e) => {
          setValue(e.target.value);
          if (e.target.value !== field.value) onSave(field.key, e.target.value);
        }}
        aria-describedby={`${id}-note`}
        aria-invalid={!!field.error}
      >
        <option value="">Choose a state or UT</option>
        {states.map((s) => <option key={s} value={s}>{s}</option>)}
      </select>
    ) : (
      <input
        id={id}
        className={cx(inputClass(!!note, !!field.error), ["gstin", "ifsc"].includes(field.key) && "uppercase tabular")}
        value={value}
        inputMode={masked ? "numeric" : undefined}
        autoComplete="off"
        spellCheck={false}
        placeholder={PLACEHOLDER[field.key]}
        onChange={(e) => setValue(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && commit()}
        aria-describedby={`${id}-note`}
        aria-invalid={!!field.error}
      />
    );
  return (
    <div className="flex flex-col gap-1.5 border-t border-[#F2F4F7] py-2.5 sm:py-3" data-field={field.key}>
      <label htmlFor={id} className="text-xs text-muted">{field.label}</label>
      {control}
      <div id={`${id}-note`}>
        {masked && field.value ? <p className="text-xs text-muted">Current: {field.value}</p> : null}
        {field.error ? <p className="text-xs font-medium text-[#B42318]">{field.error}</p> : null}
        {note && !field.error ? (
          <p className="flex items-start gap-1.5 text-xs text-[#93370D]"><CircleAlert className="mt-px size-3.5 shrink-0 text-[#B54708]" aria-hidden />{note}</p>
        ) : null}
      </div>
      {tag}
    </div>
  );
}

function DocCard({ slot, title, view, states, onSave, onReset, extra }: {
  slot: Slot;
  title: string;
  view: DraftView;
  states: string[];
  onSave: (key: DraftFieldKey, value: string) => void;
  onReset: (key: DraftFieldKey) => void;
  extra?: (key: DraftFieldKey) => ReactNode;
}) {
  const [editing, setEditing] = useState(false);
  const id = useId();
  const file = view.files[slot];
  const read = file?.status === "read";
  const fields = view.fields.filter((f) => f.document === slot);
  return (
    <Card
      id={id}
      title={title}
      source={read ? `From your ${DOC_WORD[slot]}` : `Type these from your ${DOC_WORD[slot]}`}
      action={
        read ? (
          <button
            type="button"
            onClick={() => setEditing((e) => !e)}
            aria-pressed={editing}
            aria-label={`${editing ? "Done editing" : "Edit"} ${title.toLowerCase()}`}
            className="inline-flex min-h-11 items-center gap-1.5 rounded-[10px] bg-navy-50 px-3.5 text-[13px] font-semibold text-navy-600 hover:bg-navy-100 sm:min-h-9"
          >
            {editing ? "Done" : <><Pencil className="size-3.5" aria-hidden />Edit</>}
          </button>
        ) : null
      }
    >
      <dl>
        {fields.map((field) => (
          <div key={field.key}>
            <FieldRow field={field} editing={editing} states={states} onSave={onSave} onReset={onReset} />
            {extra?.(field.key)}
          </div>
        ))}
      </dl>
    </Card>
  );
}

function ContactInput({ label, type, value, error, autoComplete, onCommit }: {
  label: string;
  type: string;
  value: string;
  error?: string;
  autoComplete: string;
  onCommit: (value: string) => void;
}) {
  const id = useId();
  const [local, setLocal] = useState(value);
  useEffect(() => setLocal(value), [value]);
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-[13px] font-medium text-[#344054]">{label}</label>
      <input
        id={id}
        type={type}
        value={local}
        autoComplete={autoComplete}
        className={inputClass(false, !!error)}
        onChange={(e) => setLocal(e.target.value)}
        onBlur={() => local.trim() !== value && onCommit(local.trim())}
        aria-invalid={!!error}
        aria-describedby={error ? `${id}-err` : undefined}
      />
      {error ? <p id={`${id}-err`} className="text-xs font-medium text-[#B42318]">{error}</p> : null}
    </div>
  );
}

export function DetailsCards({ view, states, onSave, onReset, onContact }: {
  view: DraftView;
  states: string[];
  onSave: (key: DraftFieldKey, value: string) => void;
  onReset: (key: DraftFieldKey) => void;
  onContact: (patch: Partial<Contact>) => void;
}) {
  const contactId = useId();
  const contact = view.contact;
  const pan = (key: DraftFieldKey) =>
    key === "gstin" ? (
      <div className="border-t border-[#F2F4F7] py-2.5 sm:py-3" data-field="pan">
        <dt className="text-xs text-muted">PAN <span className="text-[#98A2B3]">· taken from GSTIN</span></dt>
        <dd className="mt-0.5 text-[15px] font-medium text-ink tabular tracking-[0.02em]">{view.pan.value || "—"}</dd>
      </div>
    ) : key === "business_state" && view.address ? (
      <div className="border-t border-[#F2F4F7] py-2.5 sm:py-3">
        <dt className="text-xs text-muted">Address</dt>
        <dd className="mt-0.5 text-[15px] font-medium text-ink">{view.address}</dd>
      </div>
    ) : null;
  return (
    <>
      <DocCard slot="GST" title="Business" view={view} states={states} onSave={onSave} onReset={onReset} extra={pan} />
      <DocCard slot="BANK" title="Bank account" view={view} states={states} onSave={onSave} onReset={onReset} />
      <Card id={contactId} title="Your contact" source="Who we should talk to">
        <div className="flex flex-col gap-3 pt-1">
          <ContactInput label="Contact name" type="text" autoComplete="name" value={contact.name}
            onCommit={(name) => onContact({ name })} />
          <ContactInput label="Phone" type="tel" autoComplete="tel" value={contact.phone} error={view.contact_errors.phone}
            onCommit={(phone) => onContact({ phone })} />
          <ContactInput label="Email" type="email" autoComplete="email" value={contact.email} error={view.contact_errors.email}
            onCommit={(email) => onContact({ email })} />
        </div>
      </Card>
    </>
  );
}
