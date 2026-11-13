import { Inbox, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Alert, Button, EmptyState, OwnerPill, Pill, RiskTag, Select, Spinner, StatusBadge, cx } from "../../components/ui";
import { formatAge, formatDateTime, formatDuration } from "../../lib/format";
import type { Overview, QueueRow } from "../../lib/types";
import { useShortcuts } from "../../lib/useShortcuts";
import { TABS, TAB_IDS, type Tab, useOverview } from "./queueState";

// ---------------------------------------------------------------- shared pieces

export function Metric({ label, value, sub }: { label: string; value: ReactNode; sub?: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-2xl border border-line bg-white px-[18px] py-3.5">
      <span className="text-[13px] text-muted">{label}</span>
      <span className="text-[26px] font-bold leading-tight text-ink tabular">{value}</span>
      {sub ? <span className="text-xs text-muted">{sub}</span> : null}
    </div>
  );
}

/** Real counts from saved runs; bars are relative to the largest bucket. */
export function TopReasons({ data, className }: { data: Overview | null; className?: string }) {
  const items = data?.top_reasons.items ?? [];
  const max = Math.max(1, ...items.map((i) => i.count));
  return (
    <section aria-labelledby="reasons-h" className={cx("flex min-h-0 flex-col gap-3.5 rounded-[20px] border border-line bg-white px-5 py-[18px]", className)}>
      <div>
        <h2 id="reasons-h" className="text-[15px] font-semibold text-ink">Top reasons this week</h2>
        <p className="text-xs text-muted">{data ? `Across ${data.top_reasons.runs} automated ${data.top_reasons.runs === 1 ? "check" : "checks"} in the last ${data.top_reasons.days} days` : "Loading…"}</p>
      </div>
      {data && !items.length ? <p className="text-[13px] text-muted">No flagged checks in this period.</p> : null}
      <ul className="flex min-h-0 flex-col gap-3 overflow-y-auto text-[13px]">
        {items.map((item) => (
          <li key={item.reason} className="flex flex-col gap-1.5">
            <div className="flex justify-between gap-2"><span>{item.reason}</span><span className="text-muted tabular">{item.count}</span></div>
            <div aria-hidden className="h-2 rounded-full bg-[#F2F4F7]">
              <div className="h-2 rounded-full bg-navy-600" style={{ width: `${(item.count / max) * 100}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

export function percent(value: number | null | undefined) {
  return value == null ? "—" : `${value}%`;
}

function StatusCell({ row }: { row: QueueRow }) {
  if (row.status !== "PENDING") return <StatusBadge status={row.status} />;
  return <OwnerPill owner={row.owner} label={row.owner === "TEAM" ? "With our team" : row.owner_label} />;
}

// ---------------------------------------------------------------- Applications

export function AdminQueue() {
  const { data, error, loading, reload } = useOverview();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const requested = params.get("tab") as Tab | null;
  const tab: Tab = requested && TAB_IDS.includes(requested) ? requested : "NEEDS_REVIEW";
  const search = params.get("q") ?? "";
  const [active, setActive] = useState(0);
  const tbody = useRef<HTMLTableSectionElement>(null);
  const setTab = (t: Tab) => {
    setActive(0);
    const next = new URLSearchParams();
    if (t !== "NEEDS_REVIEW") next.set("tab", t);
    if (search) next.set("q", search);
    setParams(next);
  };
  const caseUrl = (id: string) => `/admin/cases/${id}${tab === "NEEDS_REVIEW" ? "" : `?tab=${tab}`}`;

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (data?.queue ?? []).filter(
      (r) => (tab === "ALL" || r.tab === tab) && (!q || `${r.application_id} ${r.business} ${r.gstin}`.toLowerCase().includes(q)),
    );
  }, [data, tab, search]);

  useEffect(() => setActive((a) => Math.min(a, Math.max(rows.length - 1, 0))), [rows.length]);
  useEffect(() => {
    tbody.current?.querySelector<HTMLElement>(`[data-row="${active}"]`)?.scrollIntoView({ block: "nearest" });
  }, [active]);
  useShortcuts({
    j: () => setActive((a) => Math.min(a + 1, rows.length - 1)),
    k: () => setActive((a) => Math.max(a - 1, 0)),
    Enter: () => rows[active] && navigate(caseUrl(rows[active].application_id)),
    "/": () => document.getElementById("admin-search")?.focus(),
  });

  const m = data?.metrics;
  const count = (t: Tab) =>
    !m ? null : t === "NEEDS_REVIEW" ? m.needs_review : t === "WAITING_ON_VENDOR" ? m.waiting_on_vendor : t === "APPROVED" ? m.approved : t === "REJECTED" ? m.rejected : m.total;
  const oldest = data?.queue.filter((r) => r.tab === "NEEDS_REVIEW").map((r) => r.waiting_since).sort()[0];

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      {error ? <Alert tone="error" action={<Button size="sm" variant="secondary" icon={RefreshCw} onClick={reload}>Retry</Button>}>{error}</Alert> : null}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Metric label="Needs your review" value={m?.needs_review ?? "—"} />
        <Metric label="Waiting on vendors" value={m?.waiting_on_vendor ?? "—"} />
        <Metric
          label="Approved without review"
          value={percent(m?.straight_through_rate)}
          sub={m ? (m.first_submissions ? `Of ${m.first_submissions} first ${m.first_submissions === 1 ? "submission" : "submissions"}` : "No submissions yet") : undefined}
        />
        <Metric label="Oldest case waiting on you" value={oldest ? formatAge(oldest) : "—"} />
      </div>

      <div className="grid gap-4 fit:min-h-0 fit:flex-1 lg:grid-cols-[minmax(0,3fr)_minmax(0,1fr)]">
        <section aria-labelledby="queue-h" className="flex min-h-[420px] flex-col overflow-hidden rounded-[20px] border border-line bg-white fit:min-h-0">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-line-soft px-5 py-4">
            <h1 id="queue-h" className="text-lg font-bold text-ink">Applications</h1>
            <div role="tablist" aria-label="Filter applications" className="hidden flex-wrap gap-1.5 sm:flex">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={tab === t.id}
                  onClick={() => setTab(t.id)}
                  className={cx(
                    "rounded-full px-3.5 py-[7px] text-[13px]",
                    tab === t.id ? "bg-ink font-semibold text-white" : "bg-[#F2F4F7] text-[#344054] hover:bg-slate-200",
                  )}
                >
                  {t.label}
                  {count(t.id) != null && (t.id === "NEEDS_REVIEW" || t.id === "WAITING_ON_VENDOR") ? <span className="tabular"> · {count(t.id)}</span> : null}
                </button>
              ))}
            </div>
            <Select aria-label="Filter applications" className="w-auto sm:hidden" value={tab} onChange={(e) => setTab(e.target.value as Tab)}>
              {TABS.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </Select>
          </div>

          <div className="min-h-0 flex-1 overflow-auto">
            {loading && !data ? (
              <div className="p-8"><Spinner label="Loading applications…" /></div>
            ) : rows.length === 0 ? (
              <EmptyState icon={Inbox} title={search ? "No matching applications" : tab === "NEEDS_REVIEW" ? "No cases need review" : "Nothing here yet"}>
                {search ? "Try a different name, ID or GSTIN." : tab === "NEEDS_REVIEW" ? "Cases that need a decision from our team appear here." : "Applications appear here once vendors submit them."}
              </EmptyState>
            ) : (
              <table className="w-full min-w-[760px] border-collapse text-left text-sm">
                <thead className="sticky top-0 z-10 bg-white text-xs uppercase tracking-[0.04em] text-muted">
                  <tr>
                    <th scope="col" className="px-5 py-3 font-semibold">Vendor</th>
                    <th scope="col" className="px-3 py-3 font-semibold">Why it's here</th>
                    <th scope="col" className="px-3 py-3 font-semibold">Risk</th>
                    <th scope="col" className="px-3 py-3 font-semibold">Waiting</th>
                    <th scope="col" className="py-3 pl-3 pr-5 font-semibold">Status</th>
                  </tr>
                </thead>
                <tbody ref={tbody}>
                  {rows.map((r, i) => (
                    <tr
                      key={r.application_id}
                      data-row={i}
                      aria-selected={i === active}
                      onClick={() => navigate(caseUrl(r.application_id))}
                      className={cx("cursor-pointer border-t border-line-soft hover:bg-[#F9FAFB]", i === active && "bg-[#F5F7FF] shadow-[inset_3px_0_0_var(--color-navy-600)] hover:bg-[#F5F7FF]")}
                    >
                      <td className="px-5 py-3.5">
                        <Link to={caseUrl(r.application_id)} onClick={(e) => e.stopPropagation()} className="font-semibold text-ink hover:text-navy-700">
                          {r.business || "Unnamed business"}
                        </Link>
                        <div className="text-xs text-muted tabular">{r.application_id}{r.gstin ? ` · ${r.gstin}` : ""}</div>
                      </td>
                      <td className="px-3 py-3.5 text-ink">{r.reason}</td>
                      <td className="px-3 py-3.5"><RiskTag risk={r.risk} /></td>
                      <td className="whitespace-nowrap px-3 py-3.5 tabular" title={formatDateTime(r.waiting_since)}>{formatAge(r.waiting_since)}</td>
                      <td className="py-3.5 pl-3 pr-5"><StatusCell row={r} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          <div className="flex justify-between gap-3 border-t border-line-soft px-5 py-2.5 text-xs text-muted">
            <span>Sorted by risk, then waiting time</span>
            <span>Synthetic test data</span>
          </div>
        </section>

        <aside className="grid gap-4 fit:min-h-0 fit:grid-rows-[minmax(0,1fr)_auto]">
          <TopReasons data={data} />
          <section aria-labelledby="keys-h" className="flex flex-col gap-2.5 rounded-[20px] bg-ink px-5 py-[18px] text-[#E4E7EC]">
            <h2 id="keys-h" className="text-sm font-semibold text-white">Keyboard</h2>
            <dl className="grid grid-cols-[auto_1fr] items-center gap-x-3 gap-y-2 text-[13px]">
              {[["J / K", "Move down / up"], ["Enter", "Open case"], ["/", "Search"]].map(([key, label]) => (
                <div key={key} className="contents">
                  <dt><kbd className="block rounded-md border border-[#334155] bg-[#1E293B] px-2 py-0.5 text-center text-xs">{key}</kbd></dt>
                  <dd>{label}</dd>
                </div>
              ))}
            </dl>
          </section>
        </aside>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Overview

export function AdminOverview() {
  const { data, error } = useOverview();
  const m = data?.metrics;
  const oldest = data?.queue.filter((r) => r.tab === "NEEDS_REVIEW").map((r) => r.waiting_since).sort()[0];
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-lg font-bold text-ink">Overview</h1>
        <Pill>Synthetic test data</Pill>
      </div>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-5">
        <Metric label="Needs review" value={m?.needs_review ?? "—"} />
        <Metric label="Waiting on vendors" value={m?.waiting_on_vendor ?? "—"} />
        <Metric label="Straight-through rate" value={percent(m?.straight_through_rate)} sub="First submissions approved automatically" />
        <Metric label="Median check time" value={m?.median_check_ms != null ? formatDuration(m.median_check_ms) : "—"} sub={m ? `Automated checks with documents (${m.runs_with_documents})` : undefined} />
        <Metric label="Oldest case waiting on you" value={oldest ? formatAge(oldest) : "—"} />
      </div>
      <div className="grid gap-4 fit:min-h-0 fit:flex-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,2fr)]">
        <TopReasons data={data} />
        <RunsTable title="Recent runs" runs={(data?.recent_runs ?? []).slice(0, 25)} loading={!data} />
      </div>
    </div>
  );
}

function RunsTable({ title, runs, loading, description }: { title: string; runs: Overview["recent_runs"]; loading: boolean; description?: string }) {
  return (
    <section className="flex min-h-[320px] flex-col overflow-hidden rounded-[20px] border border-line bg-white fit:min-h-0">
      <div className="border-b border-line-soft px-5 py-4">
        <h2 className="text-[15px] font-semibold text-ink">{title}</h2>
        {description ? <p className="text-xs text-muted">{description}</p> : null}
      </div>
      <div className="min-h-0 flex-1 overflow-auto">
        {loading ? (
          <div className="p-6"><Spinner /></div>
        ) : runs.length === 0 ? (
          <EmptyState icon={Inbox} title="No runs yet">Automated checks appear here once vendors submit.</EmptyState>
        ) : (
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="sticky top-0 bg-white text-xs uppercase tracking-[0.04em] text-muted">
              <tr>
                <th scope="col" className="px-5 py-2.5 font-semibold">Time</th>
                <th scope="col" className="px-3 py-2.5 font-semibold">Vendor</th>
                <th scope="col" className="px-3 py-2.5 font-semibold">Trigger</th>
                <th scope="col" className="px-3 py-2.5 font-semibold">Result</th>
                <th scope="col" className="py-2.5 pl-3 pr-5 text-right font-semibold">Duration</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.run_id} className="border-t border-line-soft">
                  <td className="whitespace-nowrap px-5 py-2.5 text-[13px] text-muted">{formatDateTime(r.at)}</td>
                  <td className="px-3 py-2.5">
                    <Link to={`/admin/cases/${r.application_id}?tab=ALL`} className="font-medium text-ink hover:text-navy-700">{r.business || r.application_id}</Link>
                    <div className="text-xs text-muted tabular">{r.application_id}</div>
                  </td>
                  <td className="px-3 py-2.5 text-[13px]">{r.trigger}</td>
                  <td className="px-3 py-2.5">
                    <Pill tone={r.result === "Approved" ? "teal" : r.result === "Waiting on vendor" ? "amber" : "navy"}>{r.result}</Pill>
                  </td>
                  <td className="py-2.5 pl-3 pr-5 text-right text-[13px] tabular">{formatDuration(r.elapsed_ms)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- Activity

export function AdminActivity() {
  const { data, error, loading } = useOverview();
  const actions = data?.recent_actions ?? [];
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <div>
        <h1 className="text-lg font-bold text-ink">Activity</h1>
        <p className="text-[13px] text-muted">Every automated check and reviewer decision across all vendors, newest first.</p>
      </div>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <div className="grid gap-4 fit:min-h-0 fit:flex-1 xl:grid-cols-2">
        <RunsTable title="Automated checks" runs={data?.recent_runs ?? []} loading={loading && !data} description="Each run with its trigger, result and server-measured duration." />
        <section className="flex min-h-[320px] flex-col overflow-hidden rounded-[20px] border border-line bg-white fit:min-h-0">
          <div className="border-b border-line-soft px-5 py-4">
            <h2 className="text-[15px] font-semibold text-ink">Decision history</h2>
            <p className="text-xs text-muted">Read-only audit of reviewer actions.</p>
          </div>
          <div className="min-h-0 flex-1 overflow-auto">
            {loading && !data ? (
              <div className="p-6"><Spinner /></div>
            ) : actions.length === 0 ? (
              <EmptyState icon={Inbox} title="No reviewer actions yet">Approvals, rejections and correction requests appear here.</EmptyState>
            ) : (
              <table className="w-full min-w-[620px] text-left text-sm">
                <thead className="sticky top-0 bg-white text-xs uppercase tracking-[0.04em] text-muted">
                  <tr>
                    <th scope="col" className="px-5 py-2.5 font-semibold">When</th>
                    <th scope="col" className="px-3 py-2.5 font-semibold">Application</th>
                    <th scope="col" className="px-3 py-2.5 font-semibold">Action</th>
                    <th scope="col" className="py-2.5 pl-3 pr-5 font-semibold">Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {actions.map((a, i) => (
                    <tr key={`${a.application_id}-${a.created_at}-${i}`} className="border-t border-line-soft align-top">
                      <td className="whitespace-nowrap px-5 py-2.5 text-[13px] text-muted">{formatDateTime(a.created_at)}</td>
                      <td className="px-3 py-2.5">
                        <Link to={`/admin/cases/${a.application_id}?tab=ALL`} className="font-medium text-ink hover:text-navy-700">{a.business || a.application_id}</Link>
                        <div className="text-xs text-muted tabular">{a.application_id}</div>
                      </td>
                      <td className="px-3 py-2.5">
                        <Pill tone={a.action === "APPROVE" ? "teal" : a.action === "REJECT" ? "red" : "amber"}>{a.label}</Pill>
                      </td>
                      <td className="py-2.5 pl-3 pr-5 text-[13px] text-ink">
                        {a.reason}
                        {a.confirmation ? <div className="mt-0.5 text-xs text-teal-700">✓ {a.confirmation}</div> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
