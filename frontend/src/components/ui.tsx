import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import {
  AlertTriangle, Check, CheckCircle2, Copy, Info, Loader2, XCircle, CircleDashed, type LucideIcon,
} from "lucide-react";
import {
  forwardRef, useId, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode,
  type SelectHTMLAttributes, type TextareaHTMLAttributes,
} from "react";
import type { CheckState, Risk, Status } from "../lib/types";

/** clsx + tailwind-merge: a later class reliably overrides a conflicting default. */
export const cx = (...inputs: ClassValue[]) => twMerge(clsx(inputs));

// ---------------------------------------------------------------- Button
type Variant = "primary" | "secondary" | "ghost" | "danger" | "success";
type Size = "sm" | "md" | "lg";
const variants: Record<Variant, string> = {
  primary: "bg-navy-600 text-white hover:bg-navy-700 active:bg-navy-800 disabled:bg-navy-300",
  secondary:
    "bg-white text-slate-700 border border-[#D0D5DD] hover:bg-slate-50 hover:border-slate-400 disabled:text-slate-400",
  ghost: "text-slate-700 hover:bg-slate-100 disabled:text-slate-400",
  danger: "bg-[#B42318] text-white hover:bg-red-800 disabled:bg-red-300",
  success: "bg-teal-700 text-white hover:bg-teal-800 disabled:bg-teal-300",
};
const sizes: Record<Size, string> = {
  sm: "h-8 px-3 text-[13px] gap-1.5 rounded-[10px]",
  md: "h-10 px-4 text-sm gap-2 rounded-xl",
  lg: "h-11 px-5 text-[15px] gap-2 rounded-xl",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: LucideIcon;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "primary", size = "md", loading, icon: Icon, className, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      className={cx(
        "inline-flex items-center justify-center font-semibold transition-colors disabled:cursor-not-allowed whitespace-nowrap",
        variants[variant],
        sizes[size],
        className,
      )}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : Icon ? <Icon className="size-4" aria-hidden /> : null}
      {children}
    </button>
  );
});

// ---------------------------------------------------------------- Card
export function Card({ className, children, as: Tag = "section", ...rest }: {
  className?: string;
  children: ReactNode;
  as?: "section" | "div" | "article" | "aside";
} & Record<string, unknown>) {
  return (
    <Tag className={cx("rounded-2xl border border-line bg-white", className)} {...rest}>
      {children}
    </Tag>
  );
}

export function CardHeader({ title, description, action, className }: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("flex flex-wrap items-start justify-between gap-3 border-b border-line-soft px-5 py-4", className)}>
      <div className="min-w-0">
        <h2 className="text-[15px] font-semibold text-slate-900">{title}</h2>
        {description ? <p className="mt-0.5 text-[13px] text-slate-500">{description}</p> : null}
      </div>
      {action}
    </div>
  );
}

// ---------------------------------------------------------------- Status
export const STATUS_STYLE: Record<Status, { badge: string; label: string; icon: LucideIcon }> = {
  APPROVED: { badge: "bg-teal-50 text-teal-700 ring-teal-600/20", label: "Approved", icon: CheckCircle2 },
  PENDING: { badge: "bg-amber-50 text-amber-800 ring-amber-600/25", label: "Pending", icon: AlertTriangle },
  REJECTED: { badge: "bg-[#FEF3F2] text-[#B42318] ring-red-600/20", label: "Rejected", icon: XCircle },
};

export function StatusBadge({ status, className }: { status: Status; className?: string }) {
  const style = STATUS_STYLE[status] ?? STATUS_STYLE.PENDING;
  const Icon = style.icon;
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset", style.badge, className)}>
      <Icon className="size-3.5" aria-hidden />
      {style.label}
    </span>
  );
}

/** Reviewer-only risk tag: colour dot plus text. */
export function RiskTag({ risk, suffix = "" }: { risk: Risk; suffix?: string }) {
  if (!risk) return <span className="text-muted">—</span>;
  const style = {
    HIGH: ["bg-[#FEF3F2] text-[#B42318]", "bg-[#D92D20]", "High"],
    MEDIUM: ["bg-[#FFFAEB] text-[#93370D]", "bg-[#DC6803]", "Medium"],
    LOW: ["bg-[#F2F4F7] text-[#344054]", "bg-[#667085]", "Low"],
  }[risk];
  return (
    <span className={cx("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold", style[0])}>
      <span aria-hidden className={cx("size-[7px] rounded-full", style[1])} />
      {style[2]}{suffix}
    </span>
  );
}

/** Who acts next on a pending case, as a coloured dot + text pill. */
export function OwnerPill({ owner, label, className }: { owner: string; label: string; className?: string }) {
  const tone = owner === "VENDOR" ? ["bg-amber-50 text-amber-800", "bg-amber-500"] : owner === "TEAM" ? ["bg-team-50 text-team-700", "bg-team-500"] : ["bg-slate-100 text-slate-700", "bg-slate-400"];
  return (
    <span className={cx("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold", tone[0], className)}>
      <span aria-hidden className={cx("size-2 rounded-full", tone[1])} />
      {label}
    </span>
  );
}

export function CheckIcon({ state }: { state: CheckState }) {
  if (state === "PASS") return <CheckCircle2 className="size-4 shrink-0 text-teal-600" aria-label="Passed" />;
  if (state === "FAIL") return <XCircle className="size-4 shrink-0 text-red-600" aria-label="Needs correction" />;
  return <CircleDashed className="size-4 shrink-0 text-amber-600" aria-label="Not verified" />;
}

