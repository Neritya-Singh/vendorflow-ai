# VendorFlow — UI status/navigation microfix

**Target:** Local `stage6-v1.1-design` checkout after the previously delivered sidebarless UX refinement. Do not apply directly to `main` or `stage6-v1.1-remediation`.

## Fixed

1. **Pending status icon overlap:** all decision banners now use an explicit 36 × 36 px status-icon tile, with a 14 px gap to the label and individual Approved/Pending/Rejected colours. This is not just a spacing adjustment; it creates a visibly separate element.
2. **Dropdown chevron:** the selectbox SVG is shifted left 6 px, scoped only to Streamlit selectboxes to avoid modifying icons elsewhere.
3. **Admin logout navigation:** clicking Log out clears admin authorization and saved review selection, returns to `?portal=vendor`, and opens the Welcome view. The admin header also displays a permanent `← Vendor portal` button, including before admin authentication.

## Files
- `app.py`
- `vendorflow/theme.py`
- `tests/test_stage6_design_reassessment.py`
- `tests/test_stage6_design_microfix.py`

## Offline verification

```bash
PYTHONPATH=. python -m pytest -q
```

**Expected:** `166 passed` (based on the previous 161-test design baseline).

## Browser acceptance

- Check an actual Pending Review case: icon in a separate tinted box with clear space before the words.
- Open an India state / admin status dropdown and check its arrow is inside the border without overlapping the right side.
- Open `?portal=admin` signed out: header button returns to vendor Welcome.
- Sign into admin, then click Log out: page automatically returns to vendor Welcome; staff authorization must be cleared.
- Return to Admin Console: password must be required again.

This change is UI-only: no Supabase migrations, Gemini changes, persistence changes or production deployments.
