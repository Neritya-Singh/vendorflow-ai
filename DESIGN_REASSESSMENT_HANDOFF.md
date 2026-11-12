# VendorFlow AI — Design Reassessment and UI/UX Correction

**Target:** `stage6-v1.1-design`, based on Stage 6.4 `dd43efa`. **Do not merge or deploy**. All changes here are presentation/UX only, not rules, Gemini, storage, Supabase SQL, or auth.

## What was reviewed

- Two real Admin Console screenshots from 11 November 2026, showing a Rejected case and a Pending Review case.
- One-page PDF print of the new Vendor Welcome screen.
- Source code from both the original Stage 6.4 remediation interface and the Ledger Navy proposal, including current CSS, vendor fields, review/decision forms, and tests.

**Limits:** The screenshots only show the admin case overview and vendor Welcome. Vendor input/track/correct assessment also comes from source-code comparison, not a fresh recorded end-to-end user study.

## UX assessment

| Workflow | Pre-design v1.1 | First Ledger Navy design | Reassessment fix |
|---|---|---|---|
| Vendor entry | Clear actions, but a heavy heading and multi-step navigation | Shorter headings and large task actions, yet Welcome duplicates the same links in the tab bar | Hide duplicate tabs on Welcome; preserve task buttons; retain navigation on inner screens |
| Business entry | Step 1 worked, but field grouping was not consistent | Similar grouping: State beside email, contact name under State | Group contact email + contact person; State on a separate line |
| Small screens | Larger headline and step tiles | Compact typography, but three step tiles still crowd a phone | Visible **Step X of 3** label and compact progress bar on small screens |
| Vendor receipt and tracking | More technical text | Better, with clear recovery code and plain-language action | Keep the new improvements |
| Review queue | Required table-to-selectbox duplication | Single-click row selection and highlighted Pending KPI | **Keep** direct selection and no stale carryover |
| Admin evidence | Full-width; easiest for comparing submitted and extracted fields | Two-column layout compresses evidence to ~2/3 of available space | Restore **full-width evidence and comparison table** |
| Final cases | Full-width read-only case | Rejected/Approved cases leave unused decision column space | Full-width read-only case; no decision form on terminal cases |
| Admin findings | Long cards | Long stack of identically styled cards | Actual FAIL before UNKNOWN; show three initially; others expandable; clear action wording |
| Admin decision | Full width, three equal action buttons | Safer single explicit choice, but narrow sidebar and tiny helper text | Full-width bordered decision desk; retain explicit choice, case confirmation and approval checkbox |

## Readability fixes

- Keep navy primary `#1E3A8A` with unchanged green/amber/red semantic outcomes.
- Increase helper/caption font size to 14 px, admin issue details to 15 px, and darken subtitles.
- Darken token `subtle` from `#667085` to `#475467` and `muted` from `#475467` to `#344054`.
- Measured contrast against the `#F6F7F9` canvas: subtle **7.17:1**, muted **9.76:1**, navy primary **9.66:1**; input border remains **3.04:1**.
- Each nonpassing reviewer check has an explicit `Correction needed` or `Not yet verified` label in addition to its border/accent colour.

## Implementation constraints respected

- No modifications to deterministic decision rules, vendor authentication, application status definitions, SQL triggers/migrations, PDF provenance, Gemini retries, or Supabase environments.
- Backend reviewer call still provides `expected_revision` and `expected_latest_run_id`, with explicit case ID confirmation and approval-only evidence acknowledgement.
- Only Pending applications with saved runs may receive a reviewer action.
- R12 duplicate screening remains staff-only.
- Vendor recovery credentials are still presented before the first durable write.
- No `.env`, staging secrets, screenshots or actual vendor documents in the patch.

## Verification

- Baseline Ledger Navy design: **147 passing tests**.
- Updated UI and 13 new offline reassessment checks: **160 passing tests**.
- Passed `python -m compileall` on modified Python files.
- A clean-overlay check applies the patch to the original Ledger Navy full project and reruns the tests.
- **Not verified in this environment:** live Streamlit browser rendering of this revision, final reviewer UI behavior on staging, keyboard/screenreader audit. Those remain required before committing/merging or any production release.

## How to apply and review (staging only)

1. Ensure your **current checkout already contains the earlier Ledger Navy design**, and is on `stage6-v1.1-design` (not `stage6-v1.1-remediation` or `main`). Check `git branch --show-current` and `git status --short`.
2. Unzip `VendorFlow_Design_UX_Refinement_Patch.zip` into the root of that checkout. It touches only `app.py`, `vendorflow/theme.py`, `vendorflow/ux_support.py`, a new test, and design handoff files.
3. Run `PYTHONPATH=. python -m pytest -q` (expected **160 passed**) and `git diff --check`.
4. Restart `streamlit run app.py`. Check Vendor Welcome, new-application Step 1 desktop/mobile, and the three-step indicator on a 390 px mobile view.
5. Open `?portal=admin` with your **staging** configuration. Select a Pending case, inspect the **full-width** comparison table, choose an action, and confirm the single full-width decision area has readable text. Inspect a Rejected case: it must have **no empty right column** and **no action form**.
6. Verify a correction request still requires a reason and case confirmation, Approve additionally needs evidence acknowledgement, and selecting a new case clears the old selection after a decision.
7. Only after browser acceptance: commit to `stage6-v1.1-design`. Do **not** merge to production `main` or deploy.

## Release note

The user-provided screenshots and the proposed design introduced real product/UX insights. The new source fixes specific observed layout and readability regressions but should not be represented as a measured reduction in application processing time without comparative user testing.
