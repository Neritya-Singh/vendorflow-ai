import { CheckCircle2, Lock, LogOut, Search, ShieldCheck } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { BootErrorBanner } from "../../components/AppShell";
import { clearDocumentCache } from "../../components/admin/DocumentViewer";
import { Alert, Button, Card, Field, Input, Spinner, cx } from "../../components/ui";
import { ApiError, api, setCsrf } from "../../lib/api";
import { useAppState } from "../../state";

interface AdminCtx {
  signOut: () => Promise<void>;
  onUnauthorized: (e: unknown) => boolean;
  /** Short confirmation that survives navigation to the next case. */
  toast: (text: string) => void;
}
const Ctx = createContext<AdminCtx | null>(null);
export const useAdmin = () => {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAdmin outside AdminLayout");
  return ctx;
};

function Login({ onDone, configured }: { onDone: () => void; configured: boolean }) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="flex min-h-dvh flex-col bg-canvas">
      <BootErrorBanner />
      <div className="flex flex-1 items-center justify-center px-4 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-6 flex items-center justify-center gap-2 text-navy-900">
            <ShieldCheck className="size-6" aria-hidden />
            <span className="text-lg font-semibold">VendorFlow staff console</span>
          </div>
          <Card>
            <form
              className="grid gap-5 p-6"
              onSubmit={async (e) => {
                e.preventDefault();
                setBusy(true);
                setError(null);
                try {
                  const res = await api.adminLogin(password);
                  setCsrf(res.csrf_token);
                  setPassword("");
                  onDone();
                } catch (err) {
                  setError(err instanceof ApiError ? err.message : "Sign-in failed.");
                } finally {
                  setBusy(false);
                }
              }}
            >
              <div>
                <h1 className="text-[17px] font-semibold text-slate-900">Reviewer sign-in</h1>
                <p className="mt-1 text-[13px] text-slate-500">For authorised finance and procurement reviewers.</p>
              </div>
              {!configured ? (
                <Alert tone="warning">Admin access isn't configured on this server. Set ADMIN_PASSWORD server-side.</Alert>
              ) : null}
              <Field label="Admin password" htmlFor="admin-password">
                <Input id="admin-password" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required autoFocus />
              </Field>
              {error ? <Alert tone="error">{error}</Alert> : null}
              <Button type="submit" size="lg" icon={Lock} loading={busy} disabled={!password || !configured}>Sign in</Button>
              <p className="text-xs text-slate-500">
                Demo access uses one shared password and a secure session cookie. It is not a production identity system.
              </p>
            </form>
          </Card>
          <p className="mt-5 text-center text-[13px]">
            <Link to="/" className="font-medium text-slate-600 hover:text-navy-800">← Vendor portal</Link>
          </p>
        </div>
      </div>
    </div>
  );
}

const NAV = [
  { to: "/admin/overview", label: "Overview" },
  { to: "/admin", label: "Applications", end: true, also: "/admin/cases" },
  { to: "/admin/activity", label: "Activity" },
];

function TopNav() {
  const { pathname } = useLocation();
  return (
    <nav aria-label="Main" className="flex gap-1 rounded-xl bg-[#F2F4F7] p-1">
      {NAV.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) => {
            const active = isActive || (!!item.also && pathname.startsWith(item.also));
            return cx(
              "rounded-[9px] px-3.5 py-2 text-sm whitespace-nowrap",
              active ? "bg-white font-semibold text-ink shadow-[0_1px_2px_rgba(16,24,40,0.08)]" : "font-medium text-[#344054] hover:text-ink",
            );
          }}
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}

/** Header search: filters the Applications queue by name, ID or GSTIN ("/" focuses it there). */
function HeaderSearch() {
  const navigate = useNavigate();
  const { pathname, search } = useLocation();
  const params = new URLSearchParams(search);
  const onQueue = pathname === "/admin" || pathname === "/admin/";
  const value = onQueue ? params.get("q") ?? "" : "";
  return (
    <div className="flex h-10 min-w-[200px] flex-1 items-center gap-2 rounded-xl border border-[#D0D5DD] bg-white px-3 focus-within:border-navy-600 focus-within:ring-2 focus-within:ring-navy-600/25">
      <Search className="size-4 shrink-0 text-muted" aria-hidden />
      <label htmlFor="admin-search" className="sr-only">Search applications</label>
      <input
        id="admin-search"
        type="search"
        value={value}
        placeholder="Search vendor, GSTIN or ID"
        className="h-full min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-slate-400"
        onChange={(e) => {
          const next = new URLSearchParams(onQueue ? search : "");
          if (e.target.value) next.set("q", e.target.value);
          else next.delete("q");
          const qs = next.toString();
          navigate(`/admin${qs ? `?${qs}` : ""}`, { replace: onQueue });
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape") e.currentTarget.blur();
        }}
      />
      <kbd className="hidden rounded-md border border-line px-1.5 text-[11px] text-muted sm:inline">/</kbd>
    </div>
  );
}

