import { Check, Lock, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { useAppState } from "../state";
import { cx } from "./ui";

export function Logo({ to = "/" }: { to?: string }) {
  return (
    <Link to={to} className="flex items-center gap-2.5 rounded-md" aria-label="VendorFlow AI home">
      <svg viewBox="0 0 32 32" className="size-8" aria-hidden>
        <rect width="32" height="32" rx="8" fill="#13294B" />
        <path d="M8 10.5l5.2 11 3-6.4M16.3 15l3 6.5L24.5 10.5" fill="none" stroke="#5EEAD4" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="leading-tight">
        <span className="block text-[15px] font-semibold tracking-tight text-slate-900">VendorFlow AI</span>
        <span className="block text-[11px] font-medium text-slate-500">Vendor onboarding</span>
      </span>
    </Link>
  );
}

/** Shown only when the app could not start (e.g. the API is unreachable). */
export function BootErrorBanner() {
  const { bootError } = useAppState();
  if (!bootError) return null;
  return (
    <div role="alert" className="bg-red-700 px-4 py-2 text-center text-[13px] font-medium text-white">
      {bootError}
    </div>
  );
}

export const VENDOR_STEPS = ["Documents", "Details", "Submit"] as const;

function StepPills({ step }: { step: number }) {
  return (
    <>
      <ol aria-label="Progress" className="hidden items-center gap-2.5 text-sm md:flex">
        {VENDOR_STEPS.map((label, i) => {
          const done = i < step;
          const current = i === step;
          return (
            <li key={label} className="flex items-center gap-2.5">
              {i > 0 ? <span aria-hidden className={cx("h-0.5 w-7", done || current ? "bg-[#ABEFC6]" : "bg-[#D0D5DD]")} /> : null}
              <span
                aria-current={current ? "step" : undefined}
                className={cx(
                  "flex items-center gap-2 rounded-full py-1.5",
                  current ? "bg-navy-50 px-3.5 font-semibold text-navy-800" : done ? "px-2.5 font-medium text-teal-700" : "px-2.5 text-muted",
                )}
              >
                <span
                  aria-hidden
                  className={cx(
                    "grid size-[22px] place-items-center rounded-full text-xs",
                    current ? "bg-navy-600 text-white" : done ? "bg-teal-100 text-teal-700" : "border-[1.5px] border-[#98A2B3]",
                  )}
                >
                  {done ? <Check className="size-3" strokeWidth={3} /> : i + 1}
                </span>
                {label}
                <span className="sr-only">{done ? " (done)" : current ? " (current step)" : ""}</span>
              </span>
            </li>
          );
        })}
      </ol>
      <div className="md:hidden">
        <p className="text-right text-xs text-muted">Step {Math.min(step, 2) + 1} of 3 · {VENDOR_STEPS[Math.min(step, 2)]}</p>
      </div>
    </>
  );
}

function StepBar({ step }: { step: number }) {
  return (
    <div aria-hidden className="grid grid-cols-3 gap-1.5 md:hidden">
      {VENDOR_STEPS.map((label, i) => (
        <div key={label} className={cx("h-[5px] rounded-full", i < step ? "bg-teal-600" : i === step ? "bg-navy-600" : "bg-line")} />
      ))}
    </div>
  );
}

/**
 * Co-branded vendor frame (V2_03 §4.1): buyer workspace header, step pills,
 * "Powered by VendorFlow". On a laptop (≥1280×760) the page fits the screen and
 * cards scroll inside; smaller windows and zoom fall back to normal scrolling.
 * `fit={false}` lets a page scroll at every size (the phone details step).
 */
export function VendorFrame({ step, children, fit = true }: { step?: number; children: ReactNode; fit?: boolean }) {
  const { meta } = useAppState();
  const buyer = meta?.workspace_name || "Zamp AI";
  return (
    <div className={cx("flex min-h-dvh flex-col gap-3 bg-canvas p-3 sm:gap-4 sm:p-4", fit && "fit:h-dvh fit:overflow-hidden")}>
      <BootErrorBanner />
      <header className="flex flex-col gap-2.5 rounded-2xl border border-line bg-white px-4 py-3 md:flex-row md:items-center md:justify-between md:gap-6 md:px-6 md:py-3.5">
        <div className="flex items-center justify-between gap-3">
          <Link to="/" className="flex items-center gap-3 rounded-md" aria-label={`${buyer} supplier registration home`}>
            <span aria-hidden className="grid size-[30px] place-items-center rounded-[9px] bg-ink text-[13px] font-bold text-white md:size-9 md:rounded-[10px] md:text-[15px]">
              {buyer.slice(0, 1).toUpperCase()}
            </span>
            <span className="flex flex-col leading-tight">
              <span className="text-sm font-semibold text-ink md:text-[15px]">{buyer}</span>
              <span className="hidden text-xs text-muted md:block">Supplier registration · Demo workspace</span>
            </span>
          </Link>
          {step !== undefined ? <div className="md:hidden"><StepPills step={step} /></div> : <span className="text-xs text-muted md:hidden">Demo workspace</span>}
        </div>
        {step !== undefined ? <StepBar step={step} /> : null}
        {step !== undefined ? <div className="hidden md:block"><StepPills step={step} /></div> : null}
        <span className="hidden text-xs text-muted md:block">Powered by VendorFlow</span>
      </header>
      <main id="main" className="flex min-h-0 flex-1 flex-col">
        {children}
      </main>
      <footer className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 px-1 text-xs text-muted">
        <p className="flex items-center gap-1.5">
          <Lock className="size-3.5 shrink-0" aria-hidden />
          Your documents are stored privately and seen only by {buyer}'s finance team.
        </p>
        <p className="flex items-center gap-3">
          <span>Synthetic test data only</span>
          <Link to="/admin" className="inline-flex items-center gap-1 font-medium text-[#344054] hover:text-navy-800">
            <ShieldCheck className="size-3.5" aria-hidden /> Staff console
          </Link>
        </p>
      </footer>
    </div>
  );
}

export function PageHeader({ eyebrow, title, description, action }: {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div className="min-w-0">
        {eyebrow ? <p className="text-xs font-semibold uppercase tracking-wider text-navy-600">{eyebrow}</p> : null}
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-slate-900 sm:text-[28px]">{title}</h1>
        {description ? <p className="mt-1.5 max-w-2xl text-[15px] text-slate-600">{description}</p> : null}
      </div>
      {action}
    </div>
  );
}
