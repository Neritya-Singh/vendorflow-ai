import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./lib/api";
import { EMPTY_FIELDS, type Credentials, type Health, type Meta, type VendorFields, type VendorView } from "./lib/types";

/**
 * In-memory only. Drafts, files and tracking credentials are never written to
 * localStorage/sessionStorage; a page reload intentionally clears them.
 */
interface Draft {
  fields: VendorFields;
  gst: File | null;
  bank: File | null;
  step: number;
  creds: Credentials | null;
  receipt: { creds: Credentials; view: VendorView } | null;
}

interface AppState {
  health: Health | null;
  meta: Meta | null;
  bootError: string | null;
  draft: Draft;
  updateDraft: (patch: Partial<Draft>) => void;
  resetDraft: () => void;
  handoff: Credentials | null;
  setHandoff: (creds: Credentials | null) => void;
}

const FALLBACK_META: Meta = { states: [], max_pdf_bytes: 5 * 1024 * 1024, stages: [] };
const emptyDraft = (): Draft => ({ fields: { ...EMPTY_FIELDS }, gst: null, bank: null, step: 0, creds: null, receipt: null });
const Ctx = createContext<AppState | null>(null);

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<Health | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);
  const [draft, setDraft] = useState<Draft>(emptyDraft);
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

  const updateDraft = useCallback((patch: Partial<Draft>) => setDraft((d) => ({ ...d, ...patch })), []);
  const resetDraft = useCallback(() => setDraft(emptyDraft()), []);

  const value = useMemo(
    () => ({ health, meta, bootError, draft, updateDraft, resetDraft, handoff, setHandoff }),
    [health, meta, bootError, draft, updateDraft, resetDraft, handoff],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAppState(): AppState {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAppState outside provider");
  return ctx;
}
