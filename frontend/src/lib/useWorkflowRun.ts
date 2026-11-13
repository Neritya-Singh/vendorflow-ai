import { useCallback, useRef, useState } from "react";
import { ApiError, runWorkflow, type WorkflowPayload } from "./api";
import { applyStageEvent, initialStages } from "./stages";
import type { StageRow, VendorView } from "./types";

export type RunPhase = "idle" | "sending" | "running" | "done" | "failed" | "interrupted";

export interface RunState {
  phase: RunPhase;
  stages: StageRow[];
  liveStartedAt: Record<string, number>;
  sentAt: number | null;
  acceptedAt: number | null;
  finishedAt: number | null;
  result: VendorView | null;
  error: { status: number; message: string } | null;
}

const fresh = (): RunState => ({
  phase: "idle",
  stages: initialStages(),
  liveStartedAt: {},
  sentAt: null,
  acceptedAt: null,
  finishedAt: null,
  result: null,
  error: null,
});

export function useWorkflowRun() {
  const [state, setState] = useState<RunState>(fresh);
  const busy = useRef(false);

  const start = useCallback(async (payload: WorkflowPayload) => {
    if (busy.current) return null;
    busy.current = true;
    setState({ ...fresh(), phase: "sending", sentAt: Date.now() });
    let finalResult: VendorView | null = null;
    let sawTerminalMessage = false;
    try {
      await runWorkflow(payload, (message) => {
        if (message.type === "accepted") {
          setState((s) => ({ ...s, phase: "running", acceptedAt: Date.now() }));
        } else if (message.type === "stage") {
          setState((s) => ({
            ...s,
            stages: applyStageEvent(s.stages, message),
            liveStartedAt:
              message.event === "STARTED" ? { ...s.liveStartedAt, [message.stage_id]: Date.now() } : s.liveStartedAt,
          }));
        } else if (message.type === "result") {
          sawTerminalMessage = true;
          finalResult = message.data;
          setState((s) => ({
            ...s,
            phase: "done",
            result: message.data,
            finishedAt: Date.now(),
            // The saved record is the authority for the final stage rows.
            stages: message.data.stages?.length ? message.data.stages : s.stages,
          }));
        } else if (message.type === "error") {
          sawTerminalMessage = true;
          setState((s) => ({
            ...s,
            phase: "failed",
            finishedAt: Date.now(),
            error: { status: message.status, message: message.message },
          }));
        }
      });
      if (!sawTerminalMessage) throw new ApiError(0, "STREAM_INTERRUPTED");
    } catch (err) {
      const e = err instanceof ApiError ? err : new ApiError(0, "STREAM_INTERRUPTED");
      setState((s) => ({
        ...s,
        phase: e.message === "STREAM_INTERRUPTED" ? "interrupted" : "failed",
        finishedAt: Date.now(),
        error: { status: e.status, message: e.message },
      }));
    } finally {
      busy.current = false;
    }
    return finalResult;
  }, []);

  const reset = useCallback(() => setState(fresh()), []);
  return { state, start, reset };
}
