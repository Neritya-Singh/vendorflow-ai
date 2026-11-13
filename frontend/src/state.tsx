import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./lib/api";
import type { Credentials, Health, Meta, VendorView } from "./lib/types";

/**
 * In-memory only. The draft itself (files, read values, contact) is saved on the
 * server as soon as the first file is uploaded; the browser keeps just the
 * credentials and the current step. Nothing is written to localStorage or
 * sessionStorage, so a reload forgets the tracking code (it can be re-entered).
 */
export interface ApplyState {
  creds: Credentials | null;
  /** 0 documents · 1 details · 2 submit */
  step: number;
  /** True when the credentials belong to an existing server draft to reopen. */
  resume: boolean;
  receipt: { creds: Credentials; view: VendorView } | null;
}

interface AppState {
  health: Health | null;
  meta: Meta | null;
  bootError: string | null;
  apply: ApplyState;
  updateApply: (patch: Partial<ApplyState>) => void;
  resetApply: () => void;
  handoff: Credentials | null;
  setHandoff: (creds: Credentials | null) => void;
}

const FALLBACK_META: Meta = { states: [], max_pdf_bytes: 5 * 1024 * 1024, stages: [] };
const emptyApply = (): ApplyState => ({ creds: null, step: 0, resume: false, receipt: null });
const Ctx = createContext<AppState | null>(null);

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);
  const [apply, setApply] = useState<ApplyState>(emptyApply);
  const [handoff, setHandoff] = useState<Credentials | null>(null);

  useEffect(() => {
    Promise.all([api.health(), api.meta()])
      .then(([h, m]) => {
        setHealth(h);
        setMeta(m);
      })
      .catch((e: Error) => {
        setMeta(FALLBACK_META);
        setBootError(e.message);
      });
  }, []);

  const updateApply = useCallback((patch: Partial<ApplyState>) => setApply((d) => ({ ...d, ...patch })), []);
  const resetApply = useCallback(() => setApply(emptyApply()), []);

  const value = useMemo(
    () => ({ health, meta, bootError, apply, updateApply, resetApply, handoff, setHandoff }),
    [health, meta, bootError, apply, updateApply, resetApply, handoff],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAppState(): AppState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAppState outside provider");
  return ctx;
}
