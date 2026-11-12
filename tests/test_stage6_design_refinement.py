"""Independent design review: plain language, accessibility, safe selection and decision guards.

These tests do not connect to Gemini, Storage, production or staging.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from vendorflow.ui_support import display_status, vendor_visible_checks
from vendorflow.ux_support import selected_review_case, vendor_owner_label

ROOT = Path(__file__).resolve().parents[1]
_THEME_AST = ast.parse((ROOT / "vendorflow/theme.py").read_text())
TOKENS = ast.literal_eval(next(n.value for n in _THEME_AST.body if isinstance(n, ast.Assign)
                               and any(isinstance(t, ast.Name) and t.id == "TOKENS" for t in n.targets)))
APP = (ROOT / "app.py").read_text(encoding="utf-8")
CONFIG = (ROOT / ".streamlit/config.toml").read_text(encoding="utf-8")


def _luminance(color):
    rgb = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    normalized = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    return sum(a * b for a, b in zip(normalized, (0.2126, 0.7152, 0.0722)))


def _contrast(a, b):
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_navy_primary_white_text_is_aa():
    assert _contrast(TOKENS["primary"], "#FFFFFF") >= 4.5


def test_input_border_is_at_least_3_to_1_against_surface():
    assert _contrast(TOKENS["border-input"], TOKENS["surface"]) >= 3


def test_keyboard_focus_distinguishable_against_background():
    assert _contrast(TOKENS["focus"], TOKENS["bg"]) >= 3


@pytest.mark.parametrize("status, expected", [("APPROVED", "Approved"), ("PENDING", "Pending Review"), ("REJECTED", "Rejected")])
def test_status_labels_not_emoji_dependent(status, expected):
    assert display_status(status) == expected


def test_staff_only_identity_screening_still_not_visible_to_vendor():
    checks = [{"rule_id": "R12", "admin_detail": "private duplicate"}, {"rule_id": "R03", "label": "PAN"}]
    assert vendor_visible_checks(checks) == [checks[1]]


@pytest.mark.parametrize("owner, label", [("Vendor", "you"), ("Reviewer", "the review team"),
                                          ("Technical retry", "you — retry the document check"),
                                          ("Complete", "no one — final decision")])
def test_vendor_owner_labels(owner, label):
    assert vendor_owner_label(owner) == label


def test_queue_row_selection_requires_one_valid_case():
    rows = [{"Application ID": "VF-CASE-1"}, {"Application ID": "VF-CASE-2"}]
    assert selected_review_case(rows, [1]) == "VF-CASE-2"
    assert selected_review_case(rows, [0]) == "VF-CASE-1"
    for bad in ([], [-1], [2], [0, 1], [True], ["0"]):
        assert selected_review_case(rows, bad) is None
    assert selected_review_case([{"Application ID": "INVALID"}], [0]) is None


def test_css_is_single_tokenized_module_and_native_scheme_is_navy():
    assert "from vendorflow.theme import apply_theme" in APP
    assert 'primaryColor = "#1E3A8A"' in CONFIG
    assert "#602C2D" not in APP
    assert (ROOT / "vendorflow/theme.py").read_text().count("!important") < 50


def test_navigation_has_compact_inner_pages_and_no_sidebar():
    assert 'st.session_state["vendor_page"] == "Welcome"' in APP
    assert 'with st.sidebar' not in APP
    assert 'st.button("Staff sign-in"' in APP
    assert 'view = st.segmented_control(' in APP
    assert "Stop tracking / sign out" not in APP


def test_recovery_code_labelled_before_first_database_write():
    fn = APP[APP.index("def new_application() -> None:"):APP.index("def track_application() -> None:")]
    card = APP[APP.index("def recovery_card("):APP.index("def new_application() -> None:")]
    assert card.count("Private tracking code") >= 1 and card.count("st.code(") == 2
    # Shown on the receipt AND before the first database write.
    assert "recovery_card(receipt.application_id, receipt.tracking_code, before_submit=False)" in fn
    prepared_at = fn.index('st.session_state.prepared_intake = prepare_intake()')
    before = fn.index("recovery_card(prepared.application_id, prepared.tracking_code, before_submit=True)")
    assert prepared_at < before < fn.index('with st.form("new_documents"):')
    assert 'Persisted: {receipt.result.persisted}' not in fn


def test_admin_click_selection_has_id_confirmation_and_revision_guard():
    assert 'on_select="rerun", selection_mode="single-row"' in APP
    assert 'selected_id = selected_review_case(queue_rows, chosen)' in APP
    assert 'if submitted and action:' in APP
    assert 'if not confirm_case:' in APP
    assert 'if action == "APPROVE" and not reviewed_evidence:' in APP
    assert 'expected_revision=int(app.get("revision", 0))' in APP
    assert 'expected_latest_run_id=app.get("latest_run_id")' in APP


def test_admin_non_pending_and_no_run_can_never_approve():
    fn = APP[APP.index("def admin_console() -> None:"):APP.index("def _track_receipt(")]
    assert 'if app.get("current_status") != "PENDING":' in fn
    assert 'if not runs:' in fn
    assert fn.index('if app.get("current_status") != "PENDING":') < fn.index('if submitted and action:')
    assert fn.index('if not runs:', fn.index('if app.get("current_status") != "PENDING":')) < fn.index('if submitted and action:')


def test_status_semantics_green_amber_red():
    assert _contrast(TOKENS["ok"], TOKENS["ok-bg"]) >= 4.5
    assert _contrast(TOKENS["warn"], TOKENS["warn-bg"]) >= 4.5
    assert _contrast(TOKENS["bad"], TOKENS["bad-bg"]) >= 4.5


def test_app_parses_and_no_backend_migration_added():
    ast.parse(APP)
    assert not list((ROOT / "supabase/migrations").glob("*design*"))
