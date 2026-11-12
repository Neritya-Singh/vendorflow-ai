# VendorFlow AI

**AI-assisted vendor onboarding for Indian businesses**  
**Zamp AI — Solutions Analyst case study | v1.1 submission build**

**[Launch the live application](https://vendorflow-ai-zamp-submission.streamlit.app/)**

VendorFlow AI is a working Streamlit prototype for an India-only vendor-onboarding process. A vendor enters business and bank details, uploads a GST certificate and bank proof, and receives an understandable decision. Finance/procurement reviewers handle exceptions in a protected admin console, with document evidence and a saved audit trail.

> **Scope:** Educational case-study demo using synthetic business and bank documents. A decision indicates consistency of submitted information with extracted PDF evidence; it does **not** verify a company against government databases, confirm bank ownership with a bank, or constitute regulatory KYC/KYB.

## What the product solves

Manual vendor onboarding requires comparing repeated information across forms, tax documents and bank letters. Exceptions can create slow back-and-forth communication. VendorFlow targets the document-comparison and exception-handling steps while keeping a person responsible for uncertain decisions.

| Vendor experience | Reviewer experience |
| --- | --- |
| Three-step application, with GST and bank PDF uploads | A queue of applications needing human review |
| **Approved / Pending Review / Rejected** with plain-English reasons | Submitted information compared with extracted PDF evidence |
| Private application ID + tracking code for status lookup | Download the PDF versions associated with a specific evaluation |
| Correct a pending application without starting over | Approve, reject or request correction with an audit trail |

## How it works

~~~mermaid
flowchart LR
    A[Vendor form + two PDFs] --> B[PDF text and Gemini-assisted extraction]
    B --> C[Deterministic business and evidence checks]
    C --> D{Decision}
    D -->|Checks pass| E[Approved]
    D -->|Insufficient or conflicting evidence| F[Pending Review]
    F --> G[Staff review or vendor correction]
    G --> H[Audited decision or new evaluation]
    D -->|Applicable terminal decision| I[Rejected]
~~~

**Key design choice:** AI extracts candidate document fields; deterministic rules make the decision. The model alone cannot approve a vendor. Scanned, unreadable, reversed or unsupported PDFs are routed to review rather than silently accepted.

## Product highlights

- **India-only checks:** PAN/GSTIN patterns, GST state and PAN relationships, IFSC pattern, legal-name and bank-details agreement, and document evidence grounding.
- **Reliable exception handling:** Unreadable or swapped documents generate actionable instructions; missing or inconsistent evidence does not produce automatic approval.
- **Controlled review:** Staff decisions are recorded as manual actions, distinct from automated evaluations.
- **Traceable history:** Applications retain evaluations, immutable document versions, processing-stage evidence and reviewer actions.
- **Revision protection:** Stale reviewer decisions and concurrent changes are guarded by database revision checks.
- **Private credentials:** Vendor tracking requires an application ID and secret code; the stored tracking verifier is hashed. Server-side credentials never belong in frontend code.

## Technical architecture

| Layer | Implementation |
| --- | --- |
| User interfaces | Streamlit, with vendor and password-protected admin views |
| Document processing | PyMuPDF for PDF text; Gemini (`gemini-3.5-flash-lite`) for structured extraction |
| Decision logic | Python rule engine, evidence checks and document-role safeguards |
| Persistence | Supabase PostgreSQL, with protected tables, run history and revision controls |
| Documents | Private Supabase Storage, versioned PDF records tied to evaluated runs |
| Reliability | Bounded AI retries, server-only credentials and regression tests |

**Meaning of timings:** The app records evaluation durations and workflow events; it does not claim to have measured a real-world reduction in vendor approval waiting time.

## Try the live demo

1. Open the **[VendorFlow AI application](https://vendorflow-ai-zamp-submission.streamlit.app/)**.
2. Select **Start a new application**, use *synthetic* details and PDFs, and save the displayed application ID and private tracking code.
3. Submit to see the decision, reasons and receipt. The **Track / correct application** view lets a pending vendor view reviewer notes and replace incorrect details or PDFs.
4. The **Admin Console** is available at the app URL with `?portal=admin`; access is deliberately password-protected and is demonstrated in the submission video.

**Demo safety:** Use fictional details only. The PDF fixtures in `fixtures/` are generated synthetic test evidence, not genuine identity or bank documents. Some identifiers may already appear in saved demo cases; approved GSTINs are protected against reuse.

## Run locally

**Requirements:** Python 3.12, a Gemini API key, and a private Supabase project configured with the repository schema and required migrations.

~~~bash
git clone https://github.com/Neritya-Singh/vendorflow-ai.git
cd vendorflow-ai
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
~~~

Add **your own secret values locally** to `.env` or to Streamlit's server-side Secrets settings. Required variable names (never their values):

~~~text
GEMINI_API_KEY
GEMINI_MODEL
SUPABASE_URL
SUPABASE_SECRET_KEY
ADMIN_PASSWORD
~~~

Then run:

~~~bash
python -m pytest -q
streamlit run app.py
~~~

**Never commit `.env`, Streamlit `secrets.toml`, private tracking codes, API tokens or database service keys.** This repository intentionally includes placeholder configuration only. For database installation, read `supabase/SETUP.md` and the migration SQL first; existing databases may require a controlled migration rather than reapplying an empty-database bootstrap.

## Verification and limitations

- **195 offline automated tests passed** on the frozen v1.1 build.
- Live synthetic staging tests covered approved applications, pending corrections, rejected decisions, reviewer actions, immutable document revisions, swapped/unreadable PDFs and Gemini extraction.
- Evaluator-facing copy was verified in both first-submission results and application tracking.
- Admin access is a shared demo password, **not** a production-grade identity provider; vendor recovery is based on possession of a private tracking code.
- Document consistency is not independent fraud detection, a government GST lookup, legal compliance certification or actual bank-account verification.
- Shared public-demo hosting can sleep when idle; the recorded walkthrough provides a deterministic demonstration.

## Source and release

The default **`main`** branch contains the reviewer-ready v1.1 source. The immutable tested implementation is retained in [`release-v1.1-frozen-2026-11-12`](https://github.com/Neritya-Singh/vendorflow-ai/tree/release-v1.1-frozen-2026-11-12).

Built as a **Solutions Analyst case-study MVP**. The design emphasizes clear vendor next steps, cautious automation, reviewer accountability and reproducible workflow history.
