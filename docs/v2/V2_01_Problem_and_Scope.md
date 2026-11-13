# VendorFlow AI v2 — Stage 1: Problem and Scope (Approved)

**Status:** Approved by product owner, 13 Nov 2026
**Primary reference:** Zamp *ASA Case Study — Candidate Guide* (PS-2: Vendor onboarding)
**Supersedes:** v1.1 PRD (`01_Product_Requirements_VendorFlow_AI.md`), v1.1 workflow design (`02_Workflow_System_Design_VendorFlow_AI.md`) and `PRODUCT_AUDIT_v1.md`. Anything those documents contain that is still valid has been carried into this one.

---

## 1. Working stages

| Stage | Goal | Status |
|---|---|---|
| 1 | Problem, pain points, what to build | ✅ This document |
| 2 | Product thinking: vendor and admin psychology, priorities, screen workflow | Next |
| 3 | UI/UX direction | Pending |
| 4 | Change requests to Claude Code (coding is frozen until then) | Pending |
| 5 | Testing, including the live Gemini and Supabase test on a separate staging project | Pending |
| 6 | Submission and deployment | Pending |

---

## 2. What PS-2 requires

| # | Requirement | v2 response |
|---|---|---|
| R1 | Collect company, bank, tax and compliance information | GST certificate, bank proof, optional Udyam (MSME) certificate, contact details |
| R2 | Check the submission is complete, consistent and credible | Completeness, consistency between documents, duplicate and bank-reuse checks |
| R3 | Handle incomplete forms, wrong documents, name ≠ bank-account name, wrong tax-ID format and subtle cross-field inconsistencies | Explicit checks for each (§6) |
| R4 | Return Approved / Pending / Rejected with the reasoning visible | Three statuses plus a "waiting on" owner (§7) |
| R5 | For anything not approved, tell the vendor what is needed | A vendor message for every non-approved outcome (§8) |
| R6 | Replace manual follow-up and the inbox-only audit trail | Message log and immutable run and action history |
| R7 | UI: live run view plus a dashboard of history, status and outputs | Kept from the current v2 build |
| R8 | 2–4 non-trivial edge cases, run live in a ≤5-minute demo | §10 |

---

## 3. Pain points (India)

**Buyer company (finance and procurement)**
- Payment fraud through wrong or changed bank details.
- Lost input tax credit (ITC) when a supplier's GSTIN is cancelled or suspended.
- MSME 45-day payment obligation (Income Tax Act s.43B(h)): Udyam status must be known at onboarding.
- People still type details from PDFs by hand.
- Chasing vendors for missing items; the audit trail lives in someone's inbox.

**Vendor (often a small business, frequently on a phone)**
- Retyping numbers already printed on their documents.
- Not knowing the status; vague or wrong reasons when something fails.
- Being asked to "fix" things they cannot fix, such as a duplicate check or a review in progress.
- Failing on trivial name variants ("Pvt Ltd" vs "Private Limited").
- Bank proof is usually a scan or photo, not a clean text PDF.

---

## 4. Principles kept from v1.1

1. AI only extracts. Deterministic rules decide. AI never approves.
2. Fail closed: any extraction, API or storage failure leads to Pending, never Approved.
3. Fixable issues are never auto-rejected.
4. Scope: Indian, GST-registered business vendors only.
5. Runs are immutable; every automated and manual decision is audited.
6. "Approved" means the documents are consistent under our policy. It is **not** government, KYC or bank verification, and the UI must never imply that it is.

---

## 5. Intake model: upload first, then confirm

The vendor uploads documents. The system reads them and pre-fills the form. The vendor reviews and confirms.

| Field | Source |
|---|---|
| Legal name, trade name, GSTIN, state, address | Extracted from the GST registration certificate |
| PAN | Derived from GSTIN characters 3–12 (not typed) |
| Account holder, account number, IFSC, bank | Extracted from the cancelled cheque or bank letter (PDF, JPG or PNG; scans and photos allowed) |
| Contact name, email, phone | Typed (no document contains them) |
| MSME status | Yes/No; if Yes, a Udyam certificate upload (§9) |

**Edited fields:** if the vendor changes an extracted value, the change is kept, flagged, and shown to the reviewer next to the original document value.

---

## 6. Checks

Because values now come from documents, the core checks are **document vs document**, **vendor edit vs document**, and **document vs our own records**.

| Check | Type | Failure goes to |
|---|---|---|
| Required documents and fields present | Completeness | Waiting on vendor |
| Document type matches its slot; swapped files detected | Wrong document | Waiting on vendor ("The files look swapped") |
| Document readable and fields extracted | Extraction | Waiting on vendor (clearer copy) or reviewer (outage) |
| GSTIN, IFSC and Udyam number formats; GSTIN state code vs state | Format | Waiting on vendor |
| GST legal name vs bank account holder name (with "Pvt Ltd" = "Private Limited" style normalisation) | Document vs document | Waiting on reviewer |
| Udyam enterprise name vs GST legal name; Udyam state vs GST state | Document vs document | Waiting on vendor |
| Vendor edited an extracted value | Edit vs document | Waiting on reviewer |
| GSTIN already on an approved, pending or rejected application | Duplicate / reapplication | Waiting on reviewer |
| Same bank account (number + IFSC) under a different GSTIN | Bank reuse (fraud signal) | Waiting on reviewer |

