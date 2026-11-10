# VendorFlow AI — Zamp AI / PS-2 Vendor Onboarding

**v1.1 development copy — Stage 6.3 UX changes prepared, not released.**

This checkout is intended for `stage6-v1.1-remediation` and the isolated
`vendorflow-v11-staging` Supabase project. The production MVP remains on GitHub
`main` until the separate Stage 6.5 release gate. Use **synthetic vendor documents only**.

## What the product does

An India-only, GST-registered vendor onboarding demo with:

- A three-step vendor application with GST and bank PDFs; recovery ID + private code issued before the first save.
- A document-consistency decision: **Approved, Pending Review or Rejected**, with plain-language reasons and tracked next actions.
- AI-assisted PDF extraction; deterministic PAN/GSTIN/IFSC, evidence-grounding, and approved-GSTIN duplicate rules.
- Staff exception queue, masked submitted-vs-PDF comparison, authenticated run-bound PDF downloads, revision-safe manual review, and an audit trail.
- Real persisted workflow stages and processing time. These metrics are **not** a measured reduction in vendor waiting time.

Approval reflects prototype document consistency, **not** government registration validation,
independent bank verification or legal KYC/KYB. Scanned/unreadable PDFs remain review-bound.

## Staging-only local setup (Ubuntu)

Create a separate local `.env` in this development checkout using `.env.example`, with
**staging** Supabase values only. Set `GEMINI_API_KEY`, `GEMINI_MODEL` and
`ADMIN_PASSWORD` locally. **Never share or commit `.env` or Streamlit secrets.**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
PYTHONPATH=. python -m pytest -q
streamlit run app.py
```

The Stage 6.3 offline suite is **99/99 passing**. The UI still requires a real
staging desktop/mobile browser acceptance pass before Stage 6.3 is declared done.
See [`STAGE6_3_HANDOFF.md`](STAGE6_3_HANDOFF.md) for the exact review checklist.

## Environment safeguards

- Do not run v1.1 locally with the **production Supabase secret or URL**.
- Database migrations for Stages 6.1 and 6.2 are already installed in isolated staging;
  **do not rerun those migrations or `schema.sql` there**.
- Keep the original working deployed MVP intact until the controlled Stage 6.5 release.
- The staff password and vendor ID+tracking-code model are demo access controls,
  not a production identity and authorization solution.

See [`PROGRESS.md`](PROGRESS.md) for stage status, and the Stage 6.1/6.2 handoffs for tested integrity and recovery guarantees.
