# VendorFlow Status Tone and Layout Hotfix

## Purpose
This hotfix softens the status banners, refines admin header button placement, and improves the recovery-code card styling.

## Changes included
- Removed status SVG icons from the result banners.
- Kept colour-coded status headings with simpler visual weight.
- Repositioned admin header buttons to feel smaller and more balanced.
- Kept direct return to the Vendor Portal after admin logout.
- Styled the recovery code field using a tinted inner box inside the white recovery card.
- Shifted the select-box chevron slightly further left for cleaner alignment.

## Files changed
- `app.py`
- `vendorflow/theme.py`
- `tests/test_stage6_design_microfix.py`
- `tests/test_stage6_design_reassessment.py`

## Verification
Run:

```bash
source .venv/bin/activate
PYTHONPATH=. python -m pytest -q
```

Expected:
- **167 passed**

## Scope
- No business-rule changes.
- No database changes.
- No Gemini changes.
- No production deployment.
