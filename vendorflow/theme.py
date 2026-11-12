"""VendorFlow AI design tokens and scoped Streamlit CSS (Ledger Navy).

Presentation only: no workflow, rule, schema, auth or Gemini change.

Colours, heading sizes, code blocks and alert tints come from
.streamlit/config.toml (native Streamlit 1.66 theming). This module only styles
what the theme cannot: VendorFlow's own HTML components and a few widget
boundaries that must meet WCAG 1.4.11 (3:1). Selectors target the stable
`data-testid` hooks Streamlit 1.66 renders, or `st-key-*` classes from keyed
containers, never generated `st-emotion-cache-*` classes.

Usage in app.py:
    from vendorflow.theme import apply_theme
    apply_theme()
"""
from __future__ import annotations

import streamlit as st

TOKENS = {
    # Neutrals
    "bg": "#F6F7F9", "surface": "#FFFFFF", "surface-2": "#F9FAFB", "code-bg": "#F2F4F7",
    "ink": "#101828", "ink-2": "#344054", "muted": "#344054", "subtle": "#475467",
    "border": "#E4E7EC", "border-input": "#868FA0",
    # Brand
    "primary": "#1E3A8A", "primary-hover": "#172E6E", "primary-active": "#12245A",
    "primary-tint": "#EEF2FF", "primary-tint-border": "#C7D2FE", "focus": "#3B5BDB",
    # Semantic decision statuses (unchanged meaning: APPROVED / PENDING / REJECTED)
    "ok": "#067647", "ok-bg": "#ECFDF3", "ok-border": "#ABEFC6",
    "warn": "#93600A", "warn-bg": "#FFFAEB", "warn-border": "#FEDF89",
    "bad": "#B42318", "bad-bg": "#FEF3F2", "bad-border": "#FECDCA",
}

_ROOT = ";".join(f"--vf-{k}:{v}" for k, v in TOKENS.items())

