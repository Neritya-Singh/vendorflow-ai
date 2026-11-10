# VendorFlow AI — Phase 3 Development Tracker

Updated: 2026-11-05. The last confirmed live actions were performed by the user on their Supabase project.

| Stage | Status | Evidence / blockers |
| --- | --- | --- |
| 3.1 Backend | ✅ Completed | Real Gemini happy path APPROVED; 14 deterministic checks passed |
| 3.2 Testing | ✅ Completed | Four real Gemini edge cases passed; 23 foundational offline tests |
| 3.3 Supabase | ✅ Completed | Live persisted happy path, private bucket verification, DB-backed duplicate flag, pending→approved correction with two immutable runs and bank PDF versions 1/2, admin request/approve/reject actions with one audit record each and a verified pending queue. |
| 3.4 Streamlit frontend | 🟡 In Progress | Vendor and Admin UI code prepared; 36 local offline tests passed across backend and UI helpers. Browser/server acceptance pending. |
| 3.5 UI/UX improvements | ⚪ Not Started | Review usability after functional UI tests |
| 3.6 GitHub + Streamlit Cloud deployment | ⚪ Not Started | Requires GitHub repo and deployment secrets; fresh-browser verification needed |

## Immediate next step

Download and merge Stage 3.4 frontend add-on into user's existing project, install dependencies, run 36 tests, and confirm. Then configure `ADMIN_PASSWORD`, launch `streamlit run app.py`, and perform the first live browser test.

## Notes

- All data are synthetic; Approved is document-consistency policy, not legal/GST/bank verification.
- Public demo must not use real financial documents.
- Existing API keys and tracking codes should never be pasted into chat.


## Stage 6.2 — Staging-only development update (2026-11-10)

- Code implemented locally: revision CAS, run-linked source-PDF manifests, immutable PDF metadata, recoverable initial receipt/idempotent retry, and lost run-ack recovery.
- Full offline suite: **82/82 passing**. Includes all Stage 6.1 regressions and the four previously RED Stage 6.2 tests.
- Staging migration `stage6_2_revision_provenance_recovery` applied; read-only checks show all four tables empty and new columns/trigger present.
- **Pending manual gates:** run `supabase/stage6_2_sql_smoke_rollback.sql` in staging and `scripts/stage6_2_concurrency_gate.py` with staging credentials. Real Supabase Storage API fault tests are still an E2E release prerequisite.
- **Not yet committed to GitHub**; production GitHub `main`, database and Streamlit deployment remain unchanged.