export function AdminLayout() {
  const [status, setStatus] = useState<"loading" | "in" | "out">("loading");
  const [configured, setConfigured] = useState(true);
  const [expired, setExpired] = useState(false);

  const check = useCallback(() => {
    api
      .adminSession()
      .then((s) => {
        setConfigured(s.configured);
        if (s.authenticated && s.csrf_token) {
          setCsrf(s.csrf_token);
          setStatus("in");
        } else {
          setCsrf(null);
          setStatus("out");
        }
      })
      .catch(() => setStatus("out"));
  }, []);

  useEffect(check, [check]);

  const signOut = useCallback(async () => {
    try {
      await api.adminLogout();
      clearDocumentCache();
    } finally {
      setCsrf(null);
      setStatus("out");
    }
  }, []);

  const onUnauthorized = useCallback((e: unknown) => {
    if (e instanceof ApiError && e.status === 401) {
      setCsrf(null);
      setExpired(true);
      setStatus("out");
      return true;
    }
    return false;
  }, []);

  const { meta } = useAppState();
  const workspace = meta?.workspace_name ?? "Zamp AI";
  const [toastText, setToastText] = useState<string | null>(null);
  const toast = useCallback((text: string) => setToastText(text), []);
  useEffect(() => {
    if (!toastText) return;
    const timer = window.setTimeout(() => setToastText(null), 4000);
    return () => window.clearTimeout(timer);
  }, [toastText]);

  if (status === "loading") return <div className="grid min-h-dvh place-items-center"><Spinner label="Checking session…" /></div>;
  if (status === "out")
    return (
      <>
        {expired ? <div role="alert" className="bg-amber-100 px-4 py-2 text-center text-[13px] text-amber-950">Your session ended. Sign in again to continue.</div> : null}
        <Login configured={configured} onDone={() => { setExpired(false); setStatus("in"); }} />
      </>
    );

  return (
    <Ctx.Provider value={{ signOut, onUnauthorized, toast }}>
      <div className="flex min-h-dvh flex-col bg-canvas fit:h-dvh fit:overflow-hidden">
        <BootErrorBanner />
        <div className="flex min-h-0 flex-1 flex-col gap-4 p-3 sm:p-4">
          <header className="flex flex-wrap items-center gap-x-6 gap-y-3 rounded-2xl border border-line bg-white py-2.5 pl-5 pr-4">
            <Link to="/admin" className="flex items-center gap-2.5">
              <span aria-hidden className="grid size-8 place-items-center rounded-[10px] bg-navy-600 text-sm font-bold text-white">V</span>
              <span className="flex flex-col leading-tight">
                <span className="text-[15px] font-bold text-ink">VendorFlow</span>
                <span className="text-[11px] text-muted">{workspace} · Demo workspace</span>
              </span>
            </Link>
            <TopNav />
            <HeaderSearch />
            <div className="flex items-center gap-2">
              <span aria-label="Signed in as reviewer" className="grid size-9 place-items-center rounded-full bg-navy-100 text-[13px] font-semibold text-navy-800">RV</span>
              <Button variant="ghost" size="sm" icon={LogOut} onClick={signOut}>Sign out</Button>
            </div>
          </header>
          <main id="main" className="flex min-h-0 flex-1 flex-col">
            <Outlet />
          </main>
        </div>
        <div aria-live="polite" role="status" className="pointer-events-none fixed inset-x-0 bottom-24 z-50 flex justify-center px-4">
          {toastText ? (
            <p className="flex items-center gap-2 rounded-xl bg-ink px-4 py-2.5 text-sm font-medium text-white shadow-raised">
              <CheckCircle2 className="size-4 text-teal-300" aria-hidden /> {toastText}
            </p>
          ) : null}
        </div>
      </div>
    </Ctx.Provider>
  );
}