CSS = """
<style>
:root {%ROOT%;
  --vf-mono:ui-monospace,'SFMono-Regular',Menlo,Consolas,monospace;
  --vf-r-md:8px;--vf-r-lg:12px;
  --vf-shadow:0 1px 2px rgba(16,24,40,.05);}

/* ---------- Base ---------- */
[data-testid="stHeader"]{background:transparent;}
.block-container,[data-testid="stMainBlockContainer"]{max-width:860px;padding:1.25rem 1.5rem 4rem;}
p,li{line-height:1.55;}
[data-testid="stCaptionContainer"],[data-testid="stCaptionContainer"] p{color:var(--vf-muted)!important;font-size:.875rem!important;line-height:1.5;}
/* Streamlit renders captions at opacity .6, which drops #344054 to ~3.4:1 on white.
   The token already encodes the intended secondary tone, so render it at full strength. */
[data-testid="stCaptionContainer"]{opacity:1;}

/* ---------- Keyboard focus ----------
   One visible ring on the control the user is on. Text fields get their ring on
   the field wrapper (below), so the inner <input> must not draw a second
   outline: in 1.66 that inner outline ran into the selectbox chevron. */
:is(button,a,summary,[role="tab"],[role="radio"]):focus-visible{outline:2px solid var(--vf-focus)!important;outline-offset:2px;}
:is([data-testid="stTextInputRootElement"],[data-testid="stTextAreaRootElement"],[data-testid="stSelectbox"]) :is(input,textarea):focus-visible{outline:none!important;}

/* ---------- Form fields (1.66 DOM: no BaseWeb wrappers) ---------- */
[data-testid="stTextInputRootElement"],
[data-testid="stTextAreaRootElement"],
[data-testid="stSelectbox"] div:has(> input){
  border:1px solid var(--vf-border-input)!important;border-radius:var(--vf-r-md);background:var(--vf-surface);}
[data-testid="stTextInputRootElement"]:focus-within,
[data-testid="stTextAreaRootElement"]:focus-within,
[data-testid="stSelectbox"] div:has(> input):focus-within{
  border-color:var(--vf-primary)!important;box-shadow:0 0 0 3px var(--vf-primary-tint-border);}
[data-testid="stWidgetLabel"] p{color:var(--vf-ink-2);font-size:.875rem;font-weight:500;}
[data-testid="stFileUploaderDropzone"]{background:var(--vf-surface-2);border:1.5px dashed var(--vf-border-input);border-radius:var(--vf-r-md);}

/* ---------- Surfaces ---------- */
[data-testid="stForm"]{background:var(--vf-surface);border-color:var(--vf-border);padding:1.5rem;box-shadow:var(--vf-shadow);}
[data-testid="stExpander"] details{background:var(--vf-surface);border-color:var(--vf-border);}
/* Bordered st.container(key=...) cards are white, not page grey. */
.st-key-vf-recovery-card,.st-key-vf-decision-panel,.st-key-vf-welcome-new,.st-key-vf-welcome-track{
  background:var(--vf-surface);border-radius:var(--vf-r-lg);box-shadow:var(--vf-shadow);}
/* The decision form sits inside the bordered panel: one border, not two. */
.st-key-vf-decision-panel [data-testid="stForm"]{border:0;box-shadow:none;padding:.25rem 0;}

/* ---------- Buttons ---------- */
/* Secondary buttons need a 3:1 edge; the theme borderColor is decorative only. */
[data-testid="stBaseButton-secondary"],[data-testid="stBaseButton-secondaryFormSubmit"]{border-color:var(--vf-border-input);}
.st-key-vf-danger button{color:var(--vf-bad);border-color:var(--vf-bad);}
.st-key-vf-danger button:hover{background:var(--vf-bad-bg);color:var(--vf-bad);border-color:var(--vf-bad);}
/* Compact header navigation (brand row). */
.st-key-vf-topnav{margin-bottom:.75rem;}
.st-key-vf-topnav button{min-height:2.25rem;padding:.3rem .9rem;font-size:.875rem;white-space:nowrap;}

/* ---------- Recovery card ---------- */
[data-testid="stMarkdownContainer"] p.vf-recovery-label{font-size:.8125rem;font-weight:600;color:var(--vf-ink-2);margin:.5rem 0 0;line-height:1.3;}
.st-key-vf-recovery-card [data-testid="stCode"] pre{border:1px solid var(--vf-border);}

/* ---------- App header ---------- */
.vf-brand{display:flex;align-items:center;gap:.6rem;font-weight:600;font-size:.95rem;color:var(--vf-ink);margin:0;}
.vf-mark{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;border-radius:var(--vf-r-md);
  background:var(--vf-primary);color:#fff;font-size:.85rem;font-weight:700;}
.vf-tag{display:inline-block;padding:.125rem .5rem;border:1px solid var(--vf-border);background:var(--vf-surface);
  border-radius:999px;font-size:.6875rem;font-weight:600;letter-spacing:.04em;color:var(--vf-muted);}
.vf-lead,.vf-section-subtitle{font-size:.9375rem;color:var(--vf-muted);margin:0 0 .75rem;}
[data-testid="stMarkdownContainer"] p.vf-demo-note{font-size:.8125rem;color:var(--vf-subtle);border-top:1px solid var(--vf-border);padding-top:.75rem;margin-top:2rem;}

/* ---------- Stepper ---------- */
.vf-mobile-step{display:none;}
.vf-mobile-progress{height:5px;border-radius:999px;margin-top:.55rem;background:var(--vf-border);overflow:hidden;}
.vf-mobile-progress span{display:block;height:100%;border-radius:999px;background:var(--vf-primary);}
.vf-steps{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.5rem;margin:.25rem 0 1.25rem;padding:0;}
.vf-step{display:flex;align-items:center;gap:.6rem;padding:.6rem .75rem;border-radius:var(--vf-r-md);
  border:1px solid var(--vf-border);background:var(--vf-surface);font-size:.8125rem;font-weight:500;color:var(--vf-subtle);}
.vf-step-index{flex:0 0 24px;width:24px;height:24px;display:inline-flex;align-items:center;justify-content:center;
  border-radius:50%;border:1px solid var(--vf-border-input);font-size:.75rem;font-weight:600;}
.vf-step.vf-active{border-color:var(--vf-primary);color:var(--vf-ink);box-shadow:0 0 0 3px var(--vf-primary-tint);}
.vf-active .vf-step-index{background:var(--vf-primary);border-color:var(--vf-primary);color:#fff;}
.vf-step.vf-done{color:var(--vf-ink-2);}
.vf-done .vf-step-index{background:var(--vf-ok-bg);border-color:var(--vf-ok-border);color:var(--vf-ok);}

/* ---------- Review summary ---------- */
.vf-summary{background:var(--vf-surface);border:1px solid var(--vf-border);border-radius:var(--vf-r-lg);padding:1rem 1.25rem;margin:.5rem 0 1rem;}
.vf-summary h4{font-size:.875rem;color:var(--vf-ink);margin:0 0 .6rem;padding:0;}
.vf-summary p{display:flex;gap:.75rem;align-items:baseline;margin:.35rem 0;font-size:.875rem;}
.vf-summary .vf-key{min-width:110px;color:var(--vf-subtle);}
.vf-summary .vf-value{color:var(--vf-ink);font-weight:500;overflow-wrap:anywhere;}
.vf-summary .vf-value.vf-missing{color:var(--vf-subtle);font-weight:400;font-style:italic;}

/* ---------- Notices ---------- */
.vf-review-notice{padding:.75rem 1rem;margin:.25rem 0 1rem;background:var(--vf-warn-bg);border:1px solid var(--vf-warn-border);
  border-radius:var(--vf-r-md);color:var(--vf-ink-2);font-size:.875rem;line-height:1.5;}
.vf-review-notice strong{color:var(--vf-warn);font-weight:600;}
.vf-work-owner{background:var(--vf-surface);border:1px solid var(--vf-border);border-radius:var(--vf-r-lg);
  padding:.85rem 1rem;margin:.25rem 0 1rem;font-size:.9375rem;color:var(--vf-ink-2);}
.vf-work-owner strong{color:var(--vf-ink);}

/* ---------- Decision / status banner ----------
   Coloured heading + subtle tint + 1px border. No icons, no shadow. Status is
   told apart by its words first and colour second. */
.vf-result{border:1px solid var(--vf-border);border-radius:var(--vf-r-lg);padding:.9rem 1.15rem;margin:.5rem 0 1rem;background:var(--vf-surface);}
.vf-result.approved{background:var(--vf-ok-bg);border-color:var(--vf-ok-border);}
.vf-result.pending{background:var(--vf-warn-bg);border-color:var(--vf-warn-border);}
.vf-result.rejected{background:var(--vf-bad-bg);border-color:var(--vf-bad-border);}
.vf-result .vf-result-heading{font-size:1.0625rem;font-weight:600;line-height:1.35;margin:0 0 .3rem;padding:0;}
.vf-result.approved .vf-result-heading{color:var(--vf-ok);}
.vf-result.pending .vf-result-heading{color:var(--vf-warn);}
.vf-result.rejected .vf-result-heading{color:var(--vf-bad);}
.vf-result p{color:var(--vf-ink-2);font-size:.9375rem;margin:0;}
.vf-result ul{margin:.55rem 0 0;padding-left:1.2rem;}
.vf-result li{font-size:.9rem;color:var(--vf-ink-2);margin:.15rem 0;overflow-wrap:anywhere;}

/* ---------- Welcome ---------- */
[data-testid="stMarkdownContainer"] p.vf-welcome-title{font-size:1rem;font-weight:600;color:var(--vf-ink);margin:0 0 .2rem;}

/* ---------- Metrics ---------- */
[data-testid="stMetric"]{background:var(--vf-surface);border:1px solid var(--vf-border);border-radius:var(--vf-r-lg);padding:.75rem 1rem;}
[data-testid="stMetricLabel"] p{color:var(--vf-muted);font-size:.8125rem;font-weight:500;}
[data-testid="stMetricValue"]{font-variant-numeric:tabular-nums;}
.st-key-vf-kpi-pending [data-testid="stMetric"]{border-color:var(--vf-warn-border);background:var(--vf-warn-bg);}

/* ---------- Admin workspace (no sidebar) ---------- */
[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="collapsedControl"]{display:none;}
.vf-admin-shell-note{font-size:.9375rem;color:var(--vf-muted);margin:-.35rem 0 .75rem;}
.vf-admin-subtitle,.vf-admin-queue-note{font-size:.9375rem;color:var(--vf-muted);margin:0 0 .75rem;}
.vf-admin-issue{background:var(--vf-surface);border:1px solid var(--vf-border-input);
  border-left:4px solid var(--vf-warn);border-radius:var(--vf-r-md);padding:.7rem 1rem;margin:.45rem 0;}
.vf-admin-issue-fail{border-left-color:var(--vf-bad);}
.vf-admin-issue-unknown{border-left-color:var(--vf-warn);}
.vf-admin-issue-type{font-size:.8125rem;font-weight:600;color:var(--vf-ink-2);margin:0 0 .15rem;}
.vf-admin-issue-label{font-size:.9375rem;font-weight:600;color:var(--vf-ink);margin:0 0 .15rem;}
.vf-admin-issue-note{font-size:.9375rem;line-height:1.5;color:var(--vf-ink-2);margin:0;}
.vf-admin-ok{background:var(--vf-ok-bg);border:1px solid var(--vf-ok-border);border-radius:var(--vf-r-md);color:var(--vf-ok);padding:.7rem .9rem;margin:.5rem 0;font-size:.9rem;}
.vf-admin-divider{height:1px;background:var(--vf-border);margin:1.5rem 0 1rem;}
.vf-admin-caseid{font:600 .9375rem var(--vf-mono);color:var(--vf-ink);}
.vf-admin-select-hint{background:var(--vf-surface-2);border:1px dashed var(--vf-border-input);border-radius:var(--vf-r-md);
  padding:.85rem 1rem;margin:.5rem 0;font-size:.9375rem;color:var(--vf-ink-2);}

/* ---------- Evidence table ---------- */
.vf-evidence-scroll{overflow-x:auto;margin:.5rem 0 .75rem;border:1px solid var(--vf-border);border-radius:var(--vf-r-lg);background:var(--vf-surface);}
.vf-evidence-table{width:100%;min-width:620px;border-collapse:collapse;font-size:.875rem;color:var(--vf-ink-2);}
.vf-evidence-table th{background:var(--vf-surface-2);color:var(--vf-subtle);text-align:left;font-weight:600;
  font-size:.75rem;letter-spacing:.03em;text-transform:uppercase;padding:.65rem .85rem;border-bottom:1px solid var(--vf-border);}
.vf-evidence-table td{padding:.65rem .85rem;border-bottom:1px solid var(--vf-border);vertical-align:middle;overflow-wrap:anywhere;}
.vf-evidence-table td:nth-child(2),.vf-evidence-table td:nth-child(3){font-family:var(--vf-mono);font-size:.8125rem;}
.vf-evidence-table td:first-child{font-weight:600;color:var(--vf-ink);}
.vf-evidence-table tr:last-child td{border-bottom:0;}
.vf-evidence-table tr.vf-evidence-flag{background:var(--vf-warn-bg);}
.vf-evidence-pill{display:inline-flex;align-items:center;padding:.125rem .5rem;border-radius:999px;font-size:.75rem;font-weight:600;line-height:1.5;
  border:1px solid var(--vf-ok-border);background:var(--vf-ok-bg);color:var(--vf-ok);white-space:nowrap;}
.vf-evidence-pill.vf-evidence-flag{border-color:var(--vf-warn-border);background:var(--vf-warn-bg);color:var(--vf-warn);}
.vf-evidence-pill.vf-evidence-missing{border-color:var(--vf-border);background:var(--vf-surface-2);color:var(--vf-muted);}
.vf-evidence-disclaimer{font-size:.8125rem;color:var(--vf-subtle);margin:0 0 1rem;}

/* Wider canvas for staff only */
@media (min-width:1024px){
  body:has(.vf-admin-view-marker) .block-container,
  body:has(.vf-admin-view-marker) [data-testid="stMainBlockContainer"]{max-width:1360px!important;padding:1.25rem 2.5rem 4rem!important;}}

/* ---------- Mobile ---------- */
@media (max-width:760px){
  .block-container,[data-testid="stMainBlockContainer"]{padding:.75rem .9rem 3rem!important;}
  [data-testid="stForm"]{padding:1rem;}
  .vf-steps{display:none;}
  .vf-mobile-step{display:block;background:var(--vf-surface);border:1px solid var(--vf-border-input);
    border-radius:var(--vf-r-md);padding:.65rem .85rem;margin:.25rem 0 1.25rem;
    color:var(--vf-ink-2);font-size:.9375rem;}
  .vf-summary p{display:block;}
  .vf-summary .vf-key{display:block;min-width:0;}
}
@media (prefers-reduced-motion:reduce){*{transition:none!important;animation:none!important;}}
</style>
""".replace("%ROOT%", _ROOT)


def apply_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def status_badge(status: str) -> str:
    """HTML badge for APPROVED / PENDING / REJECTED (labels unchanged)."""
    from html import escape
    labels = {"APPROVED": "Approved", "PENDING": "Pending Review", "REJECTED": "Rejected"}
    variant = {"APPROVED": "approved", "PENDING": "pending", "REJECTED": "rejected"}.get(status, "pending")
    return f'<span class="vf-badge {variant}">{escape(labels.get(status, status))}</span>'
