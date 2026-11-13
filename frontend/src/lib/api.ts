import type {
  AdminCase, ComparisonRow, Contact, Credentials, DraftFieldKey, DraftStreamMessage, DraftView, FixView, Health, Meta, Overview,
  Slot, StreamMessage, VendorFields, VendorView,
} from "./types";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

let csrfToken: string | null = null;
export const setCsrf = (token: string | null) => {
  csrfToken = token;
};

function detailOf(body: unknown, fallback: string): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return "Some fields are invalid. Check your entries and try again.";
  }
  return fallback;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (csrfToken && init.method && init.method !== "GET") headers.set("X-CSRF-Token", csrfToken);
  let response: Response;
  try {
    response = await fetch(path, { ...init, headers, credentials: "same-origin" });
  } catch {
    throw new ApiError(0, "Can't reach the VendorFlow server. Check your connection and try again.");
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(response.status, detailOf(body, `Request failed (${response.status}).`));
  }
  return body as T;
}

export const api = {
  health: () => request<Health>("/api/health"),
  meta: () => request<Meta>("/api/meta"),
  intake: () => request<Credentials>("/api/vendor/intake", { method: "POST" }),
  track: (creds: Credentials) =>
    request<VendorView>("/api/vendor/track", { method: "POST", body: JSON.stringify(creds) }),
  openDraft: (creds: Credentials) =>
    request<DraftView>("/api/vendor/draft", { method: "POST", body: JSON.stringify(creds) }),
  saveDraft: (
    creds: Credentials,
    body: { changes?: Partial<Record<DraftFieldKey, string>>; reset?: DraftFieldKey[]; contact?: Contact; declaration?: boolean },
  ) => request<DraftView>("/api/vendor/draft/values", { method: "PUT", body: JSON.stringify({ ...creds, ...body }) }),
  openFix: (creds: Credentials) =>
    request<FixView>("/api/vendor/fix", { method: "POST", body: JSON.stringify(creds) }),
  saveFix: (creds: Credentials, body: { changes?: Partial<Record<DraftFieldKey, string>>; reset?: DraftFieldKey[]; contact?: Contact }) =>
    request<FixView>("/api/vendor/fix/values", { method: "PUT", body: JSON.stringify({ ...creds, ...body }) }),
  removeDraftFile: (creds: Credentials, slot: Slot) =>
    request<DraftView>("/api/vendor/draft/remove", { method: "POST", body: JSON.stringify({ ...creds, slot }) }),

  adminSession: () =>
    request<{ authenticated: boolean; csrf_token?: string; configured: boolean }>("/api/admin/session"),
  adminLogin: (password: string) =>
    request<{ authenticated: boolean; csrf_token: string }>("/api/admin/session", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),
  adminLogout: () => request<{ authenticated: boolean }>("/api/admin/session", { method: "DELETE" }),
  overview: () => request<Overview>("/api/admin/overview"),
  adminCase: (id: string) => request<AdminCase>(`/api/admin/applications/${encodeURIComponent(id)}`),
  reveal: (id: string) =>
    request<{ rows: ComparisonRow[] }>(`/api/admin/applications/${encodeURIComponent(id)}/reveal`),
  review: (
    id: string,
    body: { action: string; reason: string; expected_revision: number; expected_latest_run_id: string; confirmation?: string; items?: string[] },
  ) =>
    request<AdminCase>(`/api/admin/applications/${encodeURIComponent(id)}/review`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  documentPages: (id: string, runId: string, docType: string) =>
    request<{ pages: number; total_pages: number }>(
      `/api/admin/applications/${encodeURIComponent(id)}/runs/${encodeURIComponent(runId)}/documents/${docType}/pages`,
    ),
  documentPageUrl: (id: string, runId: string, docType: string, page: number) =>
    `/api/admin/applications/${encodeURIComponent(id)}/runs/${encodeURIComponent(runId)}/documents/${docType}/pages/${page}`,
  documentUrl: (id: string, runId: string, docType: string) =>
    `/api/admin/applications/${encodeURIComponent(id)}/runs/${encodeURIComponent(runId)}/documents/${docType}`,
};

export interface WorkflowPayload {
  creds: Credentials;
  fields: VendorFields;
  gst?: File | null;
  bank?: File | null;
  expected?: { revision: number; latest_run_id: string };
}

/**
 * POST a submission/correction and read the server's NDJSON stream. Every
 * `stage` message is a real pipeline callback forwarded by the API as it happens.
 */
export async function runWorkflow(
  payload: WorkflowPayload,
  onMessage: (message: StreamMessage) => void,
  signal?: AbortSignal,
): Promise<void> {
  const form = new FormData();
  form.set("application_id", payload.creds.application_id);
  form.set("tracking_code", payload.creds.tracking_code);
  for (const [key, value] of Object.entries(payload.fields)) form.set(key, value ?? "");
  if (payload.gst) form.set("gst_pdf", payload.gst, payload.gst.name);
  if (payload.bank) form.set("bank_pdf", payload.bank, payload.bank.name);
  if (payload.expected) {
    form.set("expected_revision", String(payload.expected.revision));
    form.set("expected_latest_run_id", payload.expected.latest_run_id);
  }
  const url = payload.expected ? "/api/vendor/resubmit" : "/api/vendor/applications";
  return streamRequest(url, { method: "POST", body: form }, onMessage, signal);
}

/** POST and read an NDJSON stream of real server events (stages, then a result or error). */
export async function streamRequest<M>(
  url: string,
  init: RequestInit,
  onMessage: (message: M) => void,
  signal?: AbortSignal,
): Promise<void> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(url, { ...init, headers, credentials: "same-origin", signal });
  } catch {
    throw new ApiError(0, "Your request could not be sent. Check your connection and try again.");
  }
  if (!response.ok || !response.body) {
    const body = await response.json().catch(() => null);
    throw new ApiError(response.status, detailOf(body, `Submission failed (${response.status}).`));
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    let chunk: ReadableStreamReadResult<Uint8Array>;
    try {
      chunk = await reader.read();
    } catch {
      throw new ApiError(0, "STREAM_INTERRUPTED");
    }
    if (chunk.done) break;
    buffer += decoder.decode(chunk.value, { stream: true });
    let newline = buffer.indexOf("\n");
    while (newline >= 0) {
      const line = buffer.slice(0, newline).trim();
      buffer = buffer.slice(newline + 1);
      if (line) onMessage(JSON.parse(line) as M);
      newline = buffer.indexOf("\n");
    }
  }
  if (buffer.trim()) onMessage(JSON.parse(buffer) as M);
}

