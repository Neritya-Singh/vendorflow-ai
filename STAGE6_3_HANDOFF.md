# VendorFlow AI v1.1 — Stage 6.3 UX and reviewer workflow

**Prepared:** 11 November 2026
**Scope:** Streamlit vendor and admin workflows only; no schema changes, model changes, or new decision status.
**Target:** `stage6-v1.1-remediation` branch; never production `main` until Stage 6.5.

## Implementation

1. Added a **vendor welcome screen** with two clear paths: new application and track/correct. Staff sign-in remains a separate password-guarded portal.
2. The first successful submission **reruns into one result/receipt screen** instead of leaving the submitted form and a duplicate result visible. Recovery credentials are issued before a write and shown on the receipt. A button uses a Streamlit callback to open authenticated tracking for that receipt.
3. Tracking prominently identifies the **next action owner** (Vendor, Reviewer or Technical retry; **not** a new decision status), along with a plain-language next step. An expired correction request no longer displays as active after a newer run.
4. Correction save **refetches the current authoritative status/run** via rerun; no misleading “refresh manually” instructions. Prior committed PDFs are reused unless explicitly replaced. Correction/technical retry is deliberate, not automatic.
5. Early email format guidance on first-step and correction screens. The deterministic backend remains authoritative.
6. Admin's exception-first queue now adds **action owner, primary issue and age** based on the saved run referenced by each application; age is time since submission, **not SLA**. Staff-only checks show saved evidence including R12; vendor checks continue to suppress R12 and linked application IDs.
7. Staff can explicitly load **private, SHA-256-verified PDFs bound to the case's latest committed run**. No public URLs or staged/uncommitted document selection. Failed verification shows an error instead of a download.
8. Manual approval UI requires an additional acknowledgement of evidence review, plus the existing required reason/case ID confirmation. Database revision-locking remains the actual stale-action protection.
9. Mobile CSS for the welcome panels and already-existing responsive form/queue are preserved.

## Offline evidence

`PYTHONPATH=. python -m pytest -q` → **99 passed** (all 82 prior tests plus 17 Stage 6.3 tests).

`python -m compileall -q app.py vendorflow tests` → no syntax errors.

**Boundaries:** The local evaluation environment does not have Streamlit installed or access to the owner's staging Streamlit/Gemini credentials; therefore desktop/mobile browser acceptance and realistic vendor-to-reviewer navigation are **not yet verified**. Do not mark Stage 6.3 complete solely from offline tests.

## Manual staging acceptance gate (synthetic documents only)

Before running locally, set `.env` inside the *development checkout* to the **staging** Supabase URL and staging service secret (never share or commit). Set `GEMINI_API_KEY`, `GEMINI_MODEL`, `ADMIN_PASSWORD` locally. Preserve an encrypted offline copy of existing `.env` or use a separate `.env` for the development clone. Production secrets must never be reused in staging.

1. From the development checkout: `source .venv/bin/activate`; `python -m pip install -r requirements.txt`; `streamlit run app.py`. Browser fresh session at the printed URL.
2. At approximately **1366 × 768**: the welcome screen presents two clear paths. Start a new application and verify that invalid email is flagged before proceeding, and that business / bank / PDFs are easy to find. Upload **synthetic** GST and bank PDFs. Record ID/code privately; submit once. After saving, only one receipt/result should display; use **Track this application**.
3. Submit an EC2/EC3-style synthetic Pending case. Track its reasons and next-action owner; edit only the incorrect field or PDF; resubmit once. Confirm new status and run count display **without manual refresh**, and latest run refers to exact latest committed PDF versions. Confirm previously committed PDFs are reused only when left unchanged.
4. Open `?portal=admin`. Authenticate with the **staging-only** password. The queue should show action owner, issue and age. Open a pending case. Verify staff-only R12 evidence is absent from vendor views. Click **Load this run's verified PDFs**, inspect one download, and confirm it belongs to the correct run. Try Request correction with an explicit reason and case-ID confirmation, then check the vendor's current tracking view. Test manual approval and rejection on distinct eligible synthetic cases; the approval checkbox must be required.
5. Test desktop ~1280px wide and mobile ~375px wide. Check that fields, choices, review actions, and uploaded PDF controls remain usable without horizontal overflow or overlapping navigation. Check tab/keyboard access and labels. Log screenshots and defects.
6. Reopen in a fresh browser session and verify tracking works using the same ID/code (session state alone is not persistence). Validate that manually entering a wrong tracking code reveals no case details.
7. After the test, remove synthetic staging objects and rows using a carefully scoped cleanup plan. **Do not blindly delete records if other staging tests are present.**

**Release gate:** vendor happy path and EC2/EC3 correction complete in the actual browser, authorized admin review + evidence download correct, no duplicate saves, no privacy leak, and both desktop and mobile usable. If any fails, keep Stage 6.3 open and fix before Stage 6.4.

## Files changed in Stage 6.3

- `app.py`
- `vendorflow/ux_support.py` (new)
- `tests/test_stage6_3_ux.py` (new)
- `PROGRESS.md`
- `README.md`
- `STAGE6_3_HANDOFF.md` (this document)

Do not copy, commit or share `.env`, `.venv`, Streamlit secrets, database passwords, live PDF records or API keys.
