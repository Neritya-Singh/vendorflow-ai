import { ChevronRight, Inbox, RefreshCw, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Alert, Button, Card, EmptyState, Input, Pill, RiskTag, Select, Spinner, StatusBadge, cx } from "../../components/ui";
import { api } from "../../lib/api";
import { formatDateTime } from "../../lib/format";
import type { Overview, QueueRow, QueueTab } from "../../lib/types";
import { useAdmin } from "./AdminLayout";

function Metric({ label, value, tone, sub }: { label: string; value: string | number; tone?: "amber" | "teal" | "red"; sub?: string }) {
  return (
    <Card as="div" className="px-4 py-3.5">
      <p className="text-[13px] text-slate-500">{label}</p>
      <p className={cx("mt-1 text-2xl font-semibold tabular", tone === "amber" ? "text-amber-700" : tone === "teal" ? "text-teal-700" : tone === "red" ? "text-red-700" : "text-slate-900")}>
        {value}
      </p>
      {sub ? <p className="mt-0.5 text-xs text-slate-500">{sub}</p> : null}
    </Card>
  );
}

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

type Tab = QueueTab | "ALL";
const TABS: { id: Tab; label: string }[] = [
  { id: "NEEDS_REVIEW", label: "Needs review" },
  { id: "WAITING_ON_VENDOR", label: "Waiting on vendor" },
  { id: "APPROVED", label: "Approved" },
  { id: "REJECTED", label: "Rejected" },
  { id: "ALL", label: "All" },
];
const TAB_IDS = TABS.map((t) => t.id);

function OwnerTag({ row }: { row: QueueRow }) {
  if (row.status !== "PENDING") return <StatusBadge status={row.status} />;
  return <Pill tone={row.owner === "VENDOR" ? "amber" : "navy"}>{row.owner_label}</Pill>;
}