/** Draft (before submit) or fix (after submit): the same reading endpoints under two bases. */
export type ReadingBase = "/api/vendor/draft" | "/api/vendor/fix";

export function uploadDraftFile(creds: Credentials, slot: Slot, file: File, onMessage: (m: DraftStreamMessage) => void,
  base: ReadingBase = "/api/vendor/draft") {
  const form = new FormData();
  form.set("application_id", creds.application_id);
  form.set("tracking_code", creds.tracking_code);
  form.set("slot", slot);
  form.set("file", file, file.name);
  return streamRequest<DraftStreamMessage>(`${base}/files`, { method: "POST", body: form }, onMessage);
}

export function moveDraftFile(creds: Credentials, slot: Slot, onMessage: (m: DraftStreamMessage) => void,
  base: ReadingBase = "/api/vendor/draft") {
  return streamRequest<DraftStreamMessage>(`${base}/move`, {
    method: "POST", body: JSON.stringify({ ...creds, slot }),
  }, onMessage);
}

export function submitDraft(creds: Credentials, onMessage: (m: StreamMessage) => void) {
  return streamRequest<StreamMessage>("/api/vendor/draft/submit", {
    method: "POST", body: JSON.stringify({ ...creds, declaration: true }),
  }, onMessage);
}

export function submitFix(creds: Credentials, onMessage: (m: StreamMessage) => void) {
  return streamRequest<StreamMessage>("/api/vendor/fix/submit", { method: "POST", body: JSON.stringify(creds) }, onMessage);
}
