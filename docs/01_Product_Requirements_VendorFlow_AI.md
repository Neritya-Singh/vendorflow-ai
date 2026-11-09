# VendorFlow AI — Product Requirements Document (PRD)

**Version:** 1.0 — MVP scope proposed for lock-in  
**Assignment:** Zamp AI, PS-2 — Vendor Onboarding  
**Market:** India; GST-registered domestic businesses  
**Customer:** Indian private-company Procurement / Finance Operations team  
**Product goal:** Reduce average automated handling time and manual verification effort while ensuring explainable outcomes and clear exception routing.  
**Build constraint:** One-day, publicly deployed, interview-demonstrable MVP.

## 1. Problem and opportunity

Today, an operations analyst manually collects vendor information, opens registration and bank documents, retypes key fields, checks for inconsistencies, and follows up when information is missing. The vendor may not know why onboarding is delayed. The product should automate document reading, basic consistency checks, clear-case decisions, and the routing of exceptions for human action.

**Core principle:** Automate straightforward checks; escalate uncertainty. Do not equate document consistency with official legal, tax, or bank-account verification.

## 2. Research and assumptions

Desk research reviewed Indian vendor onboarding forms (e.g. Axis Bank), SAP Ariba supplier-management guidance, government GST taxpayer-search guidance, and RBI IFSC format information. Such flows typically collect tax information and bank proof; missing data, duplication and manual handoffs are common design challenges. These are **desk-research-derived assumptions**, not validated interview findings.

**MVP boundary:** Only India-based, GST-registered business vendors. Other legitimate categories (unregistered suppliers, foreign vendors, individuals, multi-entity businesses) are out of scope. This restriction is a fictional customer's onboarding policy, not a statement that all Indian vendors require GST registration.

## 3. Personas and jobs-to-be-done

**Vendor applicant:** “I need to submit correct information once, track the outcome, and immediately see what to fix.” Pain points: repeated requests, opaque status, confusing forms.

**Procurement/Finance reviewer:** “I need to see only the exceptions that require my judgment, with evidence and quick approve/reject/request-correction actions.” Pain points: repetitive checking, duplicate entries, slow follow-up, inadequate audit trail.

## 4. End-to-end experience

**Vendor:** Open Vendor Portal → enter details → upload two documents → preview submission → run validation → see Accepted / Under Review / Rejected with plain-language reasons → save application ID + secret tracking code → return to track and, if Under Review, correct fields / replace documents → resubmit for an automatic rerun.

**Administrator:** Open secured Demo Admin Portal → view queue and summary KPIs → filter Under Review → open one application → inspect fields, extracted document evidence, each check and reason → Accept, Reject, or Request Correction with a reason → updated vendor-facing status and recorded audit event.

**Workflow stages:** Intake → document reading → AI structured extraction → field normalization → rule checks → duplicate lookup → decision routing → user-facing explanation → history persistence. Each stage must show actual completion/error states rather than fabricated animation.

## 5. Input data and documentation

**Required typed fields:** legal business name; contact person; contact email; GSTIN; PAN; bank account holder name; bank account number; IFSC; business state.

**Required PDF uploads:** (1) GST Registration Certificate; (2) cancelled cheque **or** bank confirmation letter. Use synthetic/sample documents only. A PAN-card upload is unnecessary for the MVP because the vendor enters PAN and the GSTIN encodes PAN; the system cross-checks them. Real PAN database verification is not performed.

**AI-extracted fields (when present):** from GST certificate — legal name, GSTIN, business state/address; from bank proof — holder name, account number, IFSC. Each extracted value is displayed alongside the claimed value, with `Not found` as an explicit possible result. AI never independently decides final eligibility.

## 6. Validation and decision policy

**Deterministic checks:** Required fields and documents; file type; GSTIN structure; PAN structure; GSTIN-embedded PAN versus submitted PAN; IFSC structure; claim-versus-document GSTIN, legal name, bank account, IFSC and account-holder consistency; duplicate detection using GSTIN against previous accepted vendors; extraction failure/absence. Case-insensitive spacing normalisation is permitted, but uncertain business-name differences go to review; never assume a trade name equals a legal name.

**Accepted:** Required documents parse successfully; required IDs are structurally valid; mandatory data agree across form and documents; no duplicate accepted GSTIN. “Accepted” means passed **prototype/document-consistency policy only**, not externally verified with government or banking databases.

**Under Review:** Missing or unreadable document; failed extraction; invalid format; document/form discrepancy; ambiguous name match; uncertain bank-holder ownership; duplicate requiring investigation; any AI/network failure. Show the exact failed checks and suggested correction.

**Rejected:** Explicit administrator rejection with a recorded reason; optionally a confirmed duplicate of an already accepted GSTIN. Fixable issues must not be automatically rejected. Administrators can accept a reviewed case only with a recorded rationale; audit both automated and manual decisions.

**Security boundary:** A demo vendor accesses only their application using ID + randomly generated tracking secret. Admin access uses a separate password in deployment secrets. Both roles use synthetic data; no real identity, tax or banking records. This is demo authentication, not a production security design.

