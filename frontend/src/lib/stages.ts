import type { StageEvent, StageRow, StageState } from "./types";

/** The nine real workflow stages emitted by vendorflow.pipeline + persistence. */
export const STAGE_DEFS: { stage_id: string; label: string; description: string }[] = [
  { stage_id: "S1", label: "Intake", description: "Application and minimum details accepted" },
  { stage_id: "S2", label: "PDF reading", description: "Text read from the GST certificate and bank proof" },
  { stage_id: "S3", label: "Gemini extraction", description: "Candidate fields extracted from document text" },
  { stage_id: "S4", label: "Normalization", description: "Identifiers prepared for exact comparison" },
  { stage_id: "S5", label: "Deterministic rules", description: "Format, consistency and evidence checks" },
  { stage_id: "S6", label: "Identity screening", description: "Registration identity screened against approved vendors" },
  { stage_id: "S7", label: "Decision routing", description: "Approved or Pending Review chosen by policy" },
  { stage_id: "S8", label: "Explanation", description: "Plain-English reasons prepared from the rules" },
  { stage_id: "S9", label: "Persistence", description: "Decision, evidence versions and history saved" },
];

/** Vendor wording for the same nine real stages (matches backend VENDOR_STAGES). */
export const VENDOR_STAGE_DEFS: { stage_id: string; label: string; description: string }[] = [
  { stage_id: "S1", label: "Received", description: "Your application arrived" },
  { stage_id: "S2", label: "Opened your documents", description: "We opened your GST certificate and bank document" },
  { stage_id: "S3", label: "Read the details", description: "We read the details printed on your documents" },
  { stage_id: "S4", label: "Prepared the details", description: "Spacing and capitals tidied so numbers compare exactly" },
  { stage_id: "S5", label: "Checked formats and compared documents", description: "Your details compared with your documents" },
  { stage_id: "S6", label: "Checked our records", description: "Checked against our existing supplier records" },
  { stage_id: "S7", label: "Decided", description: "Our onboarding rules applied" },
  { stage_id: "S8", label: "Prepared your result", description: "Reasons and next step written" },
  { stage_id: "S9", label: "Saved", description: "Your result and history saved" },
];

export function initialStages(): StageRow[] {
  return STAGE_DEFS.map((d) => ({
    stage_id: d.stage_id,
    label: d.label,
    state: "NOT_RUN" as StageState,
    note: "",
    started_at: null,
    finished_at: null,
    duration_ms: null,
  }));
}

/** Apply one REAL server event. Never advances a stage the server did not report. */
export function applyStageEvent(rows: StageRow[], event: StageEvent): StageRow[] {
  return rows.map((row) => {
    if (row.stage_id !== event.stage_id) return row;
    if (event.event === "STARTED") {
      return { ...row, state: "STARTED", started_at: event.timestamp, note: event.note || row.note };
    }
    const started = row.started_at ? Date.parse(row.started_at) : NaN;
    const finished = Date.parse(event.timestamp);
    // A later SKIPPED/COMPLETED must not hide an earlier FAILED for the same stage.
    if (row.state === "FAILED" && event.event !== "FAILED") return row;
    return {
      ...row,
      state: event.event,
      note: event.note,
      finished_at: event.timestamp,
      duration_ms: Number.isFinite(started) && Number.isFinite(finished) ? Math.max(0, finished - started) : null,
    };
  });
}

export function stageProgress(rows: StageRow[]): number {
  const done = rows.filter((r) => r.state === "COMPLETED" || r.state === "SKIPPED" || r.state === "FAILED").length;
  return Math.round((done / rows.length) * 100);
}
