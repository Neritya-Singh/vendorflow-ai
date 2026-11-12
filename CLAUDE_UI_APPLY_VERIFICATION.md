# VendorFlow AI — Claude UI corrections, reconciled and verified

## Provenance
- Source: user-provided `VendorFlow_UI_final.zip` and `VendorFlow_UI_final.patch`.
- Base: the previous isolated design UI, reconstructed from its complete package and two successive microfix overlays.
- The submitted patch applied without conflicts. However, its `tests/test_stage6_design_refinement.py` content differed from the corresponding file in the submitted ZIP and contained two obsolete navigation assertions. The ZIP's corrected test was used as the source of truth.
- The reconstructed complete project includes the original synthetic `fixtures/` folder and `.env.example` (missing from Claude's ZIP).

## Source changed
- `.streamlit/config.toml` — native Streamlit theme tokens, controls and typography.
- `app.py` — vendor labels, status and recovery cards, admin navigation, review flow.
- `vendorflow/theme.py` — scoped Streamlit 1.66 styles, accessible field borders, captions.
- `tests/test_stage6_design_microfix.py` — updated UI behavior checks.
- `tests/test_stage6_design_reassessment.py` — updated UI behavior checks.
- `tests/test_stage6_design_refinement.py` — corrected ZIP version of the navigation test.
- `tests/test_stage6_ui_final.py` — Claude's 18 new tests plus one extra reviewer-safety test.

## Additional correction
Moved the *verified, committed-version PDF download* section in the Admin Console to appear after the submitted-vs-extracted comparison and **before** the decision form, instead of beneath it. This reduces the risk of approving without inspecting the underlying evidence. The existing `load_run_document()` verification, case guards and revision locking are unchanged. One regression test covers ordering and bound document loading.

## Verification performed
- Patch applied cleanly to the reconstructed design baseline.
- All **186 offline tests passed** when running with a dummy Streamlit module import for a CSS source-inspection test. This environment cannot install Streamlit 1.66.1, so a real Streamlit runtime was **not** tested here.
- Python compileall succeeded.
- Verified modified files are limited to the seven source/test paths above; backend rules, persistence, Gemini processing, schemas/migrations and credentials were not changed.
- No remote branch, staging database, production database or deployment was modified.

## Local acceptance required
1. Use `stage6-v1.1-design`, never `main`.
2. Run `PYTHONPATH=. python -m pytest -q` in the user's installed virtual environment (expected **186 passed**).
3. Start `streamlit run app.py` with staging-only `.env` settings.
4. Check vendor new → receipt → track/correct, admin sign-in → queue → PDFs → decision → log out, desktop and mobile; copy controls and dropdown focus.
5. Commit to design branch only after manual acceptance; do not merge or deploy until final release approval.
