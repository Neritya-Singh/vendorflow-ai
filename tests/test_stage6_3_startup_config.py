"""Static regression guard for Stage 6.3 keyed navigation and local config."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_vendor_navigation_initializes_session_state_without_widget_default():
    source = (ROOT / "app.py").read_text()
    tree = ast.parse(source)
    found = []
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        if not isinstance(call.func, ast.Attribute) or call.func.attr != "segmented_control":
            continue
        if any(kw.arg == "key" and isinstance(kw.value, ast.Constant)
               and kw.value.value == "vendor_page" for kw in call.keywords):
            found.append(call)
    assert len(found) == 1
    assert all(kw.arg != "default" for kw in found[0].keywords)
    assert 'st.session_state["vendor_page"] = "Welcome"' in source


def test_secret_example_lists_admin_password_without_real_keys():
    sample = (ROOT / ".env.example").read_text()
    for name in ("GEMINI_API_KEY", "GEMINI_MODEL", "SUPABASE_URL", "SUPABASE_SECRET_KEY", "ADMIN_PASSWORD"):
        assert f"{name}=" in sample
    assert "REPLACE_LOCALLY" in sample