export function AdminQueue() {
  const { data, error, loading, reload } = useOverview();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const requested = params.get("tab") as Tab | null;
  const tab: Tab = requested && TAB_IDS.includes(requested) ? requested : "NEEDS_REVIEW";
  const [search, setSearch] = useState("");
  const setTab = (t: Tab) => setParams(t === "NEEDS_REVIEW" ? {} : { tab: t });

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (data?.queue ?? []).filter(
      (r) => (tab === "ALL" || r.tab === tab) && (!q || `${r.application_id} ${r.business} ${r.gstin}`.toLowerCase().includes(q)),
    );
  }, [data, tab, search]);

  const m = data?.metrics;
  const count = (t: Tab) =>
    !m ? null : t === "NEEDS_REVIEW" ? m.needs_review : t === "WAITING_ON_VENDOR" ? m.waiting_on_vendor : t === "APPROVED" ? m.approved : t === "REJECTED" ? m.rejected : m.total;
  return (
    <div className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">Applications</h1>
          <p className="mt-0.5 text-[13px] text-slate-500">Cases that need you come first, sorted by risk, then by how long they have waited.</p>
        </div>
        <Button variant="secondary" size="sm" icon={RefreshCw} onClick={reload} loading={loading && !!data}>Refresh</Button>
      </div>

      {error ? <Alert tone="error" className="mt-4">{error}</Alert> : null}

      <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Metric label="Needs your review" value={m?.needs_review ?? "—"} tone="amber" />
        <Metric label="Waiting on vendors" value={m?.waiting_on_vendor ?? "—"} />
        <Metric label="Approved" value={m?.approved ?? "—"} tone="teal" />
        <Metric label="Rejected" value={m?.rejected ?? "—"} tone="red" />
        <Metric label="Oldest case waiting on you" value={m ? m.oldest_needs_review ?? "None" : "—"} />
      </div>

      <Card className="mt-5 overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 px-4 py-3">
          <div className="hidden flex-wrap rounded-lg bg-slate-100 p-0.5 sm:flex" role="tablist" aria-label="Filter applications">
            {TABS.map((t) => (
              <button
                key={t.id}
                role="tab"
                aria-selected={tab === t.id}
                onClick={() => setTab(t.id)}
                className={cx("rounded-md px-3 py-1.5 text-[13px] font-medium", tab === t.id ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900")}
              >
                {t.label}
                {count(t.id) != null ? <span className="ml-1.5 text-xs text-slate-400 tabular">{count(t.id)}</span> : null}
              </button>
            ))}
          </div>
          <Select aria-label="Filter applications" className="w-auto sm:hidden" value={tab} onChange={(e) => setTab(e.target.value as Tab)}>
            {TABS.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
          </Select>
          <div className="relative ml-auto w-full sm:w-72">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search name, ID or GSTIN" className="pl-9" aria-label="Search applications" />
          </div>
        </div>

        {loading && !data ? (
          <div className="p-8"><Spinner label="Loading applications…" /></div>
        ) : rows.length === 0 ? (
          <EmptyState icon={Inbox} title={search ? "No matching applications" : tab === "NEEDS_REVIEW" ? "No cases need review" : "Nothing here yet"}>
            {search ? "Try a different name, ID or GSTIN." : tab === "NEEDS_REVIEW" ? "Cases with our team appear here." : "Applications appear here once vendors submit them."}
          </EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-left text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-xs font-medium text-slate-500">
                <tr>
                  <th scope="col" className="px-4 py-2.5">Vendor</th>
                  <th scope="col" className="px-4 py-2.5">Why it's here</th>
                  <th scope="col" className="px-4 py-2.5">Risk</th>
                  <th scope="col" className="px-4 py-2.5">Status</th>
                  <th scope="col" className="px-4 py-2.5 text-right">Waiting</th>
                  <th scope="col" className="w-8"><span className="sr-only">Open</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((r) => (
                  <tr key={r.application_id} className="cursor-pointer hover:bg-slate-50" onClick={() => navigate(`/admin/cases/${r.application_id}`)}>
                    <td className="px-4 py-3">
                      <Link to={`/admin/cases/${r.application_id}`} className="font-medium text-slate-900 hover:text-navy-700" onClick={(e) => e.stopPropagation()}>
                        {r.business || "Unnamed business"}
                      </Link>
                      <p className="font-mono text-xs text-slate-500">{r.application_id}{r.gstin ? ` · ${r.gstin}` : ""}</p>
                    </td>
                    <td className="px-4 py-3 text-slate-700">{r.reason}</td>
                    <td className="px-4 py-3"><RiskTag risk={r.risk} /></td>
                    <td className="px-4 py-3"><OwnerTag row={r} /></td>
                    <td className="px-4 py-3 text-right text-[13px] text-slate-600 tabular" title={formatDateTime(r.waiting_since)}>{r.age}</td>
                    <td className="pr-3"><ChevronRight className="size-4 text-slate-400" aria-hidden /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <p className="mt-3 text-xs text-slate-500">
        Synthetic test data. Figures come from saved records; applications that were never submitted are not counted.
      </p>
    </div>
  );
}

export function AdminActivity() {
  const { data, error, loading } = useOverview();
  const actions = data?.recent_actions ?? [];
  return (
    <div className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6">
      <h1 className="text-xl font-semibold tracking-tight text-slate-900">Decision history</h1>
      <p className="mt-0.5 text-[13px] text-slate-500">Read-only audit of reviewer actions, newest first.</p>
      {error ? <Alert tone="error" className="mt-4">{error}</Alert> : null}
      <Card className="mt-5 overflow-hidden">
        {loading && !data ? (
          <div className="p-8"><Spinner /></div>
        ) : actions.length === 0 ? (
          <EmptyState icon={Inbox} title="No reviewer actions yet">Approvals, rejections and correction requests will appear here.</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-xs font-medium text-slate-500">
                <tr>
                  <th scope="col" className="px-4 py-2.5">When</th>
                  <th scope="col" className="px-4 py-2.5">Application</th>
                  <th scope="col" className="px-4 py-2.5">Action</th>
                  <th scope="col" className="px-4 py-2.5">Reason</th>
                  <th scope="col" className="px-4 py-2.5">Reviewer</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {actions.map((a, i) => (
                  <tr key={`${a.application_id}-${a.created_at}-${i}`}>
                    <td className="whitespace-nowrap px-4 py-3 text-[13px] text-slate-600">{formatDateTime(a.created_at)}</td>
                    <td className="px-4 py-3">
                      <Link to={`/admin/cases/${a.application_id}`} className="font-medium text-slate-900 hover:text-navy-700">{a.business || a.application_id}</Link>
                      <p className="font-mono text-xs text-slate-500">{a.application_id}</p>
                    </td>
                    <td className="px-4 py-3">
                      <Pill tone={a.action === "APPROVE" ? "teal" : a.action === "REJECT" ? "red" : "amber"}>{a.label}</Pill>
                    </td>
                    <td className="max-w-md px-4 py-3 text-slate-700">{a.reason}</td>
                    <td className="px-4 py-3 text-[13px] text-slate-600">{a.actor}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