## 7. Functional requirements (priority)

| ID | Requirement | Priority | Acceptance evidence |
|---|---|---|---|
| FR01 | Simple vendor submission and PDFs | P0 | Form submits a synthetic clean application |
| FR02 | Genuine document extraction via AI | P0 | Extracted fields shown from uploaded PDFs |
| FR03 | Reproducible rule-based validation | P0 | Input/doc mismatch consistently flagged |
| FR04 | Three explained outcomes | P0 | All statuses visible with reasons and next steps |
| FR05 | Vendor tracking + correction/resubmit | P0 | Under Review application corrected and rerun |
| FR06 | Admin exception queue + decision actions | P0 | Reviewer acts on flagged case with rationale |
| FR07 | Persisted execution and stage log | P0 | Previous runs visible after page refresh/restart |
| FR08 | Publicly accessible live app | P0 | Fresh-browser end-to-end test passes |
| FR09 | Demo video ≤5 minutes, narrated by candidate | P0 | Video shows success, edge case, queue/history |
| FR10 | Admin metrics and filtering | P1 | Counts, review rate, measured processing time |

## 8. User-interface requirements

Use **two clearly labelled workspaces**: `Vendor Portal` and `Admin Console`. Avoid confusing nested menus. Vendor receives inline help, upload checklist, one obvious primary button, clear application status, plain-language failure messages and correction fields. Admin sees summary cards, a sortable exception-first table, case-detail evidence and exactly three context-appropriate actions. Display technical extraction/rule evidence in expandable sections, not on the vendor's main screen. Status colours must have textual labels.

## 9. Metrics and evidence

**Primary test metric:** average elapsed *automated evaluation time* (submission → status), logged per execution. Design target: ≤60 seconds on prepared synthetic PDFs with a functioning AI API (target, not achieved result). Report the actual measured average and range from the test run.

**Operations metrics:** percentage accepted without human intervention; share Under Review; count of duplicate/format/mismatch exceptions; mean time to final resolution (track once cases are resolved); workflow success rate. Keep machine handling time and total vendor waiting time distinct.

**Impact comparison:** If claiming time saved, manually time a small, clearly labelled sample of the same synthetic applications and compare it with automation; do not present this as production ROI or a statistically validated study.

## 10. Test cases and acceptance gates

1. Complete consistent documents and details → Accepted.
2. Missing GST certificate → Under Review with specific upload request.
3. Submitted GSTIN / PAN inconsistent → Under Review with mismatch explanation.
4. Bank account or IFSC differs from uploaded bank proof → Under Review, never auto-accept.
5. Duplicate already-accepted GSTIN → Reject as duplicate **only if confirmed by policy**, otherwise review.
6. Unsupported/unreadable PDF or unavailable AI API → controlled Under Review/error state, no false approval.
7. Vendor replaces an incorrect document and resubmits → new execution logged, status recalculated.
8. Admin rejects an unresolved case with a reason → vendor sees Rejected and reason; audit log includes action.

**Release gate:** One clean case and at least three meaningful edge cases work on the deployed app; corrections and admin actions persist; every decision has reasons; no known test results in false acceptance; history survives app restart; video and submission links work.

## 11. Non-goals and constraints

Not building: foreign vendor support; non-GST supplier eligibility rules; production-grade KYC/KYB; government GST/PAN verification APIs; bank ownership confirmation; payments; ERP integration; mass email notifications; complex company types; multi-admin permissions; agent frameworks, RAG, vector database, React frontend. Any valid demo remains **document-level validation**, not official verification.

## 12. Proposed implementation

Streamlit UI + Python/Pydantic rules + Gemini structured document extraction + hosted persistent datastore (e.g. Supabase Postgres) + secure deployment secrets. Streamlit Community Cloud is the default host. If cloud storage connectivity is difficult, prioritize a simple persistent cloud DB over local SQLite that may be lost during redeployment. The application must not log secrets or expose uploaded bank documents across vendor sessions.

## 13. Product lock and next steps

**Scope status:** Proposed v1 for product-owner sign-off. Lock after acceptance.  
**Next phase:** Finalise exact per-field rules, state diagram, audit schema, screen wireframes, sample PDFs and implementation task list.  
**Critical assumption:** The brief's previously summarized PS-2 description is the working source; the original PDF could not be fetched in the current research pass, so exact wording must be rechecked before making any claim of full verbatim compliance.

### References used for discovery
- GST taxpayer search: https://tutorial.gst.gov.in/downloads/news/welcome_kit_for_new_taxpyers.pdf
- Income Tax PAN verification access: https://www.incometax.gov.in/iec/foportal/help/how-to-verify-pan
- RBI IFSC format: https://systemhealth.rbi.org.in/Scripts/PublicationsView.aspx_id%3D20315%281%29.html
- Indian vendor registration example: https://application.axis.bank.in/webforms/cptlead/onboarding.aspx
- SAP supplier duplicate checks: https://learning.sap.com/courses/sap-ariba-supplier-management-supplier-lifecycle-management/explaining-internal-supplier-request-process