export function Pill({ tone = "slate", children, className }: {
  tone?: "slate" | "teal" | "amber" | "red" | "navy";
  children: ReactNode;
  className?: string;
}) {
  const tones = {
    slate: "bg-slate-100 text-slate-700 ring-slate-500/15",
    teal: "bg-teal-50 text-teal-800 ring-teal-600/20",
    amber: "bg-amber-50 text-amber-800 ring-amber-600/25",
    red: "bg-red-50 text-red-800 ring-red-600/20",
    navy: "bg-navy-50 text-navy-800 ring-navy-600/20",
  };
  return (
    <span className={cx("inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset", tones[tone], className)}>
      {children}
    </span>
  );
}

// ---------------------------------------------------------------- Alerts
const alertTones = {
  info: { box: "border-navy-200 bg-navy-50 text-navy-900", icon: Info, iconColor: "text-navy-600" },
  warning: { box: "border-amber-200 bg-amber-50 text-amber-900", icon: AlertTriangle, iconColor: "text-amber-600" },
  error: { box: "border-red-200 bg-red-50 text-red-900", icon: XCircle, iconColor: "text-red-600" },
  success: { box: "border-teal-200 bg-teal-50 text-teal-900", icon: CheckCircle2, iconColor: "text-teal-600" },
};

export function Alert({ tone = "info", title, children, className, action }: {
  tone?: keyof typeof alertTones;
  title?: ReactNode;
  children?: ReactNode;
  className?: string;
  action?: ReactNode;
}) {
  const t = alertTones[tone];
  const Icon = t.icon;
  return (
    <div role={tone === "error" ? "alert" : "status"} className={cx("flex gap-3 rounded-lg border px-4 py-3 text-sm", t.box, className)}>
      <Icon className={cx("mt-0.5 size-4 shrink-0", t.iconColor)} aria-hidden />
      <div className="min-w-0 flex-1">
        {title ? <p className="font-semibold">{title}</p> : null}
        {children ? <div className={cx(title && "mt-1", "leading-relaxed")}>{children}</div> : null}
        {action ? <div className="mt-3">{action}</div> : null}
      </div>
    </div>
  );
}

export function Spinner({ className, label = "Loading" }: { className?: string; label?: string }) {
  return (
    <span role="status" className={cx("inline-flex items-center gap-2 text-sm text-slate-500", className)}>
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {label}
    </span>
  );
}

export function EmptyState({ icon: Icon, title, children }: { icon: LucideIcon; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-12 text-center">
      <div className="grid size-11 place-items-center rounded-full bg-slate-100">
        <Icon className="size-5 text-slate-500" aria-hidden />
      </div>
      <p className="mt-3 text-sm font-semibold text-slate-900">{title}</p>
      {children ? <p className="mt-1 max-w-sm text-[13px] text-slate-500">{children}</p> : null}
    </div>
  );
}

// ---------------------------------------------------------------- Forms
const controlBase =
  "block w-full rounded-xl border bg-white px-3 text-sm text-ink transition-colors placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-navy-600/25 disabled:bg-slate-50 disabled:text-slate-500";

export function Field({ label, hint, error, optional, children, htmlFor }: {
  label: string;
  hint?: ReactNode;
  error?: string | null;
  optional?: boolean;
  children: ReactNode;
  htmlFor: string;
}) {
  return (
    <div>
      <label htmlFor={htmlFor} className="flex items-baseline justify-between text-[13px] font-medium text-slate-800">
        <span>{label}</span>
        {optional ? <span className="text-xs font-normal text-slate-400">Optional</span> : null}
      </label>
      <div className="mt-1.5">{children}</div>
      {error ? (
        <p id={`${htmlFor}-error`} className="mt-1.5 text-xs font-medium text-red-700">{error}</p>
      ) : hint ? (
        <p id={`${htmlFor}-hint`} className="mt-1.5 text-xs text-slate-500">{hint}</p>
      ) : null}
    </div>
  );
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }>(
  function Input({ className, invalid, ...rest }, ref) {
    return (
      <input
        ref={ref}
        aria-invalid={invalid || undefined}
        className={cx(controlBase, "h-10", invalid ? "border-red-400" : "border-[#D0D5DD] focus:border-navy-600", className)}
        {...rest}
      />
    );
  },
);

export function Select({ className, invalid, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean }) {
  return (
    <select
      aria-invalid={invalid || undefined}
      className={cx(controlBase, "h-10 pr-8", invalid ? "border-red-400" : "border-[#D0D5DD] focus:border-navy-600", className)}
      {...rest}
    >
      {children}
    </select>
  );
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cx(controlBase, "min-h-24 py-2 border-[#D0D5DD] focus:border-navy-600", className)} {...rest} />;
}

// ---------------------------------------------------------------- Copy
export function CopyValue({ label, value, secret }: { label: string; value: string; secret?: boolean }) {
  const [copied, setCopied] = useState(false);
  const id = useId();
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  };
  return (
    <div>
      <p id={id} className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <div className="mt-1 flex items-center gap-2 rounded-lg border border-line bg-slate-50 py-1.5 pl-3 pr-1.5">
        <code aria-labelledby={id} className={cx("min-w-0 flex-1 break-all font-mono text-[13px] text-slate-900", secret && "select-all")}>
          {value}
        </code>
        <Button type="button" variant="secondary" size="sm" onClick={copy} icon={copied ? Check : Copy} aria-label={`Copy ${label}`}>
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
    </div>
  );
}

export function KeyValue({ label, value, mono }: { label: string; value: ReactNode; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5 py-2 sm:flex-row sm:items-baseline sm:justify-between sm:gap-4">
      <dt className="shrink-0 whitespace-nowrap text-[13px] text-slate-500">{label}</dt>
      <dd className={cx("text-sm text-slate-900 sm:text-right break-words", mono && "font-mono text-[13px]")}>{value}</dd>
    </div>
  );
}
