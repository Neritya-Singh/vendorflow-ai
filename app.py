"""VendorFlow AI — working India-only, SYNTHETIC vendor onboarding Streamlit MVP.

All decisions, runs and documents use the actual Supabase/Gemini backend.
No backend mock is used by this UI. Never use real identity/bank records.
"""
from __future__ import annotations

import os
import secrets
from html import escape
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from vendorflow import GeminiExtractor, PDFInput, VendorSubmission, UploadError
from vendorflow.persistence import (
    MinimumIntakeError, PersistenceError, PersistentVendorService,
    SupabaseRepository, TerminalApplication, UnauthorizedTracking,
)
from vendorflow.admin_login_guard import (
    clear_admin_login_failures, remaining_admin_lockout, record_admin_login_failure,
)
from vendorflow.rules import GST_STATE_CODES
from vendorflow.ui_support import (
    comparison_assessments, comparison_rows, completed_counts, display_status, mask_sensitive,
    selected_reasons, stage_rows,
)

st.set_page_config(page_title="VendorFlow AI | Onboarding", page_icon="📋", layout="wide", initial_sidebar_state="collapsed")
load_dotenv(Path(__file__).resolve().parent / ".env")

# In Streamlit Community Cloud, these are supplied via App > Settings > Secrets.
# No secrets are rendered, logged, or passed into client-side JavaScript.
try:
    for setting in ("GEMINI_API_KEY", "GEMINI_MODEL", "SUPABASE_URL", "SUPABASE_SECRET_KEY", "ADMIN_PASSWORD"):
        value = st.secrets.get(setting)
        if value and not os.environ.get(setting):
            os.environ[setting] = str(value)
except Exception:
    # Missing Streamlit secrets file is normal for local .env development.
    pass

STATE_OPTIONS = ["Select state / UT"] + sorted(GST_STATE_CODES)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;450;500;550;600;650;700&family=Manrope:wght@500;600;650;700;800&display=swap');
:root {--vf-bg:#EDEBEC;--vf-surface:#FFFFFF;--vf-ink:#090808;--vf-muted:#6A6365;
       --vf-primary:#602C2D;--vf-primary-tint:#F4E8E9;--vf-border:#E4DFE1;}
html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
    background: var(--vf-bg); color:var(--vf-ink);
    font-family: 'Inter', ui-sans-serif, system-ui, sans-serif;
}
.block-container {max-width:1160px; padding:1.35rem 2.3rem 4rem;}
h1,h2,h3,h4,[data-testid="stMetricValue"] {font-family:'Manrope','Inter',sans-serif; letter-spacing:-.035em;}
h2,h3 {font-weight:750;color:var(--vf-ink);}
p,small,label {line-height:1.6;}
[data-testid="stHeader"] {background:transparent;}
[data-testid="stForm"] {background:var(--vf-surface);border:1px solid var(--vf-border);
    border-radius:16px;padding:1.45rem 1.65rem;box-shadow:0 5px 25px rgba(32,19,21,.025);}
[data-testid="stVerticalBlockBorderWrapper"] {border-radius:16px;}
[data-testid="stAlert"] {border-radius:12px;}
[data-testid="stFileUploader"] {border-radius:12px;}
[data-testid="stMetric"] {background:#fff;border:1px solid var(--vf-border);
    border-radius:14px;padding:.9rem 1rem;min-height:112px;}
div.stButton > button[kind="primary"], div.stFormSubmitButton > button[kind="primary"] {
    background:var(--vf-primary);border-color:var(--vf-primary); color:#fff;
}
div.stButton > button, div.stFormSubmitButton > button {
    border-radius:10px;min-height:2.7rem;font-weight:650;transition:background .14s ease;
}
div.stButton > button:focus-visible, div.stFormSubmitButton > button:focus-visible {
    outline:3px solid #C59BA1;outline-offset:2px;
}
div[data-baseweb="input"] > div, div[data-baseweb="select"] > div, textarea {
    border-radius:9px !important;}
