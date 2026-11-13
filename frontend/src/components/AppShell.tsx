import { FlaskConical, ShieldCheck } from "lucide-react";
import type { ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
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

function NavItem({ to, children, end }: { to: string; children: ReactNode; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        cx(
          "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
          isActive ? "bg-navy-50 text-navy-900" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900",
        )
      }
    >
      {children}
    </NavLink>
  );
}

export function OfflineBanner() {
  const { health, bootError } = useAppState();
  if (bootError) {
    return (
      <div role="alert" className="bg-red-700 px-4 py-2 text-center text-[13px] font-medium text-white">
        {bootError}
      </div>
    );
  }
  if (health?.mode !== "offline") return null;
  return (
    <div className="flex items-center justify-center gap-2 bg-amber-100 px-4 py-1.5 text-center text-[12.5px] text-amber-950">
      <FlaskConical className="size-3.5 shrink-0" aria-hidden />
      <span>
        <strong>Offline test mode.</strong> Real PDF reading, rules and workflow — with an in-memory database and a
        test extractor instead of Supabase and Gemini. Records vanish when the server restarts.
      </span>
    </div>
  );
}

export function VendorShell({ children }: { children: ReactNode }) {
  const location = useLocation();
  return (
    <div className="flex min-h-dvh flex-col">
      <OfflineBanner />
      <header className="sticky top-0 z-20 border-b border-line bg-white">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
          <Logo />
          <nav aria-label="Vendor" className="flex items-center gap-1">
            <NavItem to="/" end>Home</NavItem>
            <NavItem to="/apply">Apply</NavItem>
            <NavItem to="/track">Track</NavItem>
          </nav>
        </div>
      </header>
      <main id="main" className="flex-1" key={location.pathname}>
        {children}
      </main>
      <footer className="border-t border-line bg-white">
        <div className="mx-auto flex max-w-6xl flex-col gap-2 px-4 py-5 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <p>VendorFlow AI · Case-study prototype for India GST-registered business vendors. Use synthetic data only.</p>
          <Link to="/admin" className="inline-flex items-center gap-1 font-medium text-slate-600 hover:text-navy-800">
            <ShieldCheck className="size-3.5" aria-hidden /> Staff console
          </Link>
        </div>
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
