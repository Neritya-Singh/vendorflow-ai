import { Check, Loader2, Minus, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { formatDuration, formatTime } from "../lib/format";
import { STAGE_DEFS } from "../lib/stages";
import type { StageRow } from "../lib/types";
import { cx } from "./ui";

function StageIcon({ state }: { state: StageRow["state"] }) {
  const base = "grid size-7 shrink-0 place-items-center rounded-full ring-1 ring-inset";
  if (state === "COMPLETED")
    return <span className={cx(base, "bg-teal-600 text-white ring-teal-600")}><Check className="size-4" aria-hidden /></span>;
  if (state === "STARTED")
    return <span className={cx(base, "bg-navy-50 text-navy-700 ring-navy-300")}><Loader2 className="size-4 animate-spin" aria-hidden /></span>;
  if (state === "FAILED")
    return <span className={cx(base, "bg-amber-500 text-white ring-amber-500")}><TriangleAlert className="size-3.5" aria-hidden /></span>;
  if (state === "SKIPPED")
    return <span className={cx(base, "bg-slate-100 text-slate-500 ring-slate-300")}><Minus className="size-4" aria-hidden /></span>;
  return <span className={cx(base, "bg-white ring-slate-200")}><span className="size-1.5 rounded-full bg-slate-300" /></span>;
}

const STATE_TEXT: Record<StageRow["state"], string> = {
  NOT_RUN: "Waiting",
  STARTED: "Running",
  COMPLETED: "Completed",
  SKIPPED: "Skipped",
  FAILED: "Failed",
};

function LiveTimer({ since }: { since: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 100);
    return () => window.clearInterval(timer);
  }, []);
  return <span className="tabular">{formatDuration(now - since)}</span>;
}

/**
 * Renders saved or live stage rows. `liveStartedAt` maps a stage to the client
 * time its STARTED event arrived, to tick a running counter; completed rows show
 * the server-measured duration between its own STARTED and final timestamps.
 */
export function StageList({ rows, liveStartedAt, compact }: {
  rows: StageRow[];
  liveStartedAt?: Record<string, number>;
  compact?: boolean;
}) {
  return (
    <ol className="relative" aria-label="Workflow stages">
      {rows.map((row, index) => {
        const def = STAGE_DEFS.find((d) => d.stage_id === row.stage_id);
        const last = index === rows.length - 1;
        return (
          <li key={row.stage_id} className="relative flex gap-3 pb-4 last:pb-0">
            {!last ? (
              <span
                aria-hidden
                className={cx(
                  "absolute left-[13px] top-8 bottom-0 w-px",
                  row.state === "COMPLETED" ? "bg-teal-300" : "bg-slate-200",
                )}
              />
            ) : null}
            <StageIcon state={row.state} />
            <div className="min-w-0 flex-1 pt-0.5">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                <p className={cx("text-sm font-medium", row.state === "NOT_RUN" ? "text-slate-400" : "text-slate-900")}>
                  <span className="mr-1.5 font-mono text-[11px] text-slate-400">{row.stage_id}</span>
                  {def?.label ?? row.label}
                </p>
                <p className="text-xs text-slate-500 tabular" aria-live={row.state === "STARTED" ? "polite" : undefined}>
                  <span className="sr-only">{STATE_TEXT[row.state]}. </span>
                  {row.state === "STARTED" && liveStartedAt?.[row.stage_id] ? (
                    <LiveTimer since={liveStartedAt[row.stage_id]} />
                  ) : row.state === "NOT_RUN" ? (
                    <span aria-hidden>{STATE_TEXT[row.state]}</span>
                  ) : (
                    <>
                      <span aria-hidden className={cx(row.state === "FAILED" && "font-medium text-amber-700")}>{STATE_TEXT[row.state]}</span>
                      {row.duration_ms !== null ? <span> · {formatDuration(row.duration_ms)}</span> : null}
                    </>
                  )}
                </p>
              </div>
              {!compact ? (
                <p className="mt-0.5 text-[13px] text-slate-500">
                  {row.note && row.state !== "NOT_RUN" ? row.note : def?.description}
                  {row.finished_at && row.state !== "NOT_RUN" ? (
                    <span className="text-slate-400"> · {formatTime(row.finished_at)}</span>
                  ) : null}
                </p>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
