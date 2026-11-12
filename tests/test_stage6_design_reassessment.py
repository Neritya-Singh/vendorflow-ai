"""Reassessment of screenshots: readable styles, full-width staff review, vendor simplicity.

All checks are offline and use synthetic metadata only; no database/API calls.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from vendorflow.ux_support import admin_review_issue_groups

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
THEME = (ROOT / "vendorflow/theme.py").read_text(encoding="utf-8")
AST = ast.parse(THEME)
TOKENS = ast.literal_eval(next(n.value for n in AST.body if isinstance(n, ast.Assign)
                               and any(isinstance(t, ast.Name) and t.id == "TOKENS" for t in n.targets)))


def _luminance(value):
    channels = [int(value[i:i+2], 16) / 255 for i in (1, 3, 5)]
    transformed = [v / 12.92 if v <= .04045 else ((v + .055)/1.055)**2.4 for v in channels]
    return sum(a*b for a, b in zip(transformed, (.2126, .7152, .0722)))


def contrast(a, b):
    bright, dark = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (bright + .05) / (dark + .05)


@pytest.mark.parametrize('token', ['muted','subtle','ink-2'])
def test_helper_text_on_surface_is_legible(token):
    assert contrast(TOKENS[token], TOKENS['surface']) >= 4.5
    assert contrast(TOKENS[token], TOKENS['bg']) >= 4.5


def test_captions_not_rendered_too_small_or_low_contrast():
    assert '[data-testid="stCaptionContainer"] p{color:var(--vf-muted)!important;font-size:.875rem!important;' in THEME
    assert '.vf-admin-issue-note{font-size:.9375rem;' in THEME
    assert '.vf-admin-subtitle,.vf-admin-queue-note{font-size:.9375rem;' in THEME


def test_review_case_always_full_width_including_rejected_cases():
    review = APP[APP.index('    # The split panel compressed evidence'):APP.index('def _track_receipt(')]
    assert 'with evidence_col:' not in review
    assert 'with decision_col:' not in review
    assert 'evidence_col, decision_col = st.columns' not in review
    assert 'with st.container(border=True, key="vf-decision-panel"):\n        st.markdown(\'<h2 class="vf-admin-heading">Record a decision' in review
    assert 'admin_evidence_table(' in review
    assert review.index('if app.get("current_status") != "PENDING":') > review.index('admin_evidence_table(')
    assert 'if not runs:' in review


def test_row_selection_still_requires_case_confirmation_and_stale_revision_guard():
    review = APP[APP.index('def admin_console() -> None:'):APP.index('def _track_receipt(')]
    assert 'selected_id = selected_review_case(queue_rows, chosen)' in review
    for snippet in ['if not confirm_case:', 'if action == "APPROVE" and not reviewed_evidence:',
                    'expected_revision=int(app.get("revision", 0))',
                    'expected_latest_run_id=app.get("latest_run_id")',
                    'repo.admin_review(selected_id, action, reason,']:
        assert snippet in review


def test_failed_checks_precede_unknowns_and_none_are_discarded():
    checks = [{'rule_id': 'R05', 'state':'UNKNOWN', 'label':'PAN in GSTIN', 'vendor_message':'Need valid values'},
              {'rule_id':'R03', 'state':'FAIL', 'label':'PAN structure', 'vendor_message':'Invalid PAN'},
              {'rule_id':'R07', 'state':'PASS', 'label':'IFSC', 'vendor_message':'Valid'}]
    failed, unknown = admin_review_issue_groups(checks)
    assert [x['rule_id'] for x in failed] == ['R03']
    assert [x['rule_id'] for x in unknown] == ['R05']
    assert len(failed) + len(unknown) == 2


def test_staff_issue_copy_is_actionable_not_misleading():
    f, _ = admin_review_issue_groups([
        {'state':'FAIL','rule_id':'R01','label':'Required fields',
         'vendor_message':'Complete: PAN, GSTIN.'},
        {'state':'FAIL','rule_id':'R02','label':'Required PDFs',
         'vendor_message':'Upload: GST certificate.'},
    ])
    assert f[0]['label'] == 'Missing submission details'
    assert f[0]['note'] == 'Ask the vendor to provide: PAN, GSTIN.'
    assert f[1]['label'] == 'Document evidence needed'
    assert f[1]['note'] == 'Ask the vendor to upload: GST certificate.'


def test_admin_still_shows_identity_screening_staff_only():
    failed, unknown = admin_review_issue_groups([{
        'state': 'FAIL', 'rule_id': 'R12', 'label': 'Duplicate', 'admin_detail': 'Staff evidence only'
    }])
    assert failed[0]['label'] == 'Possible duplicate of an approved vendor'
    assert failed[0]['note'] == 'Staff evidence only'
    assert not unknown


def test_welcome_and_inner_pages_use_the_same_vendor_header():
    assert 'def render_vendor_header() -> None:' in APP
    assert 'Vendor onboarding made easy.' in APP
    assert 'render_vendor_header()' in APP
    assert 'if st.session_state["vendor_page"] == "Welcome":' in APP
    assert 'page = "Welcome"' in APP
    assert 'page = st.segmented_control("Vendor navigation"' in APP
    assert 'st.button("Start application",' in APP
    assert 'st.button("Track or correct",' in APP


def test_mobile_has_one_line_progress_rather_than_three_stacked_cards():
    assert '.vf-mobile-step{display:none;}' in THEME
    assert '  .vf-steps{display:none;}' in THEME
    assert '  .vf-mobile-step{display:block;' in THEME
    assert 'role="progressbar"' in APP
    assert 'aria-valuenow=' in APP


def test_backend_decisions_not_reimplemented():
    assert 'def checks_without_duplicate' not in APP
    assert 'def bank_account_grounded' not in APP
    assert not list((ROOT/'supabase/migrations').glob('*design*'))


def test_contact_inputs_are_grouped_and_state_is_separate():
    fields = APP[APP.index('def business_fields('):APP.index('def bank_fields(')]
    assert fields.index('contact_email = st.text_input(') < fields.index('contact_name = st.text_input(')
    assert fields.index('contact_name = st.text_input(') < fields.index('state = st.selectbox(')
    assert 'key=f"{prefix}_state"' in fields


def test_admin_workspace_uses_top_controls_not_sidebar():
    review = APP[APP.index('def admin_console() -> None:'):APP.index('def _track_receipt(')]
    bar = APP[APP.index('def render_top_bar('):APP.index('# Vendor-first navigation')]
    assert 'with st.sidebar' not in APP
    assert 'Admin Console' in review
    # Navigation lives once in the compact header row, not duplicated in the console.
    assert 'Vendor portal' in bar and 'Log out' in bar
    assert '"Log out"' not in review and '"Vendor portal"' not in review
    assert 'on_click=_return_to_vendor_portal' in bar
    assert 'view = st.segmented_control(' in review
