# VendorFlow AI v2

VendorFlow AI is a vendor-onboarding prototype for PS-2: onboarding Indian GST-registered vendors. A vendor uploads a
GST registration certificate and a bank document (PDF, scan or phone photo of a cancelled cheque). The app reads the
details for them, checks them, and returns Approved, a clear list of what to fix, or "with our team" for a reviewer.
All companies, documents and numbers are **synthetic**. A decision means the details are consistent with the uploaded
documents under the prototype policy. It is not KYC/KYB, a GST registry lookup or bank-ownership verification.

- **Live app:** https://vendorflow-ai-l4jb.onrender.com (staff console: "Staff console" link in the footer)
- **Demo video:** `<placeholder>`
- **Submission files (brief, demo material):** https://drive.google.com/drive/folders/1oIpbBTffRelDgmFskULlopPzWX8vBcd4?usp=sharing
- **Earlier version (v1.1, Streamlit):** [`main` branch](https://github.com/Neritya-Singh/vendorflow-ai/tree/main) ·
  [v1.1 app](https://vendorflow-ai-zamp-submission.streamlit.app/)
- **Full technical notes:** [README_V2.md](README_V2.md)

## How it works

- **Upload first.** The vendor starts with their two documents, not a form. Wrong slot? "Move it" swaps them, with no re-upload.
- **AI reads, OCR confirms.** Gemini reads each document once. For photos and scans, local Tesseract OCR must find every value Gemini read, or the vendor is asked for a clearer copy (fail closed).
- **Rules decide.** Deterministic rules decide, never the model: formats, GSTIN check digit and state code, name and account matches, values the vendor edited, and records checks across all applications.
- **Three outcomes.** **Approved**; **Action needed from you** (exactly what to fix, then re-check with the same ID); or **With our team** (the vendor sees neutral text).
- **Reviewer console.** A risk-sorted queue, the reason a case is there, both values side by side, the original documents, and Approve / Request correction / Reject with an audit trail.

## Edge cases handled

| Situation | What happens |
|---|---|
| Documents in the wrong slots | Both slots warn; one "Move it" fixes both; no new reading |
| Unrelated or unreadable file, blank scan | "We couldn't find / read…"; Continue blocked until replaced |
| File that isn't what its name says | Refused at upload |
| Blurry cheque photo | "Upload a clearer copy"; the retake is checked on the same application |
| GSTIN with a wrong check digit or length, state ≠ GSTIN state code | Shown on the field; Continue blocked |
| Bank holder ≠ legal name | With our team ("Pvt Ltd" = "Private Limited" is accepted) |
| Vendor edits a value read from a document | With our team, both values shown |
| Same GSTIN as an approved vendor, different bank (payment diversion) | With our team, high risk; vendor sees neutral text |
| Bank account used under another GSTIN | With our team, high risk |
| Gemini unavailable | Honest "temporary problem on our side"; never a silent approval |
| Photo metadata (EXIF/GPS) | Stripped from the stored file and from what Gemini receives |

## Tech stack

React + TypeScript + Vite + Tailwind (frontend) · FastAPI on Python 3.12 (one service, also serves the app) · Google
Gemini (document reading) · Tesseract OCR + PyMuPDF (photos and scans) · Supabase Postgres (triggers keep runs and
documents immutable) + private Storage bucket · Docker on Render (Singapore).

## Run locally

Requirements: Python 3.12+, Node 22, `tesseract-ocr`.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cd frontend && npm ci && npm run build && cd ..
cp .env.example .env        # fill in your own staging values; never commit .env
.venv/bin/uvicorn backend.main:app --port 8000      # http://127.0.0.1:8000
```

No credentials? `ADMIN_PASSWORD='choose-a-local-password' scripts/v2_offline_servers.sh` starts an offline test mode
(in-memory database, a stand-in for Gemini). Tests: `.venv/bin/python -m pytest -q` and
`cd frontend && npm run lint && npm run typecheck && npm test`. Database setup: `supabase/schema.sql`, then `supabase/migrations/`.

## Environment variables (names only)

`GEMINI_API_KEY`, `GEMINI_MODEL` (optional), `SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `ADMIN_PASSWORD`, `SESSION_SECRET`,
`TRUST_PROXY` (`1` behind Render's proxy), `COOKIE_SECURE` (default on), `PORT` (set by Render). Optional:
`WORKSPACE_NAME`, `ADMIN_SESSION_HOURS`. Never set `VENDORFLOW_OFFLINE_MODE` in a deployment.

## Known limitations

- Not KYC/KYB: no GST registry lookup and no bank-ownership check (e.g. penny drop).
- One shared reviewer password, with no per-user accounts or MFA. The reviewer is recorded as `demo-admin`.
- OCR sometimes confuses look-alike characters (`O`/`0`) on a clear photo. It fails closed, but asks for a needless retake.
- Gemini response time varies (about 2–17 s per photo); it is most of an upload's wait.
- Rate limits and the document cache live in one server's memory: they reset on restart and aren't shared across instances.
- An approved GSTIN can be approved only once, so each demo case runs once per database (use fresh synthetic files).

## Next steps

- Confusable-tolerant OCR comparison (O/0, I/1) so clear photos never need a retake.
- Real verification: GSTN lookup and bank penny-drop, behind the same rules.
- Per-reviewer sign-in (SSO), roles and email notifications to vendors.
- Shared rate limiting and caching (e.g. Redis) for more than one instance; a Gemini timeout and fallback.
