export type Status = "APPROVED" | "PENDING" | "REJECTED";
export type CheckState = "PASS" | "FAIL" | "UNKNOWN";
export type StageState = "NOT_RUN" | "STARTED" | "COMPLETED" | "FAILED" | "SKIPPED";
/** Who acts next on a case (V2_02 §6). Never a fourth decision status. */
export type Owner = "DRAFT" | "VENDOR" | "TEAM" | "COMPLETE";
export type Risk = "HIGH" | "MEDIUM" | "LOW" | null;
export type QueueTab = "NEEDS_REVIEW" | "WAITING_ON_VENDOR" | "APPROVED" | "REJECTED";

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
  workspace_name?: string;
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

export interface VendorMessage {
  id: string;
  at: string | null;
  source: "Automated check" | "Reviewer action";
  title: string;
  text: string;
  delivery: string;
}

export interface TodoItem {
  key: string;
  text: string;
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
  retry_available: boolean;
  heading: string;
  next_step: string;
  reasons: string[];
  todo: TodoItem[];
  messages: VendorMessage[];
  reviewer_note: ReviewerNote | null;
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
  gstin: string;
  status: Status;
  status_label: string;
  decision_source: string;
  owner: Owner;
  owner_label: string;
  tab: QueueTab;
  reason: string;
  risk: Risk;
  age: string;
  created_at: string | null;
  updated_at: string | null;
  waiting_since: string | null;
  elapsed_ms: number | null;
}

export interface ReviewRecord {
  action: "APPROVE" | "REJECT" | "REQUEST_CORRECTION";
  label: string;
  reason: string;
  confirmation: string | null;
  /** Items a correction request asked for, as reviewer labels. */
  requested?: string[];
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
    needs_review: number;
    waiting_on_vendor: number;
    oldest_needs_review: string | null;
    straight_through_rate: number | null;
    first_submissions: number;
    median_check_ms: number | null;
    runs_with_documents: number;
    run_count: number;
    mean_seconds: number | null;
  };
  queue: QueueRow[];
  recent_actions: ReviewRecord[];
  top_reasons: { days: number; runs: number; items: { reason: string; count: number }[] };
  recent_runs: RecentRun[];
}

export interface RecentRun {
  run_id: string;
  application_id: string;
  business: string;
  at: string | null;
  trigger: "Submission" | "Re-check";
  result: "Approved" | "Waiting on vendor" | "Sent to team";
  status: Status;
  elapsed_ms: number | null;
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
  gstin: string;
  status: Status;
  status_label: string;
  decision_source: string;
  revision: number;
  latest_run_id: string | null;
  created_at: string | null;
  updated_at: string | null;
  contact: { name: string; email: string; phone: string; state: string };
  declared: boolean;
  /** B5: same order as `comparison`. "edited" = vendor changed it; "vendor" = typed, not on the document. */
  provenance: { field: string; label: string; status: "document" | "edited" | "vendor" | "missing" | "unread" }[];
  reasons: string[];
  owner: Owner;
  owner_label: string;
  primary_issue: string;
  risk: Risk;
  flags: { rule_id: string; risk: Exclude<Risk, null>; reason: string }[];
  vendor_items: { short: string; text: string }[];
  issues: { failed: Issue[]; unverified: Issue[] };
  comparison: ComparisonRow[];
  checks: { rule_id: string; label: string; state: CheckState; evidence: string }[];
  runs: RunDetail[];
  reviews: ReviewRecord[];
  linked_records: LinkedRecord[];
  messages: VendorMessage[];
  correction_draft: string;
  correction_items: { id: FixItemId; label: string }[];
  suggested_items: FixItemId[];
  requires_confirmation: boolean;
  confirmation_text: string;
  can_review: boolean;
  active_correction_request: boolean;
}

export interface LinkedRecord {
  application_id: string;
  business: string;
  status: Status;
  status_label: string;
  match: string[];
  comparison: { field: string; this: string; other: string; same: boolean }[];
  latest_run_id: string | null;
  documents: ("GST" | "BANK")[];
}

// ---------------------------------------------------------------- B5/B6 upload-first draft
export type Slot = "GST" | "BANK";
export type FileStatus = "read" | "nothing_found" | "wrong_slot" | "unreadable" | "unavailable";
export type FieldSource = "document" | "edited" | "vendor" | "missing" | "unread";
export type DraftFieldKey = "legal_name" | "gstin" | "business_state" | "bank_holder" | "account_number" | "ifsc";

export interface DraftFile {
  filename: string;
  status: FileStatus;
  message: string;
  suggested_slot: Slot | null;
  pages: number | null;
  uploaded_at: string | null;
  /** Fix page only: the document already used in the latest check (not a new upload). */
  on_file?: boolean;
  version?: number | null;
}

export interface DraftField {
  key: DraftFieldKey;
  label: string;
  document: Slot;
  /** Account number is masked to its last 4 digits. */
  value: string;
  document_value: string | null;
  status: FieldSource;
  error: string | null;
}

export interface Contact {
  name: string;
  email: string;
  phone: string;
}

export interface DraftView {
  application_id: string;
  owner: "DRAFT" | "VENDOR";
  buyer: string;
  /** Draft revision; parallel requests may answer out of order. */
  rev: number;
  files: Record<Slot, DraftFile | null>;
  fields: DraftField[];
  pan: { value: string; source: "GSTIN" };
  address: string | null;
  contact: Contact;
  contact_errors: Partial<Record<keyof Contact, string>>;
  declaration: boolean;
  documents_ready: boolean;
  details_ready: boolean;
  blockers: string[];
  flagged: DraftFieldKey[];
}

export type DraftStreamMessage =
  | { type: "accepted"; at: string }
  | { type: "heartbeat" }
  | StageEvent
  | { type: "result"; data: DraftView }
  /** "Move it": the swapped view, sent before the moved files' copies are saved. */
  | { type: "preview"; data: DraftView }
  | { type: "error"; status: number; kind: string; message: string };

// ---------------------------------------------------------------- B7 fix items
export type FixItemId = `doc:${Slot}` | `field:${DraftFieldKey | "contact"}`;
export type FixItem =
  | { id: FixItemId; kind: "document"; slot: Slot; text: string }
  | { id: FixItemId; kind: "field"; field: DraftFieldKey | "contact"; text: string };

/** A submitted application being fixed: only the requested items are shown. */
export interface FixView extends DraftView {
  items: FixItem[];
  show_slots: Slot[];
  shown_fields: DraftFieldKey[];
  show_contact: boolean;
  ready: boolean;
}
