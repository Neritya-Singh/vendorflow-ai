# VendorFlow AI — Stage 3.4 Streamlit Frontend

**Status:** implementation prepared; 36 local backend + helper unit tests passed; real Streamlit browser acceptance tests and cloud deployment not yet performed.

## What the patch adds

- `app.py`: a real Streamlit Vendor Portal and password-protected Admin Console.
- `vendorflow/ui_support.py`: display-only helpers; never substitutes for deterministic decisions.
- `tests/test_ui_support.py`: six offline presentation tests.
- `requirements.txt`: the prior dependencies plus Streamlit.

No `.env`, `.venv`, database schema, existing backend, or deployed account is included in this patch.

## Installation on Ubuntu (from the existing VendorFlow_AI root)

First, download `VendorFlow_AI_Stage_3_4_Frontend_Addon.zip` into `~/Downloads`.

```bash
# The current working directory must be your existing VendorFlow_AI folder.
# First validate the download, then extract into a temporary folder.
unzip -l "$HOME/Downloads/VendorFlow_AI_Stage_3_4_Frontend_Addon.zip"
mkdir -p "$HOME/Downloads/vendorflow_stage34_extracted"
unzip -o "$HOME/Downloads/VendorFlow_AI_Stage_3_4_Frontend_Addon.zip" -d "$HOME/Downloads/vendorflow_stage34_extracted"

# Only patch files will be copied (your existing .env/.venv remain intact).
cp -a "$HOME/Downloads/vendorflow_stage34_extracted/VendorFlow_AI/." .
python -m pip install -r requirements.txt
python -m pytest -q
```

Expected: `36 passed`. No cloud integrations are exercised by those tests.

## Before launching the admin UI (next manual checkpoint)

Add a **strong, unique** `ADMIN_PASSWORD` to your local `.env` (do not share or commit it). Streamlit Community Cloud will use this value from app secrets. No extra admin account needs to be created in Supabase. Never upload real tax, bank or personal records.

```bash
streamlit run app.py
```

Open the URL printed in the terminal (normally `http://localhost:8501`). Validate **one** synthetic end-to-end new application and tracking; then pending correction/resubmission; then Admin Console queue, audit actions, visible run stages and history. Each successful submission writes real records to your Supabase project. Do not repeatedly submit on errors without checking for partial records.

## Functional details and caveats

- New applications are grouped into Business → Banking → Documents/Review, with an actual execution log.
- Tracked applications require both application ID and unpredictable private tracking code. The admin console uses a separate server-side password. Both are **demo access controls, not production IAM/RBAC**.
- New application results show the tracking code to the current vendor session; it is not stored in plaintext in Supabase.
- The admin queue shows persisted values and masks bank account/identifier displays; no publicly accessible PDF URL is generated.
- The average processing-time card uses saved run measurements only. It does not measure true vendor wait time or production ROI. Supabase's default API page size may truncate counts beyond 1,000 rows; this is acceptable for the agreed small synthetic demo, not for a production dashboard.
- PDF parsing currently uses text extraction; unreadable/scanned PDFs are flagged for review per the locked MVP scope.
- The Streamlit UI is not live-verified until you complete the local browser checkpoint; Stage 3.4 must remain In Progress until then.