**Vendor-facing rule:** never reveal duplicate or fraud hits to the vendor. Show "Our team is completing an additional check."

---

## 7. Status model

External statuses remain exactly as PS-2 asks: **Approved, Pending, Rejected.**

Pending always shows who acts next:
- **Waiting on you:** the vendor must fix or upload something. The message names exactly what.
- **With our team:** a reviewer must decide. No action is needed from the vendor, and no edit form is shown.

Rejected is set by a reviewer with a written reason. Approval after review also needs a written reason. Unresolved duplicate or bank-reuse cases cannot be approved without a structured confirmation.

---

## 8. Communication

- Every non-approved outcome produces one vendor message: status, who acts next, the exact items needed, and a link.
- Every admin "request correction" produces a vendor message.
- Because all vendor emails are synthetic, messages appear in an in-app **message log** visible to vendor and admin. Optionally, real email is sent only to the owner's own address for the demo.

**Access:** an admin creates an invite, and the vendor opens a unique link (Should-have; replaces the 32-character tracking code if time allows).

---

## 9. MSME (Udyam) design

**Facts:** the Udyam number format is `UDYAM-XX-00-0000000`, where XX is the state code. The certificate shows the enterprise name, type (Micro / Small / Medium) and major activity (Manufacturing / Services). The 45-day rule applies to registered **Micro and Small** enterprises.

**Flow**
1. The vendor answers: "Is your business registered under Udyam (MSME)?" Yes / No.
2. If Yes: upload the Udyam certificate. The system extracts the number, enterprise name, type and activity.
3. Checks: number format; enterprise name matches the GST legal name; Udyam state code matches the GST state.
4. Result tag on the vendor record:
   - Micro or Small → **"MSME — pay within 45 days"**
   - Medium → "MSME (Medium) — 45-day rule not applicable"
   - No → no tag

**Effect on the decision:** MSME data never blocks approval on its own. "Yes" with a missing, unreadable or mismatching certificate leads to Pending (waiting on vendor).

**Honesty label:** "Certificate checked for consistency. Not verified with the Udyam portal."

---

## 10. Synthetic test data policy

- All companies, GSTINs, PANs, bank accounts, Udyam numbers and emails are synthetic but **correctly formatted** (including a valid GSTIN check digit if the engine validates it). No real company names.
- Every fixture document is marked **SAMPLE**.
- Fixture set to generate:
  - GST certificate
  - Bank letter
  - Cancelled cheque as an image (photo/scan look)
  - Udyam certificate (Micro / Services)
  - Variants for each edge case
- External verifications (GST portal status, penny drop, Udyam portal) are **not** simulated in the run. They are named only as "what production would add."

**Candidate edge cases (to finalise in Stage 2):**
1. GST legal name ≠ bank account holder (ownership review)
2. Same GSTIN as an approved vendor with a different bank account (payment diversion)
3. Swapped or wrong document
4. Scanned cheque photo that reads correctly → straight-through approval
5. MSME declared, but the Udyam name or state doesn't match

---

## 11. Scope

**Must have**
1. Upload-first intake with auto-fill and confirmation; edits flagged
2. Scans and photos accepted (PDF, JPG, PNG)
3. Wrong or swapped document detection
4. Pending split: "waiting on you" / "with our team"
5. Vendor message for every non-approved outcome, plus a message log
6. Reviewer evidence: document viewer, matched duplicate record, values side by side
7. Duplicate check across approved, pending and rejected; bank reuse across GSTINs
8. MSME capture (§9)

**Should have**
- Admin invite link instead of the tracking code
- Legal-suffix name normalisation

**Not building**
- Real GST, penny-drop or Udyam API calls
- ERP integration
- Multi-admin roles
- Chatbot
- Decorative animation

---

## 12. Current v2 build status (as of 13 Nov 2026)

- **Built:** React + TypeScript frontend; FastAPI backend reusing v1.1 services unchanged. Committed locally to `v2-react-saas`. Nothing pushed or deployed.
- **Tests (offline, in-memory stand-ins):**
  - 195 v1.1 tests passed
  - 18 API tests passed
  - Frontend: lint and typecheck clean, 8 unit tests passed
  - 37 browser tests passed
- **Not yet done:** any run against real Gemini or Supabase.
- **Blocker:** the Supabase project in `.env` (`hkxalnpnchzheorrogci`) is the **live v1.1 database**. Create a separate staging project before any live test.
- **Not verified:** Docker image build.
- Which items in §11 already exist in the build will be checked at Stage 4.
