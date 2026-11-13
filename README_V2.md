# VendorFlow AI v2 — React + FastAPI

v2 replaces the Streamlit UI with a React SaaS frontend. The decision logic does not change: the
**v1.1 Python rules, Gemini extractor, Supabase repository and presentation helpers in `vendorflow/` are
reused unmodified** through a thin FastAPI adapter. The v1.1 Streamlit app (`app.py`) still runs and is
untouched; its public deployment is not affected by this branch.

```
React (Vite, TS, Tailwind)  ──/api──▶  FastAPI adapter (backend/)  ──▶  vendorflow/ (v1.1, unchanged)
   vendor workspace                     auth · throttling · uploads        pipeline · rules · Gemini
   live stage view                      NDJSON stage stream                SupabaseRepository
   admin console                        vendor-safe view models            PersistentVendorService
```

## What's in it

| Area | What it does |
| --- | --- |
| Vendor workspace | Home with *Start application* / *Track existing application*; three steps (Business → Banking and PDFs → Review and submit), with the draft held in memory |
| Live processing | The nine real stages (S1 intake … S9 persistence) stream from the server as the Python pipeline emits them, with server-measured durations. No simulated progress. |
| Decision receipt | Approved / Pending Review / Rejected, the main reasons and one next step, plus the application ID and one-time tracking code with copy buttons |
| Tracking & correction | ID + private code; reviewer message, checks, history, documents on file; edit pending details and replace PDFs (same application ID, old evidence kept); one-click retry when document processing was unavailable |
| Admin console | Password sign-in → HttpOnly session; workload metrics from saved records; Pending-first queue with filters and search; case page with failed checks, masked submitted-vs-PDF comparison (reveal on demand), exact PDF versions per run, run/stage history, reviewer actions; Approve / Reject / Request correction behind a confirm dialog |

### Photos and scans (B7)

Draft and fix uploads accept PDF, JPG and PNG up to 5 MB (type checked by extension **and** magic
bytes; images over 40 MP are refused). Text PDFs are read as before. For a photo or an image-only
(scanned) PDF, `vendorflow/v2_scan.py` renders the pages and runs **local Tesseract OCR**; that OCR text
is the grounding text R13 checks every extracted value against. The values themselves come from
Gemini's **image input** (`GeminiExtractor.extract_images`); the image is rebuilt from pixels first, so
no EXIF, GPS or comments are sent, and the OCR text is not sent. If OCR can't confirm a value, R13
fails and the vendor is asked for a clearer copy (fail closed). If Tesseract is missing, the file is
marked "couldn't read just now" (our side) and the case goes to the team, never approved.
The original file is stored as evidence. Staging needs
`supabase/migrations/20261113_b7_bucket_image_types.sql` (not applied yet). The Docker image installs
`tesseract-ocr`; locally run `sudo apt-get install -y tesseract-ocr tesseract-ocr-eng`.
On phones, "Take photo" opens the rear camera; a photo over 5 MB (or HEIC) is re-encoded to JPEG in the
browser before upload.

### How the live stage view works

`POST /api/vendor/applications` (and `/api/vendor/resubmit`) runs `PersistentVendorService` in a worker
thread. Its `stage_callback` pushes each real `StageEvent` (S1–S8 from `ProcessingPipeline`, S9 from
`SupabaseRepository.commit_run`) onto a queue. The response streams those events as **NDJSON** lines,
then a final `result` (or a safe `error`). The browser reads the stream with `fetch` and updates a stage
only when its event arrives. If the connection drops, the worker still finishes and saves. Credentials
are issued *before* any write (the v1.1 recovery contract), so the vendor checks status by tracking.
Retrying with the same credentials is idempotent.

## API surface

| Endpoint | Auth |
| --- | --- |
| `GET /api/health`, `GET /api/meta` | public, no secrets (booleans only) |
| `POST /api/vendor/intake` | public; issues an ID + code, writes nothing |
| `POST /api/vendor/applications` (multipart) | new ID, or the existing ID **plus its tracking code** |
| `POST /api/vendor/track` | ID + tracking code (throttled: 10 failures / 15 min / client) |
| `POST /api/vendor/resubmit` (multipart) | ID + tracking code + expected revision/run |
| `POST /api/vendor/draft`, `/draft/files`, `/draft/move`, `/draft/remove`, `PUT /draft/values`, `POST /draft/submit` | ID + tracking code; upload-first draft (no runs yet) |
| `POST /api/vendor/fix`, `/fix/files`, `/fix/move`, `PUT /fix/values`, `POST /fix/submit` | ID + tracking code; only while the case is waiting on the vendor. Shows only the requested items; re-check reuses every reading |
| `POST/GET/DELETE /api/admin/session` | password → signed HttpOnly SameSite=Strict cookie; 5 failures → 15-min lock |
| `GET /api/admin/overview`, `/applications/{id}`, `/applications/{id}/reveal` | admin cookie |
| `GET /api/admin/applications/{id}/runs/{run}/documents/{GST\|BANK}` | admin cookie; streams the hash-verified committed PDF, `no-store` |
| `POST /api/admin/applications/{id}/review` | admin cookie + `X-CSRF-Token`; optimistic revision check |

