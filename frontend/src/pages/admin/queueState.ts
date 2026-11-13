import { useCallback, useEffect, useState } from "react";
import { api } from "../../lib/api";
import type { Overview, QueueTab } from "../../lib/types";
import { useAdmin } from "./AdminLayout";

export function useOverview() {
  const { onUnauthorized } = useAdmin();
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(() => {
    setLoading(true);
    api
      .overview()
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e: Error) => {
        if (!onUnauthorized(e)) setError(e.message);
      })
      .finally(() => setLoading(false));
  }, [onUnauthorized]);
  useEffect(load, [load]);
  return { data, error, loading, reload: load };
}

export type Tab = QueueTab | "ALL";
export const TABS: { id: Tab; label: string }[] = [
  { id: "NEEDS_REVIEW", label: "Needs review" },
  { id: "WAITING_ON_VENDOR", label: "Waiting on vendor" },
  { id: "APPROVED", label: "Approved" },
  { id: "REJECTED", label: "Rejected" },
  { id: "ALL", label: "All" },
];
export const TAB_IDS = TABS.map((t) => t.id);