div[data-testid="stExpander"] {background:#fff;border:1px solid var(--vf-border);border-radius:12px;}
[data-testid="stDataFrame"] {border-radius:11px;overflow:hidden;}
.vf-brand {display:flex;align-items:center;gap:.65rem;font:800 .92rem 'Manrope',sans-serif;
    letter-spacing:-.025em;color:var(--vf-ink); margin-bottom:.6rem;}
.vf-mark {display:inline-flex;align-items:center;justify-content:center;width:31px;height:31px;
    background:var(--vf-primary);color:#fff;border-radius:10px;font-size:.96rem;}
.vf-tag {display:inline-block;padding:.2rem .58rem;border:1px solid var(--vf-border);
    background:#fff;border-radius:7px;font-size:.75rem;color:var(--vf-muted);font-weight:600;}
.vf-hero {font:800 clamp(1.65rem,2.7vw,2.2rem)/1.2 'Manrope','Inter',sans-serif;
    letter-spacing:-.05em;color:var(--vf-ink);margin:.3rem 0 .45rem;}
.vf-lead {font-size:.92rem;color:var(--vf-muted);margin:0 0 1.35rem;}
.vf-section-subtitle {color:var(--vf-muted);font-size:.92rem;margin-top:-.35rem;margin-bottom:1.25rem;}
.vf-steps {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.65rem;margin:.55rem 0 1.25rem;}
.vf-step {background:rgba(255,255,255,.65);border:1px solid var(--vf-border);
    border-radius:11px;padding:.8rem .85rem;display:flex;align-items:center;gap:.62rem;
    font-size:.82rem;font-weight:600;color:var(--vf-muted);}
.vf-step.vf-active {background:#fff;border-color:var(--vf-primary);color:var(--vf-ink);
    box-shadow:0 2px 12px rgba(96,44,45,.04);}
.vf-step.vf-done {color:var(--vf-primary);}
.vf-step-index {display:inline-flex;align-items:center;justify-content:center; flex:0 0 25px;
    width:25px;height:25px;border:1px solid #D4CBCE;border-radius:50%;font-size:.78rem;}
.vf-active .vf-step-index {background:var(--vf-primary);color:#fff;border-color:var(--vf-primary);}
.vf-done .vf-step-index {background:var(--vf-primary-tint);border-color:var(--vf-primary-tint);}
.vf-summary {background:#fff;border:1px solid var(--vf-border);border-radius:14px;padding:1.1rem 1.3rem;
    margin:.65rem 0 .9rem;}
.vf-summary h4 {font:750 .96rem 'Manrope',sans-serif;margin:0 0 .55rem;}
.vf-summary p {font-size:.88rem;color:var(--vf-ink);margin:.2rem 0;overflow-wrap:anywhere;}
.vf-summary .vf-key {display:inline-block;min-width:116px;color:var(--vf-muted);}
.vf-result {background:#fff;border:1px solid var(--vf-border);border-left:5px solid var(--vf-primary);
    border-radius:14px;padding:1.1rem 1.35rem;margin:.8rem 0 1rem;}
.vf-result.approved {border-left-color:#176A4E;}
.vf-result.pending {border-left-color:#8F4620;}
.vf-result.rejected {border-left-color:#9C3039;}
.vf-result-heading {font:750 1.15rem 'Manrope','Inter',sans-serif;color:var(--vf-ink);margin:0 0 .35rem;}
.vf-result ul {margin:.35rem 0 0;padding-left:1.35rem;}
.vf-result li {font-size:.91rem;line-height:1.55;padding-bottom:.25rem;overflow-wrap:anywhere;}
.vf-result-note {font-size:.78rem;color:var(--vf-muted);margin-top:.55rem;}
.vf-callout {background:#fff;border:1px solid var(--vf-border);border-radius:14px;
    padding:1rem 1.3rem;margin:.55rem 0 1rem;}
.vf-step-live {font-size:.92rem;margin:.25rem 0;}
@media (max-width:800px) {
 .block-container {padding:1rem .9rem 3rem;}
 [data-testid="stForm"] {padding:1rem;}
 .vf-steps {grid-template-columns:1fr;gap:.32rem;}
 .vf-step {padding:.5rem .7rem;}
 .vf-hero {font-size:1.65rem;}
 .vf-summary .vf-key {min-width:95px;}
}

/* VF theme consistency: native Streamlit widgets should match light SaaS surfaces. */
[data-testid="stAppViewContainer"] {background: #EDEBEC; color: #090808;}
[data-testid="stSidebar"] {background: #F7F5F5;}
[data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label,
[data-testid="stMetricLabel"] p, [data-testid="stSidebar"] p {color: #534B4D !important;}
[data-testid="stMetricValue"], [data-testid="stMetricValue"] div {color: #181416 !important;}
[data-baseweb="input"] > div, [data-baseweb="select"] > div,
[data-baseweb="textarea"] > div {background: #FFFFFF !important; border-color: #D6CED1 !important;}
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea,
[data-baseweb="select"] input, [data-baseweb="select"] span {
    color: #20191B !important; caret-color: #602C2D !important;
}
[data-baseweb="input"] input::placeholder, [data-baseweb="textarea"] textarea::placeholder {
    color: #766E70 !important;
}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] {
    background: #FAF8F9 !important; border: 1px dashed #B9ABAF !important;
}
[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] * {color: #30282A !important;}
[data-testid="stForm"] {background: #FFFFFF !important;}
[data-testid="stMetric"] {background: #FFFFFF !important;}
/* The old :not([kind="primary"]) selector unintentionally styled some primary
   form-submit buttons as secondary. Target secondary widgets explicitly. */
button[data-testid="stBaseButton-secondary"],
button[data-testid="stBaseButton-secondaryFormSubmit"],
button[kind="secondary"] {
    color: #30282A;
    background: #FFFFFF;
    border-color: #D5C9CD;
}
/* VF 3.5.4.5: neutral review information, not a yellow error banner. */
.vf-review-notice {
    display: flex;
    align-items: flex-start;
    gap: .7rem;
    padding: .82rem 1rem;
    margin: .75rem 0 1rem;
    background: #F6F1F2;
    color: #423536;
    border: 1px solid #DED1D4;
    border-left: 3px solid #602C2D;
    border-radius: 10px;
    font: 500 .86rem/1.55 'Inter', sans-serif;
}
.vf-review-notice strong { color: #602C2D; font-weight: 700; }
.vf-review-notice-icon { color: #602C2D; font-weight: 750; font-size: 1rem; line-height: 1.35; }

.vf-staff-caption {font-size: .8rem; color: #6A6365;}

/* Stage 3.5.4.3: vendor-first emphasis and component consistency. */
[data-testid="stFormSubmitButton"] button[data-testid="stBaseButton-primary"],
[data-testid="stFormSubmitButton"] button[kind="primary"],
[data-testid="stButton"] button[data-testid="stBaseButton-primary"],
[data-testid="stButton"] button[kind="primary"] {
    background: #602C2D !important;
    border: 1px solid #602C2D !important;
    color: #FFFFFF !important;
    box-shadow: 0 3px 10px rgba(96,44,45,.13) !important;
    font-weight: 650 !important;
}
[data-testid="stFormSubmitButton"] button[data-testid="stBaseButton-primary"]:hover,
[data-testid="stFormSubmitButton"] button[kind="primary"]:hover,
[data-testid="stButton"] button[data-testid="stBaseButton-primary"]:hover,
[data-testid="stButton"] button[kind="primary"]:hover {
    background: #4D2225 !important;
    border-color: #4D2225 !important;
    color: #FFFFFF !important;
}
[data-testid="stFormSubmitButton"] button[data-testid="stBaseButton-primary"]:focus-visible,
[data-testid="stFormSubmitButton"] button[kind="primary"]:focus-visible {
    outline: 3px solid #D2A7AD !important;
    outline-offset: 3px !important;
}
/* VF CTA fix: target Streamlit primaryFormSubmit without overriding as secondary. */
button[data-testid="stBaseButton-primaryFormSubmit"],
button[data-testid="stBaseButton-primary"],
button[kind="primary"] {
    background-color: #602C2D !important;
    border: 1px solid #602C2D !important;
    color: #FFFFFF !important;
    font-weight: 650 !important;
    box-shadow: 0 3px 10px rgba(96,44,45,.13) !important;
}
button[data-testid="stBaseButton-primaryFormSubmit"]:hover,
button[data-testid="stBaseButton-primary"]:hover,
button[kind="primary"]:hover {
    background-color: #4D2225 !important;
    border-color: #4D2225 !important;
}
button[data-testid="stBaseButton-primaryFormSubmit"]:focus-visible,
button[data-testid="stBaseButton-primary"]:focus-visible {
    outline: 3px solid #D2A7AD !important;
    outline-offset: 3px !important;
}
.vf-summary .vf-key {min-width:105px;}
.vf-summary p {display:flex;align-items:baseline;gap:.6rem;margin:.43rem 0;}
.vf-summary h4 {margin-bottom:.8rem;}
.vf-summary .vf-value {color:#181416;font-weight:600;overflow-wrap:anywhere;}
.vf-summary .vf-value.vf-missing {color:#7B4146;font-weight:650;}
.vf-hint {color:#5F5558;font-size:.85rem;line-height:1.55;margin:.45rem 0 .85rem;}
.vf-hint strong {color:#392C30;}
@media (max-width:760px) {
    .vf-summary p {display:block;margin:.56rem 0;}
    .vf-summary .vf-key {display:block;min-width:0;}
}


/* Stage 3.5.5: restrained admin hierarchy, no impact on vendor form behaviour. */
.vf-admin-eyebrow {font:700 .75rem 'Inter',sans-serif;letter-spacing:.12em;text-transform:uppercase;color:#602C2D;margin:1.3rem 0 .3rem;}
.vf-admin-heading {font:750 1.35rem/1.35 'Manrope',sans-serif;letter-spacing:-.035em;color:#211A1C;margin:.15rem 0 .35rem;}
.vf-admin-subtitle {font:400 .86rem/1.5 'Inter',sans-serif;color:#685F62;margin:0 0 1.1rem;}
.vf-admin-panel {background:#fff;border:1px solid #E4DFE1;border-radius:14px;padding:1rem 1.1rem;margin:.55rem 0 1rem;}
.vf-admin-panel-title {font:700 .91rem 'Manrope',sans-serif;color:#211A1C;margin:0 0 .4rem;}
.vf-admin-panel-note {color:#685F62;font-size:.82rem;line-height:1.5;}
.vf-admin-pill {display:inline-flex;padding:.24rem .55rem;background:#F4E8E9;color:#602C2D;border-radius:8px;font:650 .76rem 'Inter',sans-serif;}
.vf-admin-issue {background:#FAF7F7;border:1px solid #E5D6D8;border-left:3px solid #8F5156;border-radius:10px;padding:.75rem .95rem;margin:.5rem 0;}
.vf-admin-issue-label {font:700 .86rem 'Inter',sans-serif;color:#3C272B;margin:0 0 .15rem;}
.vf-admin-issue-note {font:400 .83rem/1.5 'Inter',sans-serif;color:#53484B;margin:0;}
.vf-admin-ok {background:#EDF5F0;border:1px solid #CDE4D4;border-radius:10px;color:#176A4E;padding:.7rem .9rem;margin:.6rem 0;font-size:.85rem;}
.vf-admin-divider {height:1px;background:#E4DFE1;margin:1.3rem 0;}
.vf-admin-caseid {font:700 .87rem 'Inter',sans-serif;color:#602C2D;}
.vf-admin-danger-note {font:500 .82rem/1.5 'Inter',sans-serif;color:#7D424A;}
[data-testid="stSidebar"] .stRadio label p {color:#33272A !important;}
@media (max-width:780px){.vf-admin-panel{padding:.8rem;}}


/* Stage 3.5.5.2: desktop staff workspace, without changing the compact vendor flow. */
@media (min-width: 1024px) {
  body:has(.vf-admin-view-marker) [data-testid="stMainBlockContainer"],
  body:has(.vf-admin-view-marker) .block-container {
    max-width: 1440px !important;
    width: 100% !important;
  }
  body:has(.vf-admin-view-marker) [data-testid="stMainBlockContainer"] {
    padding: 1.4rem clamp(1.25rem, 3vw, 3rem) 4rem !important;
  }
}
body:has(.vf-admin-view-marker) [data-testid="stSidebar"] {
  background: #F7F5F5 !important;
}
body:has(.vf-admin-view-marker) [data-testid="stSidebar"] [role="radiogroup"] label {
  padding: .5rem .35rem;
  border-radius: 9px;
}
body:has(.vf-admin-view-marker) [data-testid="stSidebar"] .stRadio label p {
  font-size: .95rem !important;
  font-weight: 550 !important;
  color: #392F32 !important;
}
body:has(.vf-admin-view-marker) [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
  font-size: .78rem !important;
  font-weight: 700 !important;
  letter-spacing: .04em;
}
.vf-admin-heading {font-size: 1.55rem; margin: .2rem 0 .5rem;}
.vf-admin-eyebrow {font-size: .79rem; margin-top: 1.35rem;}
.vf-admin-subtitle {font-size: .94rem;}
.vf-admin-queue-note {font: 500 .9rem/1.55 'Inter',sans-serif;
    color: #5C5053; margin: -.2rem 0 .9rem;}
.vf-admin-queue-note strong {color: #602C2D;}
.vf-admin-section-label {font: 700 .95rem/1.4 'Inter',sans-serif;
    color: #3B2C30; margin: 1rem 0 .3rem;}
.vf-admin-select-hint {border-left: 3px solid #B79EA3; background: #F8F5F6;
    padding: .75rem 1rem; border-radius: 0 9px 9px 0;
    margin: .6rem 0; font: .9rem/1.55 'Inter',sans-serif; color: #554B4E;}
@media (max-width: 1023px) {
  .vf-admin-heading {font-size: 1.3rem;}
}


/* Stage 3.5.5.3: clearer document evidence and deliberately neutral decisions. */
.vf-evidence-scroll {overflow-x:auto;margin:.65rem 0 1.2rem;border-radius:13px;
    border:1px solid #E4DFE1;background:#FFF;}
.vf-evidence-table {width:100%;min-width:650px;border-collapse:collapse;
    font:500 .84rem/1.55 'Inter',sans-serif;color:#30262A;}
.vf-evidence-table th {background:#F7F4F5;color:#55494C;text-align:left;
    font-weight:700;font-size:.78rem;letter-spacing:.005em;padding:.8rem .9rem;
    border-bottom:1px solid #E4DFE1;}
.vf-evidence-table td {padding:.78rem .9rem;border-bottom:1px solid #EEE9EB;
    vertical-align:middle;overflow-wrap:anywhere;}
.vf-evidence-table tr:last-child td {border-bottom:0;}
.vf-evidence-table tr.vf-evidence-flag {background:#FCF4F5;}
.vf-evidence-table tr.vf-evidence-missing {background:#FAF7F7;}
.vf-evidence-table td:first-child {font-weight:650;}
.vf-evidence-pill {display:inline-flex;align-items:center;white-space:nowrap;
    font:700 .75rem/1.3 'Inter',sans-serif;padding:.28rem .52rem;
    border-radius:7px;background:#EDF5F0;color:#176A4E;}
.vf-evidence-pill.vf-evidence-flag {background:#F4E8E9;color:#7C3039;}
.vf-evidence-pill.vf-evidence-missing {background:#F0EDEF;color:#5E5357;}
.vf-evidence-disclaimer {font-size:.81rem;color:#5F5558;margin:.1rem 0 .9rem;}
@media(max-width:800px) {.vf-evidence-table th,.vf-evidence-table td {padding:.68rem .62rem;}}

</style>
""", unsafe_allow_html=True)


def repo_and_service() -> tuple[SupabaseRepository, PersistentVendorService]:
    """Create a server-side connection only after an authorised UI action."""
    repo = SupabaseRepository.from_env()
    return repo, PersistentVendorService(repo, GeminiExtractor())


def safe_error(exc: Exception) -> str:
    if isinstance(exc, (PersistenceError, MinimumIntakeError, UploadError, TerminalApplication,
                        UnauthorizedTracking, ValueError)):
        return str(exc)
    return "The operation could not be completed. Please retry or contact the demo administrator."


def run_with_live_stages(fn):
    """Five vendor-friendly milestones, updated only by REAL backend callbacks.

    Business-rule problems do not imply a technical failure; the saved outcome
    still determines Approved / Pending Review / Rejected.
    """
    labels = (
        "Application received",
        "Documents read and information extracted",
        "Consistency and duplicate checks",
        "Decision prepared",
        "Result saved",
    )
    step_for_stage = {"S1": 0, "S2": 1, "S3": 1, "S4": 2, "S5": 2, "S6": 2,
                      "S7": 3, "S8": 3, "S9": 4}
    final_stage = {"S1", "S3", "S6", "S8", "S9"}
    state = ["NOT_STARTED"] * len(labels)

    with st.status("Checking your application · live progress", expanded=True) as progress:
        slots = [st.empty() for _ in labels]

        def paint(i):
            icon = {"NOT_STARTED": "○", "STARTED": "◉", "COMPLETED": "✓",
                    "FAILED": "⚠", "SKIPPED": "–"}[state[i]]
            slots[i].markdown(f"{icon} **{labels[i]}**")

        for i in range(len(labels)):
            paint(i)

        def on_event(event):
            i = step_for_stage.get(event.stage_id)
            if i is None:
                return
            if event.event == "STARTED" and state[i] == "NOT_STARTED":
                state[i] = "STARTED"
            elif event.event == "FAILED":
                state[i] = "FAILED"
            elif event.event == "SKIPPED" and state[i] != "FAILED":
                state[i] = "SKIPPED"
            elif event.event == "COMPLETED" and event.stage_id in final_stage:
                if state[i] not in ("FAILED", "SKIPPED"):
                    state[i] = "COMPLETED"
            paint(i)

        try:
            result = fn(on_event)
            progress.update(label="Application check completed · result saved", state="complete", expanded=False)
            return result
        except Exception:
            progress.update(label="Processing interrupted · check the run history before retrying",
                            state="error", expanded=True)
            raise


def result_banner(status: str, reasons: list[str], *, source: str = "AUTOMATED", audience: str = "vendor") -> None:
    """Show an explained outcome; escape vendor/admin-controlled text for HTML safety."""
    title = display_status(status)
    if source == "MANUAL" and status == "APPROVED":
        title += " — after human review"
    variant = {"APPROVED": "approved", "PENDING": "pending", "REJECTED": "rejected"}.get(status, "pending")
    explanation = reasons or ["No explanation was recorded."]
    reason_html = "".join(f"<li>{escape(str(reason))}</li>" for reason in explanation[:3])
    if audience == "admin":
        next_step = {
            "APPROVED": "Final approval recorded. Review the audit history below.",
            "PENDING": "Review the flagged checks and evidence before recording a decision.",
            "REJECTED": "Final rejection recorded. This application is read-only.",
        }.get(status, "")
    else:
        next_step = {
            "APPROVED": "No further action is required in this demo.",
            "PENDING": "Review the issues below or follow your reviewer's instructions.",
            "REJECTED": "This application is final in the prototype. Contact the demo reviewer for assistance.",
        }.get(status, "")
    st.markdown(
        f'<section class="vf-result {variant}" aria-label="Application outcome">'
        f'<h3 class="vf-result-heading">{escape(title)}</h3>'
        f'<p>{escape(next_step)}</p><ul>{reason_html}</ul>'
        '<p class="vf-result-note">Prototype document-consistency decision only. '
        'Not government, bank, or legal verification.</p></section>',
        unsafe_allow_html=True,
    )


def timeline(run: dict) -> None:
    with st.expander("Execution timeline · actual saved stages"):
        st.table(stage_rows(run.get("stages_json") or []))
        if run.get("elapsed_ms") is not None:
            st.caption(f"Measured evaluation: {int(run['elapsed_ms']) / 1000:.2f} seconds · Run {run.get('id','')}")


def check_results(run: dict) -> None:
    with st.expander("All rule checks and evidence"):
        rows = []
        for c in (run.get("checks_json") or []):
            state = c.get("state", "UNKNOWN")
            detail = "Passed — no issue found" if state == "PASS" else (c.get("vendor_message") or "Requires review")
            rows.append({"Rule": c.get("rule_id"), "Check": c.get("label"),
                         "Outcome": state, "Detail": detail})
        st.dataframe(rows, hide_index=True, width="stretch")


def admin_evidence_table(claimed: dict, extracted: dict, checks: list[dict]) -> None:
    """Highlight documentary differences; never show unmasked sensitive IDs."""
    rows = comparison_assessments(claimed, extracted, checks)
    cells = []
    for row in rows:
        kind = row["Kind"]
        cells.append(
            f'<tr class="vf-evidence-{kind}">'
            f'<td>{escape(str(row["Field"]))}</td>'
            f'<td>{escape(str(row["Submitted"]))}</td>'
            f'<td>{escape(str(row["From PDF"]))}</td>'
            f'<td><span class="vf-evidence-pill vf-evidence-{kind}">'
            f'{escape(str(row["Assessment"]))}</span></td></tr>'
        )
    st.markdown(
        '<div class="vf-evidence-scroll"><table class="vf-evidence-table" '
        'aria-label="Submitted fields compared with PDF evidence">'
        '<thead><tr><th scope="col">Field</th><th scope="col">Submitted</th>'
        '<th scope="col">From PDF</th><th scope="col">Comparison</th></tr></thead>'
        '<tbody>' + ''.join(cells) + '</tbody></table></div>',
        unsafe_allow_html=True,
    )
    st.markdown('<p class="vf-evidence-disclaimer">“Consistent” means the two displayed sources agree; '
                'it does not verify a genuine registration or bank-account ownership.</p>',
                unsafe_allow_html=True)


def pdf_input(file) -> PDFInput | None:
    return PDFInput(filename=file.name, content=file.getvalue()) if file is not None else None


def draft() -> dict:
    if "new_draft" not in st.session_state:
        st.session_state.new_draft = VendorSubmission().model_dump()
    return st.session_state.new_draft


def show_step_header(index: int) -> None:
    labels = ("Business details", "Bank details", "Documents & review")
    cards = []
    for i, label in enumerate(labels):
        state = "vf-done" if i < index else "vf-active" if i == index else ""
        indicator = "✓" if i < index else str(i + 1)
        cards.append(
            f'<div class="vf-step {state}"><span class="vf-step-index">{indicator}</span>'
            f'<span>{escape(label)}</span></div>'
        )
    st.markdown('<nav class="vf-steps" aria-label="Application progress">' + ''.join(cards) + '</nav>',
                unsafe_allow_html=True)


def business_fields(current: dict, prefix: str = "new") -> dict:
    legal = st.text_input("Legal business name *", value=current.get("legal_name", ""), key=f"{prefix}_legal",
                          help="Enter the legal name shown on your GST certificate, not the trade name.")
    left, right = st.columns(2)
    with left:
        current_state = current.get("business_state", "")
        index = STATE_OPTIONS.index(current_state) if current_state in STATE_OPTIONS else 0
        state = st.selectbox("Business state / UT", STATE_OPTIONS, index=index, key=f"{prefix}_state")
        contact_name = st.text_input("Contact person", value=current.get("contact_name", ""), key=f"{prefix}_contact")
    with right:
        contact_email = st.text_input("Contact email *", value=current.get("contact_email", ""), key=f"{prefix}_email")
    st.markdown('<p class="vf-hint"><strong>Tax identifiers.</strong> PAN has 10 characters; GSTIN has 15. '
                'The PAN must match characters 3–12 of the GSTIN.</p>', unsafe_allow_html=True)
    pan_col, gstin_col = st.columns([1, 1.5])
    with pan_col:
        pan = st.text_input("PAN · 10 characters", value=current.get("pan", ""), key=f"{prefix}_pan", max_chars=10,
                            help="PAN example: ABCDE1234F. Demo data only; no government lookup.")
    with gstin_col:
        gstin = st.text_input("GSTIN · 15 characters", value=current.get("gstin", ""), key=f"{prefix}_gstin", max_chars=15,
                              help="GSTIN example: 09ABCDE1234F1Z5. It contains the PAN from characters 3–12.")
    st.caption("* Legal name and email are required to submit. Other missing values route to Pending Review.")
    return {"legal_name": legal, "business_state": "" if state == STATE_OPTIONS[0] else state,
            "contact_name": contact_name, "contact_email": contact_email, "pan": pan, "gstin": gstin}


def bank_fields(current: dict, prefix: str = "new") -> dict:
    holder = st.text_input("Account holder's name", value=current.get("bank_holder", ""), key=f"{prefix}_holder",
                           help="Enter the name printed on the bank letter or cancelled cheque.")
    left, right = st.columns(2)
    with left:
        number = st.text_input("Bank account number", value=current.get("account_number", ""),
                               key=f"{prefix}_account", help="Enter as text; leading zeros are preserved.")
    with right:
        ifsc = st.text_input("IFSC", value=current.get("ifsc", ""), key=f"{prefix}_ifsc", max_chars=11)
    st.caption("Use the name, full account number (including leading zeros) and IFSC printed on your bank document. "
               "These are compared with the PDF; no live bank verification is performed.")
    return {"bank_holder": holder, "account_number": number, "ifsc": ifsc}


def review_summary_value(value: object, *, masked: bool = False) -> str:
    """Render a safe, visibly marked missing value without exposing account numbers."""
    if value is None or str(value).strip() == "":
        return '<span class="vf-value vf-missing">Not supplied</span>'
    text = mask_sensitive(str(value)) if masked else str(value)
    return f'<span class="vf-value">{escape(text)}</span>'


def review_form_warnings(values: dict) -> list[str]:
    """Non-blocking hints; the backend remains the authority for validation."""
    notes: list[str] = []
    pan = str(values.get("pan") or "").strip().upper()
    gstin = str(values.get("gstin") or "").strip().upper()
    if pan and gstin and len(gstin) >= 12 and gstin[2:12] != pan:
        notes.append("PAN and GSTIN appear inconsistent. Confirm both values before checking your application.")
    incomplete = [name for key, name in (
        ("business_state", "business state"), ("pan", "PAN"), ("gstin", "GSTIN"),
        ("bank_holder", "bank account holder"), ("account_number", "bank account number"),
        ("ifsc", "IFSC")) if not str(values.get(key) or "").strip()]
    if incomplete:
        notes.append("Missing details: " + ", ".join(incomplete) + ". "
                     "You can still submit, but the application will require review.")
    return notes


def new_application() -> None:
    st.subheader("Start a new application")
    st.markdown('<p class="vf-section-subtitle">Three clear steps for GST-registered Indian businesses. Use synthetic sample details only.</p>',
                unsafe_allow_html=True)
    if st.session_state.get("receipt"):
        receipt = st.session_state.receipt
        st.subheader("Application check complete")
        result_banner(receipt.result.status.value, receipt.result.reasons)
        st.markdown("#### Your tracking details")
        st.markdown(f"**Application ID:** `{receipt.application_id}`")
        st.warning("Save the tracking code securely. It is shown here for this session and cannot be recovered from the database.")
        st.code(receipt.tracking_code, language=None)
        st.caption(f"Run: {receipt.result.run_id} · {receipt.result.elapsed_ms / 1000:.2f}s · Persisted: {receipt.result.persisted}")
        with st.expander("Detailed validation checks"):
            st.dataframe([{"Rule": c.rule_id, "Result": c.state.value, "Check": c.label,
                           "Details": "Passed — no issue found" if c.state.value == "PASS" else c.vendor_message}
                          for c in receipt.result.checks], hide_index=True, width="stretch")
        if st.button("Start another application"):
            st.session_state.pop("receipt", None)
            st.session_state.pop("new_draft", None)
            st.session_state.new_step = 0
            for key in [k for k in list(st.session_state) if k.startswith("new_")]:
                st.session_state.pop(key, None)
            st.rerun()
        return

    step = st.session_state.get("new_step", 0)
    show_step_header(step)
    values = draft()
    if step == 0:
        with st.form("new_business"):
            entered = business_fields(values)
            next_clicked = st.form_submit_button("Continue →", type="primary")
        if next_clicked:
            if not entered["legal_name"].strip() or not entered["contact_email"].strip():
                st.error("Legal business name and contact email are required to continue.")
            else:
                values.update(entered)
                st.session_state.new_step = 1
                st.rerun()
    elif step == 1:
        with st.form("new_banking"):
            entered = bank_fields(values)
            back_col, spacer, next_col = st.columns([1, 3, 1.5])
            with back_col:
                back = st.form_submit_button("← Back")
            with next_col:
                next_clicked = st.form_submit_button("Continue →", type="primary", width="stretch")
        if back or next_clicked:
            values.update(entered)
            st.session_state.new_step = 0 if back else 2
            st.rerun()
    else:
        st.markdown("#### Check your information before submitting")
        st.caption("Review the information below. You can go back to change any field before the check runs.")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(
                '<section class="vf-summary"><h4>Business details</h4>'
                f'<p><span class="vf-key">Legal name</span> {review_summary_value(values.get("legal_name"))}</p>'
                f'<p><span class="vf-key">PAN</span> {review_summary_value(values.get("pan"))}</p>'
                f'<p><span class="vf-key">GSTIN</span> {review_summary_value(values.get("gstin"))}</p>'
                f'<p><span class="vf-key">State</span> {review_summary_value(values.get("business_state"))}</p>'
                '</section>', unsafe_allow_html=True)
        with c2:
            st.markdown(
                '<section class="vf-summary"><h4>Banking details</h4>'
                f'<p><span class="vf-key">Account holder</span> {review_summary_value(values.get("bank_holder"))}</p>'
                f'<p><span class="vf-key">Account</span> {review_summary_value(values.get("account_number"), masked=True)}</p>'
                f'<p><span class="vf-key">IFSC</span> {review_summary_value(values.get("ifsc"))}</p>'
                '</section>', unsafe_allow_html=True)
        for note in review_form_warnings(values):
            st.markdown(
                '<div class="vf-review-notice" role="note">'
                '<span class="vf-review-notice-icon" aria-hidden="true">ⓘ</span>'
                '<div><strong>Details to review</strong><br>' + escape(note) + '</div>'
                '</div>',
                unsafe_allow_html=True,
            )
        with st.form("new_documents"):
            st.markdown("**Upload supporting documents**")
            st.caption("Upload a GST registration PDF and a bank letter or cancelled cheque PDF. "
                       "Maximum 5 MB each. Use synthetic documents only; never upload real records. "
                       "No official tax or bank verification is performed.")
            gst_file = st.file_uploader("GST registration certificate · PDF", type="pdf", key="gst_upload")
            bank_file = st.file_uploader("Bank letter or cancelled cheque · PDF", type="pdf", key="bank_upload")
            st.caption("Missing documents cause Pending Review; invalid or oversized files are refused. "
                       "Gemini reads the PDFs, while deterministic rules decide the outcome.")
            back_col, spacer, submit_col = st.columns([1, 2.4, 2])
            with back_col:
                back = st.form_submit_button("← Back")
            with submit_col:
                submit = st.form_submit_button("Check application →", type="primary", width="stretch")
        if back:
            st.session_state.new_step = 1
            st.rerun()
        if submit:
            try:
                vendor = VendorSubmission(**values)
                _, service = repo_and_service()
                receipt = run_with_live_stages(lambda cb: service.submit(
                    vendor, pdf_input(gst_file), pdf_input(bank_file), stage_callback=cb))
                st.session_state.receipt = receipt
                st.subheader("Application check complete")
                result_banner(receipt.result.status.value, receipt.result.reasons)
                st.write(f"**Application ID:** `{receipt.application_id}`")
                st.warning("Save your private tracking code now. Do not send it to anyone else.")
                st.code(receipt.tracking_code, language=None)
                st.caption(f"Saved: {receipt.result.persisted} · Run: {receipt.result.run_id} · {receipt.result.elapsed_ms / 1000:.2f}s")
            except Exception as exc:
                st.error(safe_error(exc))
                st.info("An interrupted submission may have created a preliminary record. Do not repeatedly resubmit without checking.")


def track_application() -> None:
    st.subheader("Track or correct an application")
    st.markdown('<p class="vf-section-subtitle">Check your latest decision, review any instructions and update only what needs correction.</p>',
                unsafe_allow_html=True)
    credentials = st.session_state.get("vendor_auth")
    if not credentials:
        with st.form("vendor_login"):
            app_id = st.text_input("Application ID", placeholder="VF-XXXXXXXXXXXX")
            token = st.text_input("Private tracking code", type="password")
            login = st.form_submit_button("Find application", type="primary")
        if login:
            try:
                _, service = repo_and_service()
                service.track(app_id.strip(), token.strip())
                st.session_state.vendor_auth = (app_id.strip(), token.strip())
                st.rerun()
            except Exception as exc:
                st.error(safe_error(exc))
        return

    app_id, token = credentials
    if st.button("Stop tracking / sign out"):
        st.session_state.pop("vendor_auth", None)
        st.rerun()
    try:
        repo, service = repo_and_service()
        record, runs = service.track(app_id, token)
        reviews = repo.review_history(app_id)
    except Exception as exc:
        st.session_state.pop("vendor_auth", None)
        st.error(safe_error(exc))
        return

    status = record["current_status"]
    st.caption(f"Application ID: {app_id}")
    result_banner(status, selected_reasons(record, runs, reviews), source=record.get("decision_source", "AUTOMATED"))

    # Display active administrator correction requests separately.
    if status == "PENDING" and reviews:
        latest_review = reviews[0]

        if latest_review.get("action") == "REQUEST_CORRECTION":
            from datetime import datetime

            review_at = latest_review.get("created_at")
            latest_run_at = (
                runs[0].get("created_at") or runs[0].get("finished_at")
            ) if runs else None

            # A new resubmission supersedes an earlier correction request.
            try:
                active_request = (
                    not review_at
                    or not latest_run_at
                    or datetime.fromisoformat(str(review_at).replace("Z", "+00:00"))
                    >= datetime.fromisoformat(str(latest_run_at).replace("Z", "+00:00"))
                )
            except (TypeError, ValueError):
                active_request = True

            if active_request:
                st.warning("Action required — Reviewer requested a correction")
                st.write(
                    latest_review.get("reason")
                    or "Please review your application and provide the requested correction."
                )
    if reviews and record.get("decision_source") == "MANUAL":
        st.caption("Latest reviewer decision and rationale are shown above.")
    if runs:
        timeline(runs[0])
        check_results(runs[0])
    with st.expander(f"Previous evaluations ({len(runs)})"):
        st.dataframe([{"Run": r.get("id"), "Trigger": r.get("trigger"),
                       "Automated outcome": r.get("status"), "Elapsed (s)": round(r.get("elapsed_ms",0)/1000,2),
                       "Created": str(r.get("created_at"))[:19]} for r in runs],
                     hide_index=True, width="stretch")
    if status != "PENDING":
        st.info("This outcome is final in the MVP. Contact the demo administrator if further assistance is needed.")
        return

    st.markdown("### Fix and resubmit")
    st.info("Only update the details that need correction. Your previously uploaded PDFs are reused unless you replace them.")
    current = record.get("payload_json") or {}
    with st.form("correction_form"):
        st.markdown("**Business details**")
        b = business_fields(current, prefix="edit")
        st.markdown("**Bank details**")
        k = bank_fields(current, prefix="edit")
        st.markdown("**Document replacements (optional · 5 MB maximum each)**")
        gst = st.file_uploader("Replace GST certificate · PDF", type="pdf", key="edit_gst_file")
        bank = st.file_uploader("Replace bank proof · PDF", type="pdf", key="edit_bank_file")
        submit = st.form_submit_button("Resubmit for checking", type="primary")
    if submit:
        if not b["legal_name"].strip() or not b["contact_email"].strip():
            st.error("Legal business name and contact email are required.")
            return
        try:
            updated = VendorSubmission(**b, **k)
            outcome = run_with_live_stages(lambda cb: service.resubmit(
                app_id, token, updated, gst_upload=pdf_input(gst),
                bank_upload=pdf_input(bank), stage_callback=cb))
            result_banner(outcome.status.value, outcome.reasons)
            st.success(f"New run saved: {outcome.run_id}. Refresh the tracking view to see updated history.")
            st.info("Use the tracking view or refresh the page to see the updated application and history.")
        except Exception as exc:
            st.error(safe_error(exc))
            st.info("Do not immediately retry if saving was interrupted; check the existing run history first.")



def admin_console() -> None:
    """Exception-first staff console. All mutations retain explicit case confirmation.

    Navigation/visuals use only persisted Supabase records. This function does
    not change business decisions, document handling, or vendor authentication.
    """
    expected_password = os.environ.get("ADMIN_PASSWORD", "")
    if not expected_password:
        st.error("Administrator access is not configured. Set ADMIN_PASSWORD as a server-side secret.")
        return
    if not st.session_state.get("admin_authorized"):
        st.subheader("Staff sign-in")
        st.caption("Private demo workspace for authorised finance and procurement reviewers.")
        # Limits repeated guesses within the same Streamlit session.
        # This demo-level measure does not replace server-side/IP rate limiting.
        wait_seconds = remaining_admin_lockout(st.session_state)
        if wait_seconds:
            wait_minutes = (wait_seconds + 59) // 60
            st.warning(f"Too many failed sign-in attempts. Try again in about {wait_minutes} minute(s).")
            return
        with st.form("admin_login"):
            entered = st.text_input("Demo admin password", type="password", key="admin_password_input")
            clicked = st.form_submit_button("Open Admin Console", type="primary")
        if clicked:
            if secrets.compare_digest(entered, expected_password):
                clear_admin_login_failures(st.session_state)
                st.session_state.admin_authorized = True
                st.rerun()
            else:
                locked_for = record_admin_login_failure(st.session_state)
                if locked_for:
                    st.error("Too many failed sign-in attempts. Sign-in is temporarily locked for this session.")
                else:
                    st.error("Incorrect administrator password.")
        return

    st.session_state.pop("admin_password_input", None)
    with st.sidebar:
        st.markdown('<p class="vf-admin-section-label">Staff workspace</p>', unsafe_allow_html=True)
        view = st.radio(
            "Staff navigation",
            ("Needs review", "All applications", "Decision history"),
            key="admin_workspace_view",
        )
        st.divider()
        if st.button("Log out of Admin Console", key="admin_logout", width="stretch"):
            st.session_state.admin_authorized = False
            st.session_state.pop("admin_selected_case_id", None)
            st.rerun()
    # Changing sections never keeps a previously armed decision form.
    if st.session_state.get("_vf_previous_admin_view") != view:
        st.session_state["admin_selected_case_id"] = None
        st.session_state["_vf_previous_admin_view"] = view

    notice = st.session_state.pop("admin_action_notice", None)
    if notice:
        st.success(notice)

    try:
        repo, _ = repo_and_service()
        apps = repo.admin_queue("ALL")
        run_rows = repo.client.table("runs").select("elapsed_ms").execute().data
    except Exception as exc:
        st.error(safe_error(exc))
        return

    kpis = completed_counts(apps, run_rows)
    st.markdown('<p class="vf-admin-eyebrow">Overview</p>', unsafe_allow_html=True)
    st.markdown('<h2 class="vf-admin-heading">Vendor operations at a glance</h2>', unsafe_allow_html=True)
    cols = st.columns(5)
    measures = (
        ("Applications", kpis["total"]),
        ("Approved", kpis["approved"]),
        ("Needs review", kpis["pending"]),
        ("Rejected", kpis["rejected"]),
        ("Mean check time", f"{kpis['mean_seconds']:.2f}s" if kpis["mean_seconds"] is not None else "N/A"),
    )
    for col, (title, value) in zip(cols, measures):
        col.metric(title, value)
    st.caption(
        f"Synthetic prototype data · Mean automated evaluation time from "
        f"{kpis['run_count']} saved runs (not total vendor waiting time)."
    )

    if view == "Decision history":
        st.markdown('<p class="vf-admin-eyebrow">Audit trail</p>', unsafe_allow_html=True)
        st.markdown('<h2 class="vf-admin-heading">Recent reviewer actions</h2>', unsafe_allow_html=True)
        st.markdown('<p class="vf-admin-subtitle">Read-only actions from saved audit records. Select Needs review to make decisions.</p>',
                    unsafe_allow_html=True)
        try:
            actions = (repo.client.table("review_actions")
                       .select("application_id,action,reason,actor,created_at")
                       .order("created_at", desc=True).limit(100).execute().data)
        except Exception as exc:
            st.error(safe_error(exc))
            return
        if actions:
            st.dataframe([{"Application": e.get("application_id"),
                           "Action": e.get("action"),
                           "Reason": e.get("reason"),
                           "Reviewer": e.get("actor"),
                           "Date": str(e.get("created_at", ""))[:19]}
                          for e in actions], hide_index=True, width="stretch")
        else:
            st.info("No administrator decisions have been recorded yet.")
        return

    heading = "Applications needing review" if view == "Needs review" else "All vendor applications"
    description = ("Start with outstanding exceptions. Each decision requires a reason and case confirmation."
                   if view == "Needs review" else
                   "Search and inspect previously submitted applications. Final decisions are read-only.")
    st.markdown('<p class="vf-admin-eyebrow">Review queue</p>', unsafe_allow_html=True)
    st.markdown(f'<h2 class="vf-admin-heading">{escape(heading)}</h2>', unsafe_allow_html=True)
    st.markdown(f'<p class="vf-admin-subtitle">{escape(description)}</p>', unsafe_allow_html=True)
    if view == "Needs review":
        filter_status = "PENDING"
        st.markdown('<p class="vf-admin-queue-note"><strong>Pending Review</strong> · '
                    'Oldest applications first. Select one case explicitly before taking any action.</p>',
                    unsafe_allow_html=True)
        search = st.text_input("Search by application ID or business name",
                               placeholder="Search pending applications", key="admin_search")
    else:
        col_filter, col_search = st.columns([1, 2])
        with col_filter:
            filter_status = st.selectbox(
                "Filter by status", ("ALL", "PENDING", "APPROVED", "REJECTED"),
                format_func=lambda s: "All statuses" if s == "ALL" else display_status(s),
                key="admin_status_filter",
            )
        with col_search:
            search = st.text_input("Search by application ID or business name",
                                   placeholder="Search applications", key="admin_search")
    subset = [a for a in apps
              if (filter_status == "ALL" or a.get("current_status") == filter_status)
              and (not search or search.casefold() in (
                  str(a.get("id", "")) + " " + str((a.get("payload_json") or {}).get("legal_name", ""))
              ).casefold())]
    subset.sort(key=lambda a: (a.get("current_status") != "PENDING", a.get("created_at") or ""))
    if not subset:
        st.markdown('<div class="vf-admin-panel"><p class="vf-admin-panel-title">No matching applications</p>'
                    '<p class="vf-admin-panel-note">Try a different search or switch to All applications.</p></div>',
                    unsafe_allow_html=True)
        return
    st.dataframe([{"Application ID": a.get("id"),
                   "Business": (a.get("payload_json") or {}).get("legal_name", ""),
                   "Status": display_status(a.get("current_status", "")),
                   "Submitted": str(a.get("created_at", ""))[:10]}
                  for a in subset], hide_index=True, width="stretch",
                  row_height=38, height=min(370, 48 + 38 * len(subset)))
    by_id = {a["id"]: a for a in subset}
    # Prevent accidental carryover after decision: NEVER auto-select another vendor.
    if st.session_state.pop("admin_clear_selection", False):
        st.session_state["admin_selected_case_id"] = None
    st.markdown('<p class="vf-admin-section-label">Open a case for review</p>',
                unsafe_allow_html=True)
    selected_id = st.selectbox(
        "Application to inspect", list(by_id), index=None,
        placeholder="Select a specific application to review",
        key="admin_selected_case_id",
        format_func=lambda aid: f"{aid} — {(by_id[aid].get('payload_json') or {}).get('legal_name', '')}",
    )
    if selected_id is None:
        st.markdown('<div class="vf-admin-select-hint">No case selected. Choose a specific application '
                    'above to inspect evidence. Nothing can be approved or rejected until a case is selected '
                    'and its ID is confirmed.</div>', unsafe_allow_html=True)
        return
    app = by_id[selected_id]
    try:
        runs = repo.runs_for_application(selected_id)
        reviews = repo.review_history(selected_id)
        docs = (repo.client.table("documents")
                .select("doc_type,filename,version,uploaded_at")
                .eq("application_id", selected_id)
                .order("uploaded_at", desc=True).execute().data)
    except Exception as exc:
        st.error(safe_error(exc))
        return

    st.markdown('<div class="vf-admin-divider"></div>', unsafe_allow_html=True)
    st.markdown('<p class="vf-admin-eyebrow">Case review</p>', unsafe_allow_html=True)
    st.markdown('<h2 class="vf-admin-heading">Application evidence</h2>', unsafe_allow_html=True)
    st.markdown(f'<p class="vf-admin-subtitle">Case <span class="vf-admin-caseid">{escape(selected_id)}</span> · '
                f'{escape(str((app.get("payload_json") or {}).get("legal_name", "")))}</p>',
                unsafe_allow_html=True)
    result_banner(app["current_status"], selected_reasons(app, runs, reviews),
                  source=app.get("decision_source", "AUTOMATED"), audience="admin")

    if runs:
        checks = runs[0].get("checks_json") or []
        flagged = [c for c in checks if c.get("state") != "PASS"]
        st.markdown("#### Checks requiring attention")
        if flagged:
            for c in flagged:
                label = ("Possible duplicate of an approved vendor" if c.get("rule_id") == "R12"
                         else str(c.get("label") or c.get("rule_id") or "Review required"))
                note = str(c.get("vendor_message") or "This check requires human attention.")
                st.markdown(
                    '<div class="vf-admin-issue">'
                    f'<p class="vf-admin-issue-label">{escape(label)}</p>'
                    f'<p class="vf-admin-issue-note">{escape(note)}</p>'
                    '</div>', unsafe_allow_html=True,
                )
        else:
            st.markdown('<div class="vf-admin-ok">✓ No automated checks currently require attention.</div>',
                        unsafe_allow_html=True)
        st.markdown("#### Submitted information vs. PDF evidence")
        st.caption("Highlighted rows need attention. Sensitive identifiers are masked by default.")
        admin_evidence_table(app.get("payload_json") or {}, runs[0].get("extracted_json") or {}, checks)
        check_results(runs[0])
        timeline(runs[0])
    else:
        st.info("No completed automated evaluation is available for this case.")
    with st.expander("Document versions and audit history"):
        st.markdown("**Private document metadata**")
        if docs:
            st.dataframe(docs, hide_index=True, width="stretch")
        else:
            st.caption("No documents recorded.")
        st.caption("Only private PDF metadata is shown; public document links are never generated.")
        st.markdown("**Reviewer actions**")
        if reviews:
            st.dataframe([{"Action": e.get("action"), "Reason": e.get("reason"),
                           "Reviewer": e.get("actor"), "Date": str(e.get("created_at", ""))[:19]}
                          for e in reviews], hide_index=True, width="stretch")
        else:
            st.caption("No reviewer actions yet.")
        st.markdown("**Past automated evaluations**")
        if runs:
            st.dataframe([{"Run": r.get("id"), "Trigger": r.get("trigger"),
                           "Automated outcome": r.get("status"), "Date": str(r.get("created_at", ""))[:19]}
                          for r in runs], hide_index=True, width="stretch")

    if app.get("current_status") != "PENDING":
        st.info("Final decision recorded. No further administrator actions are available for this case.")
        return
    st.markdown('<div class="vf-admin-divider"></div>', unsafe_allow_html=True)
    st.markdown('<p class="vf-admin-eyebrow">Decision desk</p>', unsafe_allow_html=True)
    st.markdown('<h2 class="vf-admin-heading">Choose a resolution</h2>', unsafe_allow_html=True)
    st.caption("Choose exactly one action, provide a reason and confirm this application's ID. "
               "A document match alone is not independent bank or tax verification.")
    with st.form(f"admin_decision_form_{selected_id}"):
        st.markdown(f'**Decision target:** `{selected_id}` — '
                    f'{(app.get("payload_json") or {}).get("legal_name", "")}',
                    unsafe_allow_html=False)
        reason = st.text_area("Reason shown to vendor and retained in audit history", max_chars=1000,
                              placeholder="Explain the specific evidence reviewed or correction required.")
        confirm_case = st.checkbox(f"I confirm this action applies to {selected_id}", value=False)
        first, second, third = st.columns(3)
        with first:
            approve = st.form_submit_button("✓ Approve after review")
        with second:
            request = st.form_submit_button("↩ Request correction")
        with third:
            reject = st.form_submit_button("✕ Reject")
    action = "APPROVE" if approve else "REQUEST_CORRECTION" if request else "REJECT" if reject else None
    if action:
        if len(reason.strip()) < 3:
            st.error("A specific written rationale is required before saving any decision.")
            return
        if not confirm_case:
            st.error(f"Confirm the application ID ({selected_id}) before saving.")
            return
        # No repeat of an unchanged correction message. Backend still protects terminal cases.
        if action == "REQUEST_CORRECTION" and reviews:
            latest = reviews[0]
            if (latest.get("action") == "REQUEST_CORRECTION"
                    and str(latest.get("reason") or "").strip() == reason.strip()):
                from datetime import datetime
                def as_dt(value):
                    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                try:
                    still_active = (not runs or as_dt(latest["created_at"]) >= as_dt(runs[0]["created_at"]))
                except (KeyError, TypeError, ValueError):
                    still_active = True
                if still_active:
                    st.info("This identical correction request is already recorded; no duplicate was saved.")
                    return
        try:
            repo.admin_review(selected_id, action, reason)
            st.session_state["admin_action_notice"] = (
                f"{action.replace('_', ' ').title()} saved for {selected_id}. "
                "Select another case to continue."
            )
            st.session_state["admin_clear_selection"] = True
            st.rerun()
        except Exception as exc:
            st.error(safe_error(exc))


# Vendor-first navigation: staff tools are not displayed on the applicant landing page.
# The ?portal=admin URL is a convenience only; admin_console() always authenticates.
is_admin_portal = st.query_params.get("portal") == "admin"
if is_admin_portal:
    st.markdown('<span class="vf-admin-view-marker" aria-hidden="true"></span>', unsafe_allow_html=True)
with st.sidebar:
    st.markdown("**VendorFlow AI**")
    st.caption("India-only synthetic demo")
    st.divider()
    if is_admin_portal:
        if st.button("← Back to Vendor Portal", key="go_vendor_portal", width="stretch"):
            st.session_state.pop("admin_authorized", None)
            st.query_params["portal"] = "vendor"
            st.rerun()
    else:
        st.markdown('<span class="vf-staff-caption">For finance and procurement staff</span>',
                    unsafe_allow_html=True)
        if st.button("Staff access", key="open_staff_portal", width="stretch"):
            st.query_params["portal"] = "admin"
            st.rerun()

st.markdown('<div class="vf-brand"><span class="vf-mark">V</span> VendorFlow AI '
            '<span class="vf-tag">INDIA · DEMO</span></div>', unsafe_allow_html=True)
if is_admin_portal:
    st.markdown('<h1 class="vf-hero">Finance operations workspace</h1>', unsafe_allow_html=True)
    st.markdown('<p class="vf-lead">Review flagged applications and record auditable decisions.</p>',
                unsafe_allow_html=True)
else:
    st.markdown('<h1 class="vf-hero">Vendor onboarding, without the back-and-forth.</h1>',
                unsafe_allow_html=True)
    st.markdown('<p class="vf-lead">A simpler way to submit documents, understand decisions and resolve exceptions.</p>',
                unsafe_allow_html=True)

if is_admin_portal:
    admin_console()
else:
    page = st.segmented_control("Vendor navigation", ["New application", "Track / correct application"],
                                default="New application", required=True, key="vendor_page",
                                label_visibility="collapsed")
    if page == "Track / correct application":
        track_application()
    else:
        new_application()
