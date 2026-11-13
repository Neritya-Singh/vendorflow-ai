import { applyStageEvent, initialStages, stageProgress } from "./stages";
import type { StageEvent } from "./types";

const ev = (stage_id: string, event: StageEvent["event"], timestamp: string, note = ""): StageEvent => ({
  type: "stage", stage_id, label: stage_id, event, timestamp, note,
});

describe("applyStageEvent", () => {
  it("starts with nine waiting stages and advances only on server events", () => {
    let rows = initialStages();
    expect(rows).toHaveLength(9);
    expect(rows.every((r) => r.state === "NOT_RUN")).toBe(true);
    rows = applyStageEvent(rows, ev("S2", "STARTED", "2026-01-01T00:00:00.000Z"));
    expect(rows[1].state).toBe("STARTED");
    expect(rows[0].state).toBe("NOT_RUN");
    rows = applyStageEvent(rows, ev("S2", "COMPLETED", "2026-01-01T00:00:00.250Z", "2/2 PDFs readable"));
    expect(rows[1]).toMatchObject({ state: "COMPLETED", duration_ms: 250, note: "2/2 PDFs readable" });
    expect(stageProgress(rows)).toBe(11);
  });

  it("never lets a later event hide a failure", () => {
    let rows = initialStages();
    rows = applyStageEvent(rows, ev("S3", "STARTED", "2026-01-01T00:00:00Z"));
    rows = applyStageEvent(rows, ev("S3", "FAILED", "2026-01-01T00:00:02Z", "AI extraction failed"));
    rows = applyStageEvent(rows, ev("S3", "SKIPPED", "2026-01-01T00:00:03Z"));
    expect(rows[2].state).toBe("FAILED");
  });
});
