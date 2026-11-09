# VendorFlow AI — Phase 2: Workflow & System Design

**Version:** 1.0 — proposed for product-owner lock  
**Date:** 4 November 2026  
**Predecessor:** `01_Product_Requirements_VendorFlow_AI.md` — Phase 1 approved  
**Assignment:** Zamp AI | PS-2 Vendor Onboarding  
**Build constraint:** Approximately one working day; runnable public demo required.

## 0. Source of truth and design goal

Zamp's official guide (pp. 2, 4, 6–7) asks for an actual automated process that accepts a vendor submission, returns **approved/pending/rejected with visible reasons**, communicates what is needed for non-approvals, demonstrates **2–4 meaningful edge cases**, displays **live execution stages and run history**, and can be shown in a **≤5-minute narrated demonstration**. Its strongest advice is to map the process first and build the happy path before edge cases. This design implements the approved Phase 1 PRD with India-only/GST-registered/private-company assumptions; it does not provide official KYC/KYB.

**North-star outcome:** Reduce manual analyst handling by automatically resolving clean, document-consistent applications and giving both personas one-action guidance when a case needs review.

## 1. Operating assumptions and scope

- Customer: one fictional Indian private company's Finance/Procurement team.
- Vendors: Indian GST-registered businesses, domestic bank accounts, synthetic/sample data ONLY.
- Required documents: GST registration certificate PDF plus a cancelled-cheque PDF OR bank-confirmation-letter PDF. **Happy-path fixture uses a bank letter**, since a cancelled cheque may not always contain all fields; absence routes to pending review.
- Vendor-facing and admin-facing interfaces live in the same Streamlit application but have distinct entry points and access boundaries.
- No live external tax, bank ownership, sanctions, payment, or government procurement verification.
- Three external outcomes: **Approved**, **Pending Review**, **Rejected**. These implement Phase 1's "Accepted / Under Review / Rejected" language: Approved = Accepted, Pending Review = Under Review. Internal technical states (e.g., processing or error) are NOT extra onboarding decisions.
- "Approved" means **passed a documented sample-company document-consistency policy only**, not that vendor identity was independently verified.
- All test inputs and outcome claims will be honestly labelled synthetic/prototype.

## 2. Core user journeys

### Vendor — first submission

1. Open **Vendor Portal** → select **New application**.
2. Complete three short sections: **Business details → Bank details → Documents & review**. Show current-step arrow and ticks for completed sections; avoid displaying all form fields at once.
3. Review a compact summary and click **Check application** once.
4. UI reflects real running stages: Received → Read documents → Check data → Decide → Save result.
5. Show big status banner and **up to 3 priority reasons** in plain English; provide a link/expander for full checks.
6. If approved: provide ID and tracking code; if pending: show **Fix now** and exactly which fields/documents to correct; if rejected: show admin's reason and contact/escalation guidance.

**Minimum intake:** legal business name and contact email (needed to create and retrieve a recognisable application). Other empty fields/documents may be submitted **with a warning**, creating a Pending Review outcome; that enables meaningful incomplete-document test cases. Malicious/oversized/non-PDF uploads are declined safely before processing.

### Vendor — return and correct

1. Open **Track / correct application** → enter **application ID + tracking code**.
2. See latest status, priority issues, and correction action.
3. Edit flagged fields and/or replace affected document; preserve previous values by default.
4. Click **Resubmit for checking** → a **new run** executes against the updated application. The prior run remains immutable.
5. See fresh outcome; avoid treating the resubmission as a second vendor for duplicate detection.

### Administrator — exception first

