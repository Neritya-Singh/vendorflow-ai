import { useId } from "react";
import type { VendorFields } from "../lib/types";
import { Field, Input, Select } from "./ui";

export type FieldErrors = Partial<Record<keyof VendorFields, string>>;

interface SectionProps {
  values: VendorFields;
  onChange: (patch: Partial<VendorFields>) => void;
  errors?: FieldErrors;
}

export function BusinessSection({ values, onChange, errors = {}, states }: SectionProps & { states: string[] }) {
  const p = useId();
  return (
    <div className="grid gap-5">
      <Field
        label="Legal business name"
        htmlFor={`${p}-legal`}
        hint="Exactly as printed on your GST certificate — not a trade or brand name."
        error={errors.legal_name}
      >
        <Input
          id={`${p}-legal`}
          autoComplete="organization"
          value={values.legal_name}
          invalid={!!errors.legal_name}
          onChange={(e) => onChange({ legal_name: e.target.value })}
          maxLength={200}
          required
        />
      </Field>
      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Contact email" htmlFor={`${p}-email`} error={errors.contact_email} hint="Used only for this application.">
          <Input
            id={`${p}-email`}
            type="email"
            autoComplete="email"
            value={values.contact_email}
            invalid={!!errors.contact_email}
            onChange={(e) => onChange({ contact_email: e.target.value })}
            maxLength={200}
            required
          />
        </Field>
        <Field label="Contact person" htmlFor={`${p}-contact`} hint="Missing details route the application to review.">
          <Input
            id={`${p}-contact`}
            autoComplete="name"
            value={values.contact_name}
            onChange={(e) => onChange({ contact_name: e.target.value })}
            maxLength={200}
          />
        </Field>
      </div>
      <Field label="Business state / UT" htmlFor={`${p}-state`} hint="The state of your GST registration.">
        <Select id={`${p}-state`} value={values.business_state.toUpperCase()} onChange={(e) => onChange({ business_state: e.target.value })}>
          <option value="">Select state or union territory</option>
          {states.map((s) => (
            <option key={s} value={s.toUpperCase()}>{s}</option>
          ))}
        </Select>
      </Field>
      <div className="grid gap-5 sm:grid-cols-[1fr_1.4fr]">
        <Field label="PAN" htmlFor={`${p}-pan`} hint="10 characters, e.g. ABCDE1234F">
          <Input
            id={`${p}-pan`}
            className="font-mono uppercase tracking-wide"
            value={values.pan}
            onChange={(e) => onChange({ pan: e.target.value.toUpperCase() })}
            maxLength={10}
            autoComplete="off"
            spellCheck={false}
          />
        </Field>
        <Field label="GSTIN" htmlFor={`${p}-gstin`} hint="15 characters; contains your PAN in positions 3–12">
          <Input
            id={`${p}-gstin`}
            className="font-mono uppercase tracking-wide"
            value={values.gstin}
            onChange={(e) => onChange({ gstin: e.target.value.toUpperCase() })}
            maxLength={15}
            autoComplete="off"
            spellCheck={false}
          />
        </Field>
      </div>
    </div>
  );
}

export function BankSection({ values, onChange }: SectionProps) {
  const p = useId();
  return (
    <div className="grid gap-5">
      <Field label="Account holder name" htmlFor={`${p}-holder`} hint="As printed on the bank letter or cancelled cheque. It should match your legal business name.">
        <Input id={`${p}-holder`} value={values.bank_holder} onChange={(e) => onChange({ bank_holder: e.target.value })} maxLength={200} autoComplete="off" />
      </Field>
      <div className="grid gap-5 sm:grid-cols-[1.4fr_1fr]">
        <Field label="Bank account number" htmlFor={`${p}-account`} hint="Leading zeros are kept exactly as typed.">
          <Input
            id={`${p}-account`}
            className="font-mono tracking-wide"
            inputMode="numeric"
            value={values.account_number}
            onChange={(e) => onChange({ account_number: e.target.value })}
            maxLength={34}
            autoComplete="off"
            spellCheck={false}
          />
        </Field>
        <Field label="IFSC" htmlFor={`${p}-ifsc`} hint="11 characters, e.g. HDFC0001234">
          <Input
            id={`${p}-ifsc`}
            className="font-mono uppercase tracking-wide"
            value={values.ifsc}
            onChange={(e) => onChange({ ifsc: e.target.value.toUpperCase() })}
            maxLength={11}
            autoComplete="off"
            spellCheck={false}
          />
        </Field>
      </div>
    </div>
  );
}

/** Non-blocking: the Python rules remain the authority on every field (v1.1 parity). */
export function missingDetails(values: VendorFields): string[] {
  const names: [keyof VendorFields, string][] = [
    ["contact_name", "contact person"],
    ["business_state", "business state"],
    ["pan", "PAN"],
    ["gstin", "GSTIN"],
    ["bank_holder", "account holder"],
    ["account_number", "account number"],
    ["ifsc", "IFSC"],
  ];
  return names.filter(([key]) => !values[key].trim()).map(([, name]) => name);
}