There is no public listing or enumeration endpoint. Vendor views never include R12 identity-screening
results, other case IDs, raw rule codes or the token hash. PDFs are never exposed through public URLs.

## Run locally

Requirements: Python 3.12+ (tested on 3.14), Node 22.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cd frontend && npm ci && npm run build && cd ..
cp .env.example .env      # then fill in STAGING values locally — never commit .env
.venv/bin/uvicorn backend.main:app --port 8000     # serves API + built app at http://127.0.0.1:8000
```

For frontend development with hot reload, run the API as above and `cd frontend && npm run dev`
(http://localhost:5173; `/api` is proxied to :8000, so cookies stay same-origin). With `COOKIE_SECURE=1`
the admin cookie needs HTTPS or `localhost`; set `COOKIE_SECURE=0` only for plain-http local testing.

### Offline test mode (no credentials)

```bash
ADMIN_PASSWORD='choose-a-local-password' scripts/v2_offline_servers.sh
```

This starts two servers:
- **:8000** — the real PDF reader, rules, pipeline and `SupabaseRepository` code, with an **in-memory
  Supabase double** and a **label-reading test extractor** in place of Gemini.
- **:8001** — the same, but with the **real `GeminiExtractor` and no API key**, which exercises the
  genuine provider-failure path.

A banner marks offline mode in the UI. Records vanish on restart. Offline mode refuses to start if
`SUPABASE_URL` is set. Passing tests in this mode do **not** prove the real Postgres triggers, RLS,
Storage privacy or Gemini extraction work.

## Tests

```bash
.venv/bin/python -m pytest -q                       # 195 v1.1 tests + 18 v2 API tests
cd frontend && npm run lint && npm run typecheck && npm test && npm run build
# Browser end-to-end (Chrome), against FRESH offline servers from the script above:
ADMIN_PASSWORD_FILE=/path/to/file-with-password UNREADABLE_PDF=/path/to/text-less.pdf npm run e2e
```

The e2e run drives real Chrome through the UI and covers:
- happy path → Approved
- bank-holder mismatch → Pending → reviewer requests a correction → vendor corrects and replaces the bank PDF → re-run → Approved
- swapped PDFs → Pending
- unreadable bank PDF → Pending
- Gemini failure → truthful "temporarily unavailable" plus retry
- wrong tracking code rejected
- unauthenticated admin blocked
- final application cannot be resubmitted
- PDF download, masking, mobile overflow, keyboard skip link, no console errors

Screenshots are saved to `frontend/e2e/artifacts/`. The suite expects a fresh store: a second run against
the same server correctly routes the reused fixture GSTIN to Pending through duplicate screening.

## Deploy (one service)

`Dockerfile` builds the React app and runs a single FastAPI container that serves `/api/*` and the SPA
(no CORS, one host). Set these as **host-managed secrets**, never as Vite `VITE_*` variables:
`GEMINI_API_KEY`, `GEMINI_MODEL`, `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `ADMIN_PASSWORD`,
`SESSION_SECRET`, and `TRUST_PROXY=1` behind the platform proxy. Any Docker host works (Render, Fly.io,
Cloud Run, Railway). Use a **new URL**: the Streamlit v1.1 submission URL stays as is. Deploying requires
the owner's approval.

## Limitations (honest)

- Admin access is one shared demo password with a signed session cookie — not an identity provider (no
  per-user accounts, MFA or server-side session revocation; rotating `SESSION_SECRET` or the password
  signs everyone out). The reviewer actor is recorded as `demo-admin`, as in v1.1.
- Throttling is in-process memory: it resets on restart and isn't shared across multiple instances.
- "Approved" means the submission is consistent with the uploaded PDFs under the prototype policy. It is
  not KYC/KYB, a GST registry lookup or bank-ownership verification.
- The admin overview loads up to 1,000 runs and reviewer actions (prototype scale).
- Photos: OCR is English-only Tesseract with simple lighting correction; it is tuned on synthetic
  fixtures, not real phone photos. Offline tests use a Gemini stand-in that reads the fixture's embedded
  ground truth instead of pixels; real Gemini image reading has not been tried yet.