1. Open **Admin Console** → authenticate with a demo admin password (stored in deployment secrets; don't put it in public files).
2. See KPI row and **Pending Review** queue first, sorted by oldest unresolved (or severity) so work is prioritised.
3. Open a case; view a **side-by-side claimed vs extracted** field comparison, failed-check reasons, uploaded-file identity, and immutable execution timeline.
4. Pick one action: **Approve after manual review**, **Request correction**, **Reject**. Require a written rationale for manual approval or rejection; a request for correction gets an actionable vendor-facing message.
5. Record decision as an audit event; update vendor-visible status immediately. A manual approval must be labelled "Approved after human review".

## 3. Complete processing pipeline

```text
Vendor submits form + two PDF files (or missing-file exception)
          |
  S1  Accept intake + allocate Application ID / tracking secret
          |
  S2  Validate attachment metadata + read PDF text (PyMuPDF)
          |
  S3  AI extracts field data into a strict JSON schema
      (use one Gemini request for the two textual documents where possible;
       scanned/unreadable input is review-bound unless multimodal parse succeeds)
          |
  S4  Normalize values (trim, case, common whitespace/punctuation)
          |
  S5  Run independent deterministic validation checks
          |           
  S6  Lookup already APPROVED records with matching GSTIN
          |
  S7  Policy engine makes decision
        |                         |
    All checks PASS           Any unresolved discrepancy,
    and no duplicate         missing critical evidence,
        |                    duplicate or API failure
        v                         v
    APPROVED                 PENDING REVIEW
                                  |
                            admin decision / vendor correction
                                  |
                            APPROVED | PENDING | REJECTED
        \_________________________/
                    |
  S8  Generate reason codes + deterministic plain-English messages
          |
  S9  Persist immutable run, stage events, checks, final status
          |
  S10 Present result; dashboard reflects new run
```

**IMPORTANT implementation order:** Build and test the clean S1→S10 path first; add the four exceptions sequentially. Fail-safe: no extraction/API/storage error may produce an Approved status. If persistence fails, show an honest technical error and do not claim the decision was saved.

## 4. Final field and document specification

| Form field | Format / purpose | Required for automatic approval? |
|---|---|---|
| Legal business name | non-empty text | Yes |
| Business state | Indian state/UT dropdown | Yes |
| Contact name | non-empty text | Yes |
| Contact email | standard address validation | Yes |
| PAN | uppercase string of ten characters | Yes |
| GSTIN | uppercase string of fifteen characters | Yes |
| Bank account holder name | text | Yes |
| Bank account number | **string** (preserve leading zeroes), non-empty | Yes |
| IFSC | uppercase eleven-character string | Yes |
| GST certificate | real readable PDF | Yes |
| Bank letter or cancelled cheque | real readable PDF | Yes |

Extract from GST PDF: GSTIN, legal name, state, optional address. Extract from bank proof: account holder, account number, IFSC (when available). Every extracted key is `string | null`, identifies source file and extraction status, and never substitutes a guessed value for missing evidence. Capturing the PDF filename and text evidence is sufficient; page citations are displayed only if reliably located rather than invented.

Document limit: PDF only, maximum 5MB per file for demo. API secrets remain server-side. Missing critical document data => Pending Review with a specific message.

## 5. Validation-rule catalogue

| Rule ID | Check | Pass condition | Failure treatment |
|---|---|---|---|
| R01 | Required application fields | All present for approval | PENDING; list missing fields |
| R02 | PDF attachments | GST PDF and supported bank PDF readable | PENDING; request upload/replacement |
| R03 | PAN format | `^[A-Z]{5}[0-9]{4}[A-Z]$` | PENDING; correct PAN |
| R04 | GSTIN structure | 15 chars; 2-digit state code + PAN structure + entity/14th/15th format | PENDING; correct GSTIN |
| R05 | Embedded PAN check | GSTIN chars 3–12 == submitted PAN | PENDING; highlight difference |
| R06 | GSTIN state check | first two digits correspond to selected business state | PENDING; clarify state/GSTIN |
| R07 | IFSC structure | `^[A-Z]{4}0[A-Z0-9]{6}$` | PENDING; correct IFSC |
| R08 | GST certificate identity | form GSTIN == extracted GSTIN and normalized legal names agree | PENDING; show differences |
| R09 | Bank account comparison | typed account number == extracted bank proof number | PENDING; require document correction |
| R10 | Bank IFSC comparison | typed IFSC == extracted bank proof IFSC | PENDING; require correction |
| R11 | Bank holder comparison | normalized bank holder name matches claimed name; discrepancy with legal entity triggers review rather than blind rejection | PENDING; ask admin to examine ownership evidence |
| R12 | Existing approved GSTIN | no *other* approved application with same GSTIN | PENDING; flag possible duplicate for admin |
| R13 | Extraction completeness | all critical fields extracted or deterministically available from documentary evidence | PENDING; missing fields clearly listed |
| R14 | Execution safety | API/storage operations complete without unhandled error | controlled error / PENDING if saved; never approve |

Normalization: case-insensitive, whitespace collapse, nonmaterial punctuation normalization only. Never fuzzy-auto-approve two materially different legal names. Preserve account numbers as strings. Structural validation **does not** verify real PAN/GSTIN registrations or existence/ownership of an IFSC/account. The 15th GSTIN character can be checksum-validated if correctly implemented/tested but is not essential to the MVP; format is not an authenticity test.

**Input vs document rule:** GST legal name, GSTIN and state must be internally consistent. A GST certificate may contain trade name as well as legal name; compare legal-name to legal-name, never equate trade name by default.

## 6. Decision policy and state machine

**Automated policy (deterministic and testable):**

```
if technical_failure and result_not_safely_persisted:
    show "Processing interrupted" + retry instructions; don't claim a saved decision
elif any required check is FAILED / UNKNOWN / DUPLICATE_FLAG:
    current_status = PENDING
    output actionable reason(s)
else:
    current_status = APPROVED
    output "All prototype document-consistency checks passed"
```

Automated rejection is **not used for fixable data issues**. Rejection occurs when an admin explicitly rejects with a written reason (including confirmed duplicates). A review case can be manually approved only with an explicit rationale and an audit event. The state transitions are:

```
Internal: SUBMITTED → PROCESSING → [APPROVED | PENDING]
PENDING → vendor corrects/resubmits → PROCESSING → [APPROVED | PENDING]
PENDING → admin requests correction → PENDING (new action)
PENDING → admin approves with reason → APPROVED
PENDING → admin rejects with reason → REJECTED
APPROVED and REJECTED = terminal in this MVP (no reopening)
```

Outputs returned for every completed run: application ID, run ID, status (machine code and human-readable display), check results, plain-language reasons, recommended next step, trigger (submission/resubmission), stage log, elapsed automated processing time, timestamps and whether decision was manual.

## 7. Reason-copy catalogue: actionable and not AI-hallucinated

Each check has a code, severity, short label, vendor-facing message, admin-facing evidence and next action.

| Code / example | Vendor sees | Admin sees | CTA |
|---|---|---|---|
| `PAN_GSTIN_MISMATCH` | "Your PAN does not match the PAN in your GSTIN. Check both numbers." | Entered PAN and GSTIN-embedded PAN (masked where appropriate) | **Correct PAN/GSTIN** |
| `BANK_ACCOUNT_MISMATCH` | "Your bank account number differs from the uploaded bank document." | Typed and extracted account numbers (masked, with privileged reveal if needed) | **Update bank details/document** |
| `BANK_NAME_REVIEW` | "We need to confirm the bank account holder's name." | Exact claimed/documentary names; possible legal/trade-name distinction | **Request evidence / Review** |
| `DUPLICATE_GSTIN` | "This GSTIN may already be registered. Our team will review it." | Linked existing approved application ID, masked metadata | **Review duplicate** |
| `GST_DOC_UNREADABLE` | "We couldn't read your GST certificate. Upload a clearer PDF." | Parse error or null extraction; no invented fields | **Replace certificate** |
| `MISSING_BANK_PROOF` | "Upload a bank letter or cancelled cheque to continue." | Bank proof absent | **Upload document** |
| `MANUAL_REJECTION` | "Your application was rejected: [admin's specific reason]." | Admin identity/time/rationale | **See decision** |

**AI boundary:** Gemini performs field extraction from unstructured PDFs into JSON. Vendor/admin reasons are deterministic templates from known checks, not a second opaque AI-generated judgment. If later justified, AI may paraphrase a reason, but only using fixed rule codes and evidence, not inventing compliance conclusions. A separate AI-chat widget is explicitly out of MVP scope.

## 8. UX / UI specifications

### Design rules from public UX guidance
- **Reduce cognitive load**: group related fields, show only current section, label required inputs (Nielsen Norman Group).
- **Specific, repairable errors**: summary + inline field guidance; retain all input values (CMS Design System).
- **Visible progress, not fake percentages**: show actual stage transitions with short text and status glyphs; distinguish business review from technical failure (NN/g; Streamlit `st.status`).
- **One primary action per screen**: Submit, Correct & resubmit, or Review next case. No distracting secondary buttons (consistent with checkout-friction findings from Baymard).
- **Accessible feedback**: textual status alongside ✓, ⚠, ✕, with contrast; never colour/icons alone.

### Vendor UI — 3 steps plus result

```
VendorFlow AI                  [New application] [Track existing]

  ✓ 1. Business  →  ● 2. Banking  →  ○ 3. Documents & review

  PAGE: Banking information
  Account holder name  [_________________]
  Account number       [_________________]   (kept as text)
  IFSC                 [___________]         (example format hint)

  [Back]                                       [Continue →]
```

The **execution screen** is separate from the **form stepper**:

```
Checking application VF-XXXXX
  ✓ Application received
  ✓ GST & bank PDFs read
  ✓ Details extracted
  ⚠ PAN/GSTIN cross-check needs attention
  ✓ Decision saved

  ⚠ Pending Review
  Your PAN does not match the PAN in your GSTIN.
  Next step: [Correct PAN/GSTIN]
  [Show all checks]    [Save tracking details]
```

Tick ≠ official verification. "Details extracted" means information was read, not proven genuine. UI wording must uphold this distinction.

### Admin UI — exception-first operations console

```
VendorFlow AI / Admin Console          [Log out]
[ Total 18 ] [ Approved 10 ] [ Pending 6 ] [ Rejected 2 ]
[ Average automated check time: 19.4s (sample) ]  <-- illustrative only

Needs attention (6)         [Filter status] [Search ID / company]
ID         Vendor       Created        Primary reason            Action
VF-104     Example A    Nov 4 14:00    Bank account mismatch     [Review →]
VF-105     Example B    Nov 4 14:06    Possible duplicate        [Review →]

CASE: VF-104
Status: Pending Review
                  FORM CLAIM               EXTRACTED DOCUMENT
Legal name        Example A Pvt Ltd        Example A Pvt Ltd  ✓
GSTIN             ***                      ***                ✓
Bank account      ••••4821                ••••8401           ⚠

[Approve after review] [Request correction] [Reject]
       (Reason required for manual decisions)
[Workflow execution history ▼] [Full field checks ▼]
```

No claim of "19.4s" as a real metric until the code has logged executions. All times, stats and status changes must come from persisted run data; demo-ready seeded fixtures are labelled as test data.

### Streamlit feasibility and enhancement policy

**P0 / implement immediately:** `st.form`, `st.columns`/`st.tabs` (or page navigation), `st.session_state`, `st.file_uploader`, `st.status`, `st.success/warning/error`, `st.metric`, `st.dataframe`, `st.expander`, compact CSS for step arrows/status badges, real-time `.update()` on current execution.

**P1 / if core flow fully passes:** polish spacing, typography, lightweight icons, mobile layout.

**P2 / not before submission:** React rewrite, animated transitions, elaborate chatbot, external login providers. React is a future front-end option, **not** a reason to delay a reliable Streamlit MVP.

## 9. Data and security design

**Recommended minimal stack:** Streamlit UI + Python service functions + PyMuPDF (PDF text) + one Gemini structured extraction call + Python/Pydantic business checks + Supabase Postgres tables and **private** Supabase Storage bucket. Streamlit Community Cloud hosts UI; Supabase secrets and Gemini key stay in Streamlit deployment secrets. Use the server-only service key; never expose it in browser content or GitHub.

**Four minimum tables:**

1. `applications`: `id`, `payload_json` (latest vendor-entered fields), `tracking_token_hash`, `current_status`, `decision_source`, `latest_run_id`, `created_at`, `updated_at`.
2. `documents`: `id`, `application_id`, `doc_type`, `storage_path`, `file_sha256`, `version`, `uploaded_at`. Storage bucket is private; never provide public document URLs.
3. `runs`: `id`, `application_id`, `trigger`, `status`, `stages_json`, `extracted_json`, `checks_json`, `decision`, `reasons_json`, `started_at`, `finished_at`, `elapsed_ms`. Runs are immutable once complete.
4. `review_actions`: `id`, `application_id`, `action`, `reason`, `actor`, `created_at`.

**Security basics:** demo vendor gets randomly generated application ID and unpredictable tracking code; only hash of tracking secret is stored. Admin uses protected password in secrets, authenticated state held in session; separate admin queries from vendor queries. Use synthetic documents only. Don't log full bank account numbers; mask display by default. Protect against double-submit by disabling/bounding duplicate actions and recording unique run IDs. Storage failure is surfaced rather than pretending history was saved.

**Caveat:** demo authentication is not production RBAC. Production would need individual accounts, authorisation policies, encryption/governance, audit retention and official verification integrations.

## 10. Strong edge-case suite (4) plus routine guards

| Case | Fixture | Expected behaviour | Why meaningful |
|---|---|---|---|
| EC1 — Cross-field inconsistency | GST certificate GSTIN and entered GSTIN appear well formed, but submitted PAN differs from PAN embedded in GSTIN | PENDING; `PAN_GSTIN_MISMATCH`; tells vendor exactly which identifiers to correct | Catches non-obvious inconsistency across related fields |
| EC2 — Bank ownership ambiguity | GST legal name and bank letter account holder differ (company vs trade/individual name) | PENDING; no false rejection; admin reviews evidence | Demonstrates risk-sensitive judgment rather than blind string matching |
| EC3 — Possible duplicate / changed bank info | Second application uses GSTIN of an already approved vendor but different bank account | PENDING + duplicate flag and existing record reference; admin may reject with reason | Addresses duplicate vendor and payment-diversion risk |
| EC4 — Extraction uncertainty | Bank proof missing account holder OR uploaded document is unreadable | PENDING; `Not found` not guessed; request clearer proof or admin review | Demonstrates safe failure on messy documents |

**Routine safeguards:** required document missing, malformed identifier, unsupported PDF, AI timeout, data-store failure and user correction/resubmission are tested in addition to the four designed edge cases. **Happy-path fixture** uses a readable GST certificate and a readable bank letter where all fields are present and consistent.

**Run order:** 1 happy path → EC1 → EC2 → EC3 → EC4 → correction/resubmission → admin action → fresh-session history check. Build happy path first, then each edge case. No demo depends on live government verification or real business accounts.

## 11. KPI contracts and measurement plan

- **Primary:** `automated_evaluation_time_seconds`: mean `finished_at - started_at` for completed runs, report sample `n`, median and range as context. Engineering target ≤60s on known synthetic PDFs with working AI API (goal, not result).
- **Straight-through rate:** number of initial submissions auto-APPROVED / all initial submissions with completed automated evaluations (exclude manual approvals and reruns).
- **Pending rate:** initial submissions routed to PENDING / completed initial evaluations.
- **Review resolution time:** elapsed from initial submission to manual final decision or successful corrected rerun; only compute for resolved cases.
- **Workflow completion rate:** successfully persisted decision runs / attempts.
- **Manual effort:** optionally time the *same* synthetic cases by hand and by tool; report as a small illustrative comparison, never production ROI.

Never mix dashboard populated sample data with actual measured product impact. Each KPI is labelled "prototype test data" if applicable.

## 12. Phase 3 development handoff — deterministic build order

**B1 Happy-path processing engine**: load synthetic GST/bank text PDFs → Gemini structured extraction → Pydantic typed output → rules → APPROVED → save run + status. Execute via command line first; write assertion-based test.

**B2 Vendor UI**: 3 form sections, upload, actual st.status stage transitions, result, ID and tracking secret.

**B3 Exception suite**: add EC1→EC4 one by one, test expected reasons, check no false APPROVED.

**B4 Persistence and vendor correction**: Supabase schema/storage, signed tracking code access, save all runs/doc versions, resubmit fresh run.

**B5 Admin**: password, pending-first queue, detail comparisons, manual action + audit history, KPIs.

**B6 Release**: deploy Streamlit, configure secrets, fresh-browser run, run history after restart, 5-minute real-screen recording.

**If schedule slips:** protect *runnable happy path + two to four real edge cases + visible execution + history + video* first. Reduce dashboard polish, advanced correction convenience, or custom styling before sacrificing live functionality.

## 13. Acceptance gates for Phase 2 and Phase 3

**Phase 2 locked when:** statuses/decisions and edge cases are unambiguous; vendor/admin paths are complete; AI boundary, fields, system state, schema and UI are clear; no unplanned React/refactor; security limitations and honest prototype scope documented.

**Phase 3 cannot be called done until:** a real PDF-backed, end-to-end happy-path run returns a structured, reasoned, persisted status; every visible stage corresponds to actual operations; no fake approvals or fake progress.

## 14. References (Phase 2 external research)

- Zamp AI: `ASA Case Study — Candidate Guide.pdf`, pp. 2, 4, 6–7 (provided in project).
- Nielsen Norman Group, *Few Guesses, More Success: 4 Principles to Reduce Cognitive Load in Forms*: https://www.nngroup.com/articles/4-principles-reduce-cognitive-load/
- CMS Design System, *Error validation*: https://design.cms.gov/patterns/Forms/error-validation/
- Nielsen Norman Group, *Progress Indicators Make a Slow System Less Insufferable*: https://www.nngroup.com/articles/progress-indicators/
- Streamlit official, `st.status`: https://docs.streamlit.io/develop/api-reference/status/st.status
- RBI, IFSC FAQ: https://systemhealth.rbi.org.in/Scripts/FAQView.aspx_Id%3D60%281%29.html
- CBIC/GST Council, GSTIN format and registration rules: https://cbic-gst.gov.in/hindi/gst-registration-rules.html
- Supabase Python file upload: https://supabase.com/docs/reference/python/storage-from-upload
- Streamlit Community Cloud, secrets: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management

