export type Status = "APPROVED" | "PENDING" | "REJECTED";
export type CheckState = "PASS" | "FAIL" | "UNKNOWN";
export type StageState = "NOT_RUN" | "STARTED" | "COMPLETED" | "FAILED" | "SKIPPED";
export type Owner = "Vendor" | "Reviewer" | "Technical retry" | "Complete";

export interface VendorFields {
  legal_name: string;
  contact_name: string;
  contact_email: string;
  business_state: string;
  pan: string;
  gstin: string;
  bank_holder: string;
  account_number: string;
  ifsc: string;
}

export const EMPTY_FIELDS: VendorFields = {
  legal_name: "",
  contact_name: "",
  contact_email: "",
  business_state: "",
  pan: "",
  gstin: "",
  bank_holder: "",
  account_number: "",
  ifsc: "",
};

export interface Credentials {
  application_id: string;
  tracking_code: string;
}

export interface Health {
  status: string;
  mode: "live" | "offline";
  gemini_configured: boolean;
  supabase_configured: boolean;
  admin_configured: boolean;
  extractor: string;
}

export interface Meta {
  states: string[];
  max_pdf_bytes: number;
  stages: { stage_id: string; label: string }[];
}

export interface StageRow {
  stage_id: string;
  label: string;
  state: StageState;
  note: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
}

export interface StageEvent {
  type: "stage";
  stage_id: string;
  label: string;
  event: "STARTED" | "COMPLETED" | "FAILED" | "SKIPPED";
  timestamp: string;
  note: string;
}

export interface VendorCheck {
  label: string;
  state: CheckState;
  detail: string;
}

export interface TimelineItem {
  kind: "run" | "review";
  at: string | null;
  title: string;
  status: Status;
  status_label?: string;
  elapsed_ms?: number | null;
  message?: string;
  documents?: { doc_type: string; version: number }[];
}

export interface ReviewerNote {
  action: "APPROVE" | "REJECT" | "REQUEST_CORRECTION";
  title: string;
  message: string;
  at: string | null;
}

export interface VendorView {
  application_id: string;
  status: Status;
  status_label: string;
  decision_source: "AUTOMATED" | "MANUAL";
  owner: Owner;
  processing_unavailable: boolean;
  heading: string;
  next_step: string;
  reasons: string[];
  reviewer_note: ReviewerNote | null;
  checks: VendorCheck[];
  stages: StageRow[];
  elapsed_ms: number | null;
  timeline: TimelineItem[];
  documents: { doc_type: string; version: number }[];
  editable: boolean;
  needs_resume: boolean;
  revision?: number;
  latest_run_id: string | null;
  submitted: Partial<VendorFields>;
  created_at: string | null;
  persisted?: boolean;
}

export type StreamMessage =
  | { type: "accepted"; at: string }
  | { type: "heartbeat" }
  | StageEvent
  | { type: "result"; data: VendorView }
  | { type: "error"; status: number; kind: string; message: string };

// ---------------------------------------------------------------- admin

export interface QueueRow {
  application_id: string;
  business: string;
  status: Status;
  status_label: string;
  decision_source: string;
  owner: Owner;
  primary_issue: string;
  age: string;
  created_at: string | null;
  updated_at: string | null;
  elapsed_ms: number | null;
  has_run: boolean;
}

export interface ReviewRecord {
  action: "APPROVE" | "REJECT" | "REQUEST_CORRECTION";
  label: string;
  reason: string;
  actor: string;
  reviewed_run_id: string | null;
  created_at: string | null;
  application_id?: string;
  business?: string;
}

export interface Overview {
  metrics: {
    total: number;
    approved: number;
    pending: number;
    rejected: number;
    run_count: number;
    mean_seconds: number | null;
  };
  queue: QueueRow[];
  recent_actions: ReviewRecord[];
}

export interface Issue {
  state: CheckState;
  rule_id: string;
  label: string;
  note: string;
}

export interface ComparisonRow {
  Field: string;
  Submitted: string;
  "From PDF": string;
  Assessment?: string;
  Kind?: "ok" | "flag" | "missing";
}

export interface RunDetail {
  id: string;
  trigger: "submission" | "resubmission";
  status: Status;
  status_label: string;
  created_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  elapsed_ms: number | null;
  extraction_error: boolean;
  reasons: string[];
  stages: StageRow[];
  documents: { doc_type: "GST" | "BANK"; version: number; sha256_prefix: string }[];
  pdf_types: ("GST" | "BANK")[];
}

export interface AdminCase {
  application_id: string;
  business: string;
  status: Status;
  status_label: string;
  decision_source: string;
  revision: number;
  latest_run_id: string | null;
  created_at: string | null;
  updated_at: string | null;
  contact: { name: string; email: string; state: string };
  reasons: string[];
  owner: Owner;
  primary_issue: string;
  issues: { failed: Issue[]; unverified: Issue[] };
  comparison: ComparisonRow[];
  checks: { rule_id: string; label: string; state: CheckState; evidence: string }[];
  runs: RunDetail[];
  reviews: ReviewRecord[];
  can_review: boolean;
  active_correction_request: boolean;
}
