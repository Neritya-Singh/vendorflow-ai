import { CheckCircle2, ExternalLink, Lock, LogOut, ShieldCheck } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { OfflineBanner } from "../../components/AppShell";
import { Alert, Button, Card, Field, Input, Spinner, cx } from "../../components/ui";
import { ApiError, api, setCsrf } from "../../lib/api";

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
    <div className="flex min-h-dvh flex-col bg-slate-100">
      <OfflineBanner />
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

function Tab({ to, children, end }: { to: string; children: ReactNode; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) => cx("rounded-md px-3 py-1.5 text-sm font-medium", isActive ? "bg-white/15 text-white" : "text-navy-100 hover:bg-white/10 hover:text-white")}
    >
      {children}
    </NavLink>
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
      <div className="flex min-h-dvh flex-col bg-slate-50">
        <OfflineBanner />
        <header className="sticky top-0 z-20 bg-navy-900 text-white">
          <div className="mx-auto flex h-14 max-w-[1400px] items-center justify-between gap-4 px-4 sm:px-6">
            <div className="flex items-center gap-5">
              <Link to="/admin" className="flex items-center gap-2 font-semibold">
                <ShieldCheck className="size-5 text-teal-300" aria-hidden />
                <span>VendorFlow <span className="font-normal text-navy-200">Review</span></span>
              </Link>
              <nav aria-label="Staff" className="hidden items-center gap-1 sm:flex">
                <Tab to="/admin" end>Queue</Tab>
                <Tab to="/admin/activity">Decision history</Tab>
              </nav>
            </div>
            <div className="flex items-center gap-2">
              <Link to="/" className="hidden items-center gap-1 rounded-md px-2 py-1.5 text-[13px] text-navy-100 hover:text-white md:inline-flex">
                Vendor portal <ExternalLink className="size-3.5" aria-hidden />
              </Link>
              <button type="button" onClick={signOut} className="inline-flex items-center gap-1.5 rounded-md border border-white/20 px-2.5 py-1.5 text-[13px] font-medium text-white hover:bg-white/10">
                <LogOut className="size-3.5" aria-hidden /> Sign out
              </button>
            </div>
          </div>
          <nav aria-label="Staff (mobile)" className="flex gap-1 px-4 pb-2 sm:hidden">
            <Tab to="/admin" end>Queue</Tab>
            <Tab to="/admin/activity">Decision history</Tab>
          </nav>
        </header>
        <main id="main" className="flex-1">
          <Outlet />
        </main>
        <div aria-live="polite" role="status" className="pointer-events-none fixed inset-x-0 bottom-24 z-50 flex justify-center px-4">
          {toastText ? (
            <p className="flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-medium text-white shadow-lg">
              <CheckCircle2 className="size-4 text-teal-300" aria-hidden /> {toastText}
            </p>
          ) : null}
        </div>
      </div>
    </Ctx.Provider>
  );
}
