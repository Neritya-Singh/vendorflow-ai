import { Loader2, Radio, RotateCcw, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { formatDuration } from "../lib/format";
import { stageProgress } from "../lib/stages";
import type { RunState } from "../lib/useWorkflowRun";
import { StageList } from "./StageList";
import { Alert, Button, Card, cx } from "./ui";

function Elapsed({ from, to }: { from: number; to: number | null }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (to) return;
    const t = window.setInterval(() => setNow(Date.now()), 100);
    return () => window.clearInterval(t);
  }, [to]);
  return <span className="tabular">{formatDuration((to ?? now) - from)}</span>;
}

/** Live view of one evaluation. Only server events move a stage forward. */
export function ProcessingPanel({ run, title, onRetry, onCheckStatus }: {
  run: RunState;
  title: string;
  onRetry?: () => void;
  onCheckStatus?: () => void;
}) {
  const progress = stageProgress(run.stages);
  const active = run.phase === "sending" || run.phase === "running";
  return (
    <Card className="overflow-hidden">
      <div className="border-b border-line px-5 py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-[15px] font-semibold text-slate-900">{title}</h2>
            <p className="mt-0.5 flex items-center gap-1.5 text-[13px] text-slate-500" aria-live="polite">
              {active ? <Loader2 className="size-3.5 shrink-0 animate-spin text-navy-600" aria-hidden /> : null}
              {run.phase === "sending"
                ? "Checking your application…"
                : run.phase === "running"
                  ? "Checking your application… each step below updates as it finishes."
                  : run.phase === "done"
                    ? "All steps reported by the server."
                    : "Processing stopped before a result was returned."}
            </p>
          </div>
          {run.sentAt ? (
            <div className="text-right">
              <p className="text-xs text-slate-500">{active ? "Elapsed" : "Total time"}</p>
              <p className="text-sm font-semibold text-slate-900">
                <Elapsed from={run.sentAt} to={run.finishedAt} />
              </p>
            </div>
          ) : null}
        </div>
        <div
          className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-100"
          role="progressbar"
          aria-label="Stages reported"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={progress}
        >
          <div
            className={cx("h-full rounded-full transition-[width] duration-300", run.phase === "failed" || run.phase === "interrupted" ? "bg-amber-500" : "bg-teal-600")}
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>
      <div className="px-5 py-5">
        <StageList rows={run.stages} liveStartedAt={run.liveStartedAt} audience="vendor" />
      </div>
      {run.phase === "interrupted" ? (
        <div className="border-t border-line px-5 py-4">
          <Alert tone="warning" title="Connection interrupted">
            We lost the connection before the server confirmed a result. Your application may still have been
            saved. Check its status with your application ID and tracking code before retrying — retrying with the
            same details never creates a second application.
            <div className="mt-3 flex flex-wrap gap-2">
              {onCheckStatus ? <Button size="sm" icon={Search} onClick={onCheckStatus}>Check status</Button> : null}
              {onRetry ? <Button size="sm" variant="secondary" icon={RotateCcw} onClick={onRetry}>Retry</Button> : null}
            </div>
          </Alert>
        </div>
      ) : null}
      {run.phase === "failed" && run.error ? (
        <div className="border-t border-line px-5 py-4">
          <Alert tone="error" title="This check could not be completed">
            {run.error.message}
            {onRetry || onCheckStatus ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {onRetry ? <Button size="sm" icon={RotateCcw} onClick={onRetry}>Try again</Button> : null}
                {onCheckStatus ? <Button size="sm" variant="secondary" icon={Search} onClick={onCheckStatus}>Check status</Button> : null}
              </div>
            ) : null}
          </Alert>
        </div>
      ) : null}
      <p className="flex items-center gap-1.5 border-t border-slate-100 bg-slate-50 px-5 py-2.5 text-xs text-slate-500">
        <Radio className="size-3.5" aria-hidden />
        Each step updates only when it actually finishes on our side.
      </p>
    </Card>
  );
}
