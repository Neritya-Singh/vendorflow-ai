# VendorFlow AI — Zamp AI / PS-2 Vendor Onboarding

**Build state:** Backend and five live synthetic Gemini workflows verified by user.
Stage 3.3 Supabase integration code written, **not yet connected or live tested**.
Not deployed; frontend is not built.

## Architecture

India-only GST-registered **synthetic demo**. PDF documents are read using
PyMuPDF. Google Gemini extracts structured fields (`gemini-3.5-flash-lite` has been
verified live by user). Deterministic Python policy validates PAN/GSTIN/IFSC,
document consistency, duplicate evidence and extraction completeness.
Only ALL-PASS auto-approves. Fixable issues remain PENDING; rejection requires
an explicit admin reason. Approval **is not official government/bank verification**.

## Local Python setup (Ubuntu)

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
```

Use a private `.env` copied from `.env.example`; never commit or share it.
Existing keys in your local `.env` are retained when you extract an updated ZIP.

## Live Gemini local test (NO DB persistence)

```bash
python run_backend.py --scenario happy --demo-empty-registry
```

## Supabase integration

See `supabase/SETUP.md`. **Wait for step-by-step manual confirmation.**
1. Create project, 2. SQL Editor run `supabase/schema.sql`, 3. local server
   secret configuration, 4. `python run_persisted.py --scenario happy`.

Supabase code provides a private `vendor-documents` bucket, versioned PDFs,
application tracking via secret token (only SHA-256 digest stored), immutable
executions, safe duplicate lookup, admin review actions and corrections.
The SQL trigger commits each run and latest application status together.

Only synthetic documents. Do not include bank accounts or PANs belonging to real people.

## Current progress

See `PROGRESS.md` for verified results and remaining stages.
