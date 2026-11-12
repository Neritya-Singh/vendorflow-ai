"""Final UI pass: status banners, Streamlit 1.66 selectors, admin flow, vendor copy.

Offline, source-level checks only; no database, Gemini or browser access.
"""
from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
THEME = (ROOT / "vendorflow/theme.py").read_text(encoding="utf-8")
CONFIG = tomllib.loads((ROOT / ".streamlit/config.toml").read_text(encoding="utf-8"))["theme"]
ADMIN = APP[APP.index("def admin_console() -> None:"):APP.index("def _track_receipt(")]
EMOJI = re.compile("[☀-➿\U0001F300-\U0001FAFFⓘ]")


def _banner_source() -> str:
    return APP[APP.index("def result_banner("):APP.index("def timeline(")]


# ---------- A. Status banners ----------

def test_banner_has_no_icons_emoji_or_repeated_disclaimer():
    banner = _banner_source()
    assert not EMOJI.search(banner)
    assert "<svg" not in banner
    assert "Prototype document-consistency" not in banner
    assert "vf-result-note" not in APP


def test_banner_css_is_tint_border_and_coloured_heading_only():
    block = THEME[THEME.index(".vf-result{"):THEME.index("/* ---------- Welcome")]
    assert "box-shadow" not in block
    assert "border-left" not in block
    for status, token in (("approved", "ok"), ("pending", "warn"), ("rejected", "bad")):
        assert f".vf-result.{status}{{background:var(--vf-{token}-bg);border-color:var(--vf-{token}-border);}}" in block
        assert f".vf-result.{status} .vf-result-heading{{color:var(--vf-{token});}}" in block


def test_status_labels_unchanged():
    from vendorflow.ui_support import display_status
    assert [display_status(s) for s in ("APPROVED", "PENDING", "REJECTED")] == \
        ["Approved", "Pending Review", "Rejected"]


# ---------- D. Controls: selectors that exist in Streamlit 1.66 ----------

def test_no_dead_baseweb_or_emotion_selectors():
    from vendorflow.theme import CSS
    assert 'data-baseweb="select"' not in CSS
    assert 'data-baseweb="input"' not in CSS
    assert "st-emotion-cache" not in CSS
    assert "*:focus-visible" not in CSS  # global ring drew a second box inside fields


def test_field_edges_meet_non_text_contrast_via_token():
    for selector in ('[data-testid="stTextInputRootElement"]', '[data-testid="stTextAreaRootElement"]',
                     '[data-testid="stSelectbox"] div:has(> input)'):
        assert selector in THEME
    assert "border:1px solid var(--vf-border-input)!important" in THEME


def test_native_theme_owns_headings_alerts_and_code():
    assert CONFIG["headingFontSizes"][0] == "1.75rem"
    assert CONFIG["codeTextColor"] == "#101828"
    for colour in ("blue", "green", "yellow", "red"):
        assert f"{colour}TextColor" in CONFIG and f"{colour}BackgroundColor" in CONFIG
    assert "stAlertContentInfo" not in THEME  # no CSS re-colouring of alerts
    assert THEME.count("!important") <= 15


def test_captions_not_faded_below_aa():
    # stCaptionContainer ships with opacity .6; the muted token is only AA at full opacity.
    assert '[data-testid="stCaptionContainer"]{opacity:1;}' in THEME


# ---------- B. Navigation ----------

def test_navigation_buttons_use_callbacks_not_inline_rerun():
    bar = APP[APP.index("def render_top_bar("):APP.index("# Vendor-first navigation")]
    assert "if st.button(" not in bar
    assert bar.count("on_click=") == 3
    assert 'width="content"' in bar
    redirect = APP[APP.index("def _return_to_vendor_portal("):APP.index("def _open_staff_portal(")]
    assert "st.rerun()" not in redirect.split('"""')[-1]


def test_brand_row_keeps_india_demo_tag_on_both_portals():
    bar = APP[APP.index("def render_top_bar("):APP.index("# Vendor-first navigation")]
    assert "INDIA · DEMO" in bar
    assert APP.count("render_top_bar(is_admin_portal)") == 1


# ---------- C. Recovery credentials ----------

def test_tracking_code_never_rendered_in_admin_console():
    assert "tracking_code" not in ADMIN
    assert "tracking_token" not in ADMIN


# ---------- E. Vendor copy ----------

def test_vendor_heading_and_plain_language_purpose():
    header = APP[APP.index("def render_vendor_header("):APP.index("def render_vendor_footer(")]
    assert "Vendor onboarding made easy." in header
    for phrase in ("business and bank details", "supporting PDFs", "application status", "correction requests"):
        assert phrase in header
    assert APP.count("    render_vendor_footer()\n") == 1


def test_vendor_screens_avoid_developer_language():
    vendor = APP[APP.index("def new_application() -> None:"):APP.index("def admin_console() -> None:")]
    for jargon in ("committed run", "MVP", "prototype", "Gemini", "deterministic"):
        assert jargon not in vendor


# ---------- F. Admin review workflow ----------

def test_admin_flow_order_evidence_then_decision_then_audit():
    order = [ADMIN.index("selected_id = selected_review_case(queue_rows, chosen)"),
             ADMIN.index('st.markdown("#### Checks needing attention")'),
             ADMIN.index("admin_evidence_table("),
             ADMIN.index('with st.container(border=True, key="vf-decision-panel"):'),
             ADMIN.rindex("render_audit_details()")]
    assert order == sorted(order)


def test_finalised_case_shows_records_but_no_decision_controls():
    final = ADMIN.index('if app.get("current_status") != "PENDING":')
    ret = ADMIN.index("return", final)
    assert "render_audit_details()" in ADMIN[final:ret]
    assert final < ADMIN.index('key="vf-decision-panel"')


def test_decision_validation_messages_render_inside_panel():
    panel = ADMIN[ADMIN.index('key="vf-decision-panel"'):]
    save = panel[panel.index("def save_decision() -> None:"):panel.index("if submitted and action:")]
    for guard in ("if not confirm_case:", 'if action == "APPROVE" and not reviewed_evidence:',
                  "expected_revision=int(app.get(\"revision\", 0))"):
        assert guard in save


def test_admin_lands_on_needs_review_queue():
    init = ADMIN.index('st.session_state["admin_workspace_view"] = "Needs review"')
    assert init < ADMIN.index("view = st.segmented_control(")


def test_audit_actions_shown_in_plain_words():
    assert 'ACTION_LABELS = {"APPROVE": "Approved", "REJECT": "Rejected", "REQUEST_CORRECTION": "Correction requested"}' in APP
    assert ADMIN.count("ACTION_LABELS.get(") == 2


def test_app_still_parses():
    ast.parse(APP)


def test_pdf_evidence_is_accessible_before_the_manual_decision():
    review = APP[APP.index("def admin_console() -> None:"):APP.index("def _track_receipt(")]
    assert review.index('admin_evidence_table(') < review.index('with st.expander("Verified PDF evidence · staff only")')
    assert review.index('with st.expander("Verified PDF evidence · staff only")') < review.index('with st.container(border=True, key="vf-decision-panel")')
    assert 'repo.load_run_document(selected_id, selected_run["id"], doc_type)' in review
