import { ChevronRight, Inbox, RefreshCw, Search } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Alert, Button, Card, EmptyState, Input, Pill, Select, Spinner, StatusBadge, cx } from "../../components/ui";
import { api } from "../../lib/api";
import { formatDateTime, formatDuration } from "../../lib/format";
import type { Overview, Status } from "../../lib/types";
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

const OWNER_TONE = { Vendor: "navy", Reviewer: "amber", "Technical retry": "slate", Complete: "slate" } as const;
const OWNER_LABEL = { Vendor: "Waiting on vendor", Reviewer: "Needs reviewer", "Technical retry": "Technical retry", Complete: "Complete" } as const;

export function AdminQueue() {
  const { data, error, loading, reload } = useOverview();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const status = (params.get("status") ?? "PENDING") as Status | "ALL";
  const [search, setSearch] = useState("");

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (data?.queue ?? []).filter(
      (r) => (status === "ALL" || r.status === status) && (!q || `${r.application_id} ${r.business}`.toLowerCase().includes(q)),
    );
  }, [data, status, search]);

  const m = data?.metrics;
  return (
    <div className="mx-auto max-w-[1400px] px-4 py-6 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">Review queue</h1>
          <p className="mt-0.5 text-[13px] text-slate-500">Exceptions first, oldest first. Open a case to see evidence and decide.</p>
        </div>
        <Button variant="secondary" size="sm" icon={RefreshCw} onClick={reload} loading={loading && !!data}>Refresh</Button>
      </div>

      {error ? <Alert tone="error" className="mt-4">{error}</Alert> : null}

      <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-5">
        <Metric label="Needs review" value={m?.pending ?? "—"} tone="amber" />
        <Metric label="Approved" value={m?.approved ?? "—"} tone="teal" />
        <Metric label="Rejected" value={m?.rejected ?? "—"} tone="red" />
        <Metric label="All applications" value={m?.total ?? "—"} />
        <Metric
          label="Mean automated check"
          value={m?.mean_seconds != null ? `${m.mean_seconds.toFixed(2)} s` : "—"}
          sub={m ? `Across ${m.run_count} saved runs` : undefined}
        />
      </div>

      <Card className="mt-5 overflow-hidden">
        <div className="flex flex-wrap items-center gap-3 border-b border-slate-200 px-4 py-3">
          <div className="flex rounded-lg bg-slate-100 p-0.5" role="tablist" aria-label="Filter by status">
            {(["PENDING", "APPROVED", "REJECTED", "ALL"] as const).map((s) => (
              <button
                key={s}
                role="tab"
                aria-selected={status === s}
                onClick={() => setParams(s === "PENDING" ? {} : { status: s })}
                className={cx("rounded-md px-3 py-1.5 text-[13px] font-medium", status === s ? "bg-white text-slate-900 shadow-sm" : "text-slate-600 hover:text-slate-900")}
              >
                {s === "PENDING" ? "Pending Review" : s === "ALL" ? "All" : s === "APPROVED" ? "Approved" : "Rejected"}
                {m && s !== "ALL" ? (
                  <span className="ml-1.5 text-xs text-slate-400 tabular">{s === "PENDING" ? m.pending : s === "APPROVED" ? m.approved : m.rejected}</span>
                ) : null}
              </button>
            ))}
          </div>
          <div className="relative ml-auto w-full sm:w-72">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
            <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search ID or business" className="pl-9" aria-label="Search applications" />
          </div>
          <Select aria-label="Status filter" className="w-auto sm:hidden" value={status} onChange={(e) => setParams(e.target.value === "PENDING" ? {} : { status: e.target.value })}>
            <option value="PENDING">Pending Review</option>
            <option value="APPROVED">Approved</option>
            <option value="REJECTED">Rejected</option>
            <option value="ALL">All</option>
          </Select>
        </div>

        {loading && !data ? (
          <div className="p-8"><Spinner label="Loading applications…" /></div>
        ) : rows.length === 0 ? (
          <EmptyState icon={Inbox} title={search ? "No matching applications" : status === "PENDING" ? "Queue is clear" : "No applications here yet"}>
            {search ? "Try a different ID or business name." : status === "PENDING" ? "No applications are waiting for review." : "Applications appear here once vendors submit them."}
          </EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="border-b border-slate-200 bg-slate-50 text-xs font-medium text-slate-500">
                <tr>
                  <th scope="col" className="px-4 py-2.5">Application</th>
                  <th scope="col" className="px-4 py-2.5">Status</th>
                  <th scope="col" className="px-4 py-2.5">Primary issue</th>
                  <th scope="col" className="px-4 py-2.5">Next action</th>
                  <th scope="col" className="px-4 py-2.5">Submitted</th>
                  <th scope="col" className="px-4 py-2.5 text-right">Age</th>
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
                      <p className="font-mono text-xs text-slate-500">{r.application_id}</p>
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={r.status} />
                      {r.decision_source === "MANUAL" ? <p className="mt-1 text-xs text-slate-500">Reviewer decision</p> : null}
                    </td>
                    <td className="px-4 py-3 text-slate-700">{r.primary_issue === "—" ? <span className="text-slate-400">—</span> : r.primary_issue}</td>
                    <td className="px-4 py-3"><Pill tone={OWNER_TONE[r.owner] ?? "slate"}>{OWNER_LABEL[r.owner] ?? r.owner}</Pill></td>
                    <td className="px-4 py-3 text-[13px] text-slate-600">
                      {formatDateTime(r.created_at)}
                      {r.elapsed_ms != null ? <p className="text-xs text-slate-400">Check: {formatDuration(r.elapsed_ms)}</p> : null}
                    </td>
                    <td className="px-4 py-3 text-right text-[13px] text-slate-600 tabular">{r.age}</td>
                    <td className="pr-3"><ChevronRight className="size-4 text-slate-400" aria-hidden /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <p className="mt-3 text-xs text-slate-500">
        Figures come from saved records. Mean check time is automated processing only, not total vendor waiting time.
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
