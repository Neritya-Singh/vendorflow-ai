"""Regression checks for navigation and status/icon microfixes.

Updated in the final UI pass: navigation buttons are on_click callbacks rendered
once in the header row, the selectbox chevron is no longer shifted by a fixed
pixel offset, and the recovery card uses native copyable st.code fields.
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text()
CSS = (ROOT / "vendorflow/theme.py").read_text()


def _fn_source(name: str) -> str:
    start = APP.index(f"def {name}(")
    nxt = APP.find("\ndef ", start + 1)
    return APP[start:nxt if nxt != -1 else len(APP)]


def test_admin_header_always_offers_vendor_return():
    bar = _fn_source("render_top_bar")
    assert 'key="admin_header_vendor_portal"' in bar
    assert 'on_click=_return_to_vendor_portal' in bar
    # Not gated on authorization: reachable before sign-in and after logout.
    vp = bar.index('key="admin_header_vendor_portal"')
    assert vp < bar.index('if st.session_state.get("admin_authorized"):')
    assert APP.index('render_top_bar(is_admin_portal)') < APP.index('    admin_console()\n')
    assert 'with st.sidebar' not in APP


def test_logout_redirects_to_vendor():
    bar = _fn_source("render_top_bar")
    auth = bar.index('if st.session_state.get("admin_authorized"):')
    assert bar.index('key="admin_logout"') > auth
    assert bar.count('on_click=_return_to_vendor_portal') == 2
    # One copy of each control in the whole app (no duplicated header buttons).
    assert APP.count('"Log out"') == 1
    assert APP.count('"Vendor portal"') == 1


def test_redirect_clears_auth_and_changes_page():
    fn = next(n for n in ast.parse(APP).body
              if isinstance(n, ast.FunctionDef) and n.name == '_return_to_vendor_portal')
    state = {'admin_authorized': True, 'admin_selected_case_id': 'VF-X',
             'admin_evidence_requested': 'x', 'vendor_page': 'Track / correct application'}
    params = {'portal': 'admin'}

    class FakeStreamlit:
        session_state = state
        query_params = params

        @staticmethod
        def rerun():
            raise AssertionError('st.rerun() is a no-op inside an on_click callback')

    ns = {'st': FakeStreamlit}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), '<test>', 'exec'), ns)
    ns['_return_to_vendor_portal']()
    assert state['admin_authorized'] is False
    assert state['vendor_page'] == 'Welcome'
    assert 'admin_selected_case_id' not in state
    assert 'admin_evidence_requested' not in state
    assert params['portal'] == 'vendor'


def test_status_banners_use_clear_text_without_icon_tiles():
    assert 'column-gap:14px;' not in CSS
    assert '.vf-result-icon' not in CSS
    assert '<span class="vf-result-title">' in APP
    assert 'svg_icons' not in APP


def test_dropdown_focus_ring_on_wrapper_not_inner_input():
    # The old fixed shift targeted a BaseWeb select that Streamlit 1.66 no longer renders.
    assert 'left:-10px' not in CSS
    assert '[data-testid="stSelectbox"] div:has(> input):focus-within' in CSS
    assert '[data-testid="stSelectbox"]) :is(input,textarea):focus-visible{outline:none!important;}' in CSS


def test_recovery_card_white_with_tinted_copyable_fields():
    card = _fn_source("recovery_card")
    assert 'st.container(border=True, key="vf-recovery-card")' in card
    assert card.count('st.code(') == 2
    assert 'Application ID' in card and 'Private tracking code' in card
    assert '.st-key-vf-recovery-card' in CSS and 'background:var(--vf-surface)' in CSS
    assert 'codeBackgroundColor = "#F2F4F7"' in (ROOT / ".streamlit/config.toml").read_text()
