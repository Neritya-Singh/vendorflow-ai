> **Update:** The side-by-side Admin Console described below has been superseded after visual review of actual screenshots. See `DESIGN_REASSESSMENT_HANDOFF.md`. The accepted refinement restores full-width evidence and a full-width reviewer decision panel while retaining safe row selection and a single explicit decision.

# VendorFlow AI v1.1 — Claude design refinement / implementation handoff

**Review basis:** `DESIGN_REFINEMENT_v1.md`, `proposed_theme.py`, and the Stage 6.4 source at GitHub commit `dd43efa`.

**Approval interpreted from conversation:** recommended Direction **B / Ledger Navy**, **Critical + High-impact** scope, isolated branch `stage6-v1.1-design`. No production merge, migration, or deployment.

## What is implemented

- New `vendorflow/theme.py` with Claude's navy/neutral/semantic tokens; replaces the previous incremental CSS in `app.py`. Streamlit's native theme is synchronized. `!important` overrides reduced to 36 in the proposed module (original Claude candidate had ~95).
- Status labels are plain text and accessible to assistive technologies; the result card also has semantic colour, an SVG icon and a visible label. Never use status colour alone.
- Form labels distinguish required legal name/email from optional contact; the Markdown bullet typo is fixed. Tracking and receipt pages explicitly label the private tracking code; `Persisted: True` and internal rule IDs disappear from vendor views.
- Welcome hero appears on Welcome only. The vendor sidebar is removed; staff sign-in is at the top, with existing `?portal=admin` and password checks unchanged. Welcome task panels pair descriptions with the actual action buttons.
- Vendor next-action ownership is phrased as "Waiting on: you / the review team". Corrections open in an expander when vendor action or technical retry is needed. Internal execution timeline is not on the vendor tracking screen; staff can still view it.
- Admin Needs Review metric is accented, queue cases are directly selectable using `st.dataframe(on_select="rerun", selection_mode="single-row")`, and review evidence + resolution form render side by side on larger screens. One explicit resolution is chosen before its single submit button appears; an evidence-reviewed checkbox is required only for approval.
- A strict selected-case helper rejects invalid/ambiguous/stale row selections. After a saved action, the queue widget is recreated under a fresh identity to avoid case selection carryover. The reviewer must still confirm the exact case ID and revision; no backend guards were changed.

## Safeguards

- No changes to `vendorflow/rules.py`, `vendorflow/persistence.py`, `vendorflow/gemini_extractor.py`, `vendorflow/pdf_reader.py`, `supabase/`, or authentication/tracking logic.
- Vendor-facing duplicate rule `R12` is still filtered from public checks; staff evidence remains available only in the authenticated admin interface.
- Real review actions still call `repo.admin_review` with `expected_revision` and `expected_latest_run_id`; source manifests and GSTIN database uniqueness remain unchanged.
- No `.env`, secrets, actual vendor data or original source PDFs in the patch.

## Verification in this environment

- **147/147** local automated tests pass: baseline **128** + **19** new design/UX regression checks.
- `python -m py_compile app.py`: PASS.
- Web documentation confirms row selection is supported by `st.dataframe`; its selection state is read-only. The implementation uses a fresh key after decisions rather than attempting to mutate selection state.
- **Not yet verified here:** real Streamlit rendering, mobile screenshots, and admin decisions on staging; those are required for final design approval before any merge into `main`.

## Desktop/mobile + admin acceptance (staging ONLY)

1. From the local design branch, confirm `.env` points to `https://hkxalnpnchzheorrogci.supabase.co` and uses **staging** secret, not production.
2. Run `PYTHONPATH=. python -m pytest -q` (expect **147 passed**), then `streamlit run app.py`.
3. Vendor, 390px + desktop: Welcome has clear actions; Step 1 required labels are correct and first field visible promptly; private code labelled before submission; receipt contains no debug text; Track lists human-readable checks; Pending correction can be resubmitted with the same ID.
4. Admin, `?portal=admin`: password required; select one Pending queue row; inspect its actual evidence and verified PDF; trigger a correction request; verify case selection clears after save.
5. Admin guard: Approval requires written reason, matching case ID confirmation and evidence-reviewed checkbox. Reject and Correction must NOT require the approval checkbox. Invalid/old case revisions cannot be committed.
6. Recheck on mobile: no horizontal form overflow, no clipped button or decision panel. Synthetic records only.
7. If accepted, commit/push **only `stage6-v1.1-design`**, not `stage6-v1.1-remediation` or `main`.

## Deferred items (not requested this round)

- Dynamic per-field correction highlighting, Step 3 upload/recovery panel reordering, and a bespoke mobile step progress bar.
- Broader production QA, browser matrix, WCAG keyboard/screenreader audits, and deployment: Stage 6.5.
