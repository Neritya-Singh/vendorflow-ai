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
    PreparedIntake, prepare_intake,
)
from vendorflow.admin_login_guard import (
    clear_admin_login_failures, remaining_admin_lockout, record_admin_login_failure,
)
from vendorflow.rules import GST_STATE_CODES
from vendorflow.ux_support import (
    VENDOR_NAV, active_review_request, admin_queue_rows, committed_pdf_types,
    next_action_owner, valid_contact_email, vendor_next_step, vendor_owner_label, selected_review_case,
)
from vendorflow.ui_support import (
    comparison_assessments, comparison_rows, completed_counts, display_status, mask_sensitive,
    selected_reasons, stage_rows, vendor_visible_checks,
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

from vendorflow.theme import apply_theme
apply_theme()


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
    reviewer_prefixes = ("Reviewer requested correction", "Rejected by reviewer", "Approved after human review")
    reason_html = "".join(
        f"<li><em>{escape(str(reason))}</em></li>"
        if str(reason).startswith(reviewer_prefixes)
        else f"<li>{escape(str(reason))}</li>"
        for reason in explanation[:3]
    )
    if audience == "admin":
        next_step = {
            "APPROVED": "Final decision. This application is read-only.",
            "PENDING": "Check the items below and the document comparison before deciding.",
            "REJECTED": "Final decision. This application is read-only.",
        }.get(status, "")
    else:
        next_step = {
            "APPROVED": "Your details match your documents. You don't need to do anything else.",
            "PENDING": "A few things need attention before this application can be approved:",
            "REJECTED": "This application can't be approved. Contact the review team if you need help.",
        }.get(status, "")
    # The "not official verification" limitation is stated once per page
    # (vendor footer / admin evidence note), not repeated inside every banner.
    st.markdown(
        f'<section class="vf-result {variant}" role="status" aria-label="Application status: {escape(title)}">'
        f'<h3 class="vf-result-heading"><span class="vf-result-title">{escape(title)}</span></h3>'
        f'<p>{escape(next_step)}</p><ul>{reason_html}</ul></section>',
        unsafe_allow_html=True,
    )


def timeline(run: dict) -> None:
    with st.expander("Execution timeline · actual saved stages"):
        st.table(stage_rows(run.get("stages_json") or []))
        if run.get("elapsed_ms") is not None:
            st.caption(f"Measured evaluation: {int(run['elapsed_ms']) / 1000:.2f} seconds · Run {run.get('id','')}")


def check_results(run: dict) -> None:
    with st.expander("All checks"):
        rows = []
        for c in vendor_visible_checks(run.get("checks_json") or []):
            state = c.get("state", "UNKNOWN")
            detail = "Passed — no issue found" if state == "PASS" else (c.get("vendor_message") or "Requires review")
            rows.append({"Check": c.get("label"), "Outcome": state, "Detail": detail})
        st.dataframe(rows, hide_index=True, width="stretch")


def staff_check_results(run: dict) -> None:
    """Reviewer-only detail, including R12; never reuse this in the vendor portal."""
    with st.expander("All reviewer checks and rule evidence"):
        rows = [{"Rule": c.get("rule_id"), "Check": c.get("label"),
                 "Outcome": c.get("state"),
                 "Evidence": c.get("admin_detail") or c.get("vendor_message") or "Requires review"}
                for c in run.get("checks_json") or []]
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
    st.markdown(
        f'<div class="vf-mobile-step" aria-label="Step {index + 1} of 3: {escape(labels[index])}">'
        f'<strong>Step {index + 1} of 3</strong> · {escape(labels[index])}'
        f'<div class="vf-mobile-progress" role="progressbar" aria-valuemin="0" '
        f'aria-valuemax="3" aria-valuenow="{index + 1}">'
        f'<span style="width:{(index + 1) / 3 * 100:.2f}%"></span></div></div>',
        unsafe_allow_html=True,
    )


def business_fields(current: dict, prefix: str = "new") -> dict:
    legal = st.text_input("Legal business name (required)", value=current.get("legal_name", ""), key=f"{prefix}_legal",
                          help="Enter the legal name shown on your GST certificate, not the trade name.")
    # Group contact details together. In the previous two-column layout the
    # optional contact person sat below State, opposite an unrelated email field.
    left, right = st.columns(2)
    with left:
        contact_email = st.text_input("Contact email (required)", value=current.get("contact_email", ""), key=f"{prefix}_email")
    with right:
        contact_name = st.text_input("Contact person (optional)", value=current.get("contact_name", ""), key=f"{prefix}_contact",
                                     help="Optional for submitting; missing information may lead to Pending Review.")
    current_state = current.get("business_state", "")
    index = STATE_OPTIONS.index(current_state) if current_state in STATE_OPTIONS else 0
    state = st.selectbox("Business state / UT", STATE_OPTIONS, index=index, key=f"{prefix}_state")
    st.markdown('<p class="vf-hint"><strong>Business identifiers.</strong> Enter the PAN and GSTIN used for this vendor account. '
                'They will be checked against the uploaded GST certificate.</p>', unsafe_allow_html=True)
    pan_col, gstin_col = st.columns([1, 1.5])
    with pan_col:
        pan = st.text_input("PAN · 10 characters", value=current.get("pan", ""), key=f"{prefix}_pan", max_chars=10,
                            help="PAN example: ABCDE1234F. Demo data only; no government lookup.")
    with gstin_col:
        gstin = st.text_input("GSTIN · 15 characters", value=current.get("gstin", ""), key=f"{prefix}_gstin", max_chars=15,
                              help="GSTIN example: 09ABCDE1234F1Z5. It contains the PAN from characters 3–12.")
    st.caption("Legal business name and contact email are required. Other missing details may lead to Pending Review.")
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
    st.caption("Enter these exactly as printed on your bank letter or cancelled cheque, including any leading zeros.")
    return {"bank_holder": holder, "account_number": number, "ifsc": ifsc}


def recovery_card(application_id: str, tracking_code: str, *, before_submit: bool) -> None:
    """White card, labelled identifiers in tinted copyable code fields.

    st.code provides the native copy button. Only the vendor's own session ever
    renders the tracking code; it is never placed in an admin or public table.
    """
    with st.container(border=True, key="vf-recovery-card"):
        if before_submit:
            st.markdown("**Save your recovery details before submitting**")
            st.caption("If saving is interrupted, use both to resume this same application. "
                       "The private code can't be recovered later.")
        else:
            st.markdown("**Save your recovery details**")
            st.caption("You need both to track or correct this application. Keep the private code secure.")
        st.markdown('<p class="vf-recovery-label">Application ID</p>', unsafe_allow_html=True)
        st.code(application_id, language=None)
        st.markdown('<p class="vf-recovery-label">Private tracking code</p>', unsafe_allow_html=True)
        st.code(tracking_code, language=None)


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
    incomplete = [name for key, name in (
        ("business_state", "business state"), ("pan", "PAN"), ("gstin", "GSTIN"),
        ("bank_holder", "bank account holder"), ("account_number", "bank account number"),
        ("ifsc", "IFSC")) if not str(values.get(key) or "").strip()]
    if incomplete:
        notes.append("Missing details: " + ", ".join(incomplete) + ". "
                     "You can still submit, but the application will require review.")
    return notes


def new_application() -> None:
    if st.session_state.get("receipt"):
        receipt = st.session_state.receipt
        st.subheader("Application result and receipt")
        result_banner(receipt.result.status.value, receipt.result.reasons)
        receipt_run = {
            "checks_json": [c.model_dump(mode="json") for c in receipt.result.checks],
            "extraction_error": receipt.result.extraction_error,
        }
        receipt_app = {"current_status": receipt.result.status.value}
        st.markdown('<div class="vf-work-owner" role="status"><strong>Next step</strong><div>'
                    f'{escape(vendor_next_step(receipt_app, receipt_run))}</div></div>', unsafe_allow_html=True)
        recovery_card(receipt.application_id, receipt.tracking_code, before_submit=False)
        with st.expander("All checks"):
            st.dataframe([{"Result": c["state"], "Check": c["label"],
                           "Details": "Passed — no issue found" if c["state"] == "PASS" else c["vendor_message"]}
                          for c in vendor_visible_checks([c.model_dump(mode="json") for c in receipt.result.checks])], hide_index=True, width="stretch")
        track_col, another_col, _ = st.columns([1.3, 1.3, 2], vertical_alignment="center")
        with track_col:
            st.button("Track this application", key="receipt_track_current", type="primary", width="stretch",
                      on_click=_track_receipt, args=(receipt.application_id, receipt.tracking_code))
        with another_col:
            another = st.button("Start another application", width="stretch")
        if another:
            st.session_state.pop("receipt", None)
            st.session_state.pop("new_draft", None)
            st.session_state.pop("prepared_intake", None)
            st.session_state.new_step = 0
            for key in [k for k in list(st.session_state) if k.startswith("new_")]:
                st.session_state.pop(key, None)
            st.rerun()
        return

    st.subheader("Start a new application")
    st.markdown('<p class="vf-section-subtitle">Complete these three steps to submit your vendor onboarding details.</p>',
                unsafe_allow_html=True)
    step = st.session_state.get("new_step", 0)
    show_step_header(step)
    values = draft()
    if step == 0:
        with st.form("new_business"):
            entered = business_fields(values)
            next_clicked = st.form_submit_button("Continue →", type="primary")
        if next_clicked:
            if not entered["legal_name"].strip():
                st.error("Enter the legal business name to continue.")
            elif not valid_contact_email(entered["contact_email"]):
                st.error("Enter a valid contact email address, such as contact@example.com.")
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
                '<strong>Details to review</strong><br>' + escape(note) +
                '</div>',
                unsafe_allow_html=True,
            )
        # Issue the receipt credentials BEFORE any network/database write.
        # The vendor can track/recover the same application after a crash.
        if "prepared_intake" not in st.session_state:
            st.session_state.prepared_intake = prepare_intake()
        prepared = st.session_state.prepared_intake
        recovery_card(prepared.application_id, prepared.tracking_code, before_submit=True)
        with st.form("new_documents"):
            st.markdown("**Upload supporting documents**")
            st.caption("PDF only, up to 5 MB each. You can still submit without a document, "
                       "but the application will then need review.")
            gst_file = st.file_uploader("GST registration certificate · PDF", type="pdf", key="gst_upload")
            bank_file = st.file_uploader("Bank letter or cancelled cheque · PDF", type="pdf", key="bank_upload")
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
                    vendor, pdf_input(gst_file), pdf_input(bank_file), stage_callback=cb,
                    prepared=prepared))
                # Show ONE authoritative result and receipt, not the still-filled form.
                # The prepared ID remains stable if a failure occurs before this point.
                st.session_state.receipt = receipt
                st.rerun()
            except Exception as exc:
                st.error(safe_error(exc) + " Your recovery details above still work: retry here, "
                         "or use Track / correct later. No second application is created.")


def track_application() -> None:
    st.subheader("Track or correct an application")
    st.markdown('<p class="vf-section-subtitle">Check your latest status, read any reviewer notes, and update only what needs correction.</p>',
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
    id_col, signout_col = st.columns([4, 1], vertical_alignment="center")
    with id_col:
        st.markdown(f"Application **`{app_id}`**")  # set only after a successful service.track()
    with signout_col:
        st.button("Sign out", key="vendor_signout", width="stretch",
                  on_click=lambda: st.session_state.pop("vendor_auth", None))
    try:
        repo, service = repo_and_service()
        record, runs = service.track(app_id, token)
        reviews = repo.review_history(app_id)
    except Exception as exc:
        st.session_state.pop("vendor_auth", None)
        st.error(safe_error(exc))
        return

    if not runs and record["current_status"] == "PENDING":
        st.warning("Submission interrupted before the first decision was saved. "
                   "You can resume using this same application ID and tracking code.")
        st.caption("Upload your documents again to ensure the resumed decision uses exactly "
                   "the PDFs you choose. Earlier incomplete uploads are never reused automatically.")
        with st.form("resume_initial_form"):
            b = business_fields(record.get("payload_json") or {}, prefix="resume")
            k = bank_fields(record.get("payload_json") or {}, prefix="resume")
            rgst = st.file_uploader("GST certificate · PDF", type="pdf", key="resume_gst")
            rbank = st.file_uploader("Bank proof · PDF", type="pdf", key="resume_bank")
            resume = st.form_submit_button("Resume this application", type="primary")
        if resume:
            try:
                recovered = run_with_live_stages(lambda cb: service.resume_submission(
                    app_id, token, VendorSubmission(**b, **k),
                    pdf_input(rgst), pdf_input(rbank), stage_callback=cb))
                st.session_state.vendor_action_notice = (
                    "The interrupted submission was recovered on the same application. "
                    "Your current status and run history are shown below."
                )
                st.rerun()
            except Exception as exc:
                st.error(safe_error(exc))
        return

    status = record["current_status"]
    notice = st.session_state.pop("vendor_action_notice", None)
    if notice:
        st.success(notice)
    result_banner(status, selected_reasons(record, runs, reviews, audience="vendor"), source=record.get("decision_source", "AUTOMATED"))
    latest_run = runs[0] if runs else None
    latest_review = reviews[0] if reviews else None
    owner = next_action_owner(record, latest_run, latest_review)
    st.markdown(
        '<div class="vf-work-owner" role="status">'
        f'<strong>Waiting on: {escape(vendor_owner_label(owner))}</strong><div>'
        f'{escape(vendor_next_step(record, latest_run, latest_review))}</div></div>',
        unsafe_allow_html=True,
    )

    # A new saved evaluation supersedes an earlier correction instruction.
    # selected_reasons() already puts a manual reviewer message in the status
    # banner; only show it separately if the banner would not contain it.
    if (status == "PENDING" and active_review_request(latest_review, latest_run)
            and record.get("decision_source") != "MANUAL"):
        from vendorflow.ui_support import vendor_safe_review_reason
        st.warning("**Message from the review team:** " + vendor_safe_review_reason(
            str(latest_review.get("reason") or
                "Please review your application and provide the requested correction.")))
    if runs:
        check_results(runs[0])
    with st.expander(f"History · {len(runs)} {'evaluation' if len(runs) == 1 else 'evaluations'}"):
        st.dataframe([{"Evaluation": "Initial" if r.get("trigger") == "submission" else "Correction",
                       "Outcome": display_status(str(r.get("status") or "")),
                       "Date": str(r.get("created_at"))[:19]} for r in runs],
                     hide_index=True, width="stretch")
    if status != "PENDING":
        return  # "Waiting on: no one — final decision" above already says so.

    st.markdown("### Correct or retry")
    guidance = {
        "Reviewer": "The review team is checking your application. You only need to resubmit if you have new information.",
        "Technical retry": "Processing was interrupted. Retry the check; your application ID stays the same.",
    }.get(owner, "Change only what needs fixing. Your current PDFs are reused unless you upload a replacement.")
    st.caption(guidance)
    with st.expander("Fix and resubmit", expanded=(owner in {"Vendor", "Technical retry"})):
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
            if not b["legal_name"].strip():
                st.error("Enter the legal business name.")
                return
            if not valid_contact_email(b["contact_email"]):
                st.error("Enter a valid contact email address.")
                return
            try:
                updated = VendorSubmission(**b, **k)
                outcome = run_with_live_stages(lambda cb: service.resubmit(
                    app_id, token, updated, gst_upload=pdf_input(gst),
                    bank_upload=pdf_input(bank), stage_callback=cb,
                    expected_revision=int(record.get("revision", 0)),
                    expected_latest_run_id=record.get("latest_run_id")))
                st.session_state.vendor_action_notice = (
                    "Your updated application was saved. The latest status and history are shown below."
                )
                # Freshly read the authoritative revision and decision on the rerun.
                st.rerun()
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
    # Vendor portal and Log out live once, in the compact header row
    # (render_top_bar). No second copy of either control is drawn here.
    st.markdown('<h2>Admin Console</h2><p class="vf-admin-shell-note">Review applications, inspect evidence '
                'and record decisions.</p>', unsafe_allow_html=True)
    # Land reviewers on the exception queue; without this no tab is selected
    # and the page silently fell through to "All applications".
    if st.session_state.get("admin_workspace_view") not in ("Needs review", "All applications", "Decision history"):
        st.session_state["admin_workspace_view"] = "Needs review"
    view = st.segmented_control(
        "Admin workspace",
        ("Needs review", "All applications", "Decision history"),
        key="admin_workspace_view",
        required=True,
        label_visibility="collapsed",
    )
    # Changing sections never keeps a previously armed decision form.
    if st.session_state.get("_vf_previous_admin_view") != view:
        st.session_state["_vf_previous_admin_view"] = view

    notice = st.session_state.pop("admin_action_notice", None)
    if notice:
        st.success(notice)

    try:
        repo, _ = repo_and_service()
        apps = repo.admin_queue("ALL")
        run_rows = (repo.client.table("runs")
                    .select("id,application_id,checks_json,reasons_json,elapsed_ms,created_at,finished_at,extraction_error")
                    .limit(1000).execute().data)
        reviewer_rows = (repo.client.table("review_actions")
                         .select("application_id,action,reason,created_at,reviewed_run_id")
                         .order("created_at", desc=True).limit(1000).execute().data)
        latest_runs = {r["id"]: r for r in run_rows if r.get("id")}
        latest_reviews = {}
        for action_row in reviewer_rows:
            if action_row.get("application_id") not in latest_reviews:
                latest_reviews[action_row["application_id"]] = action_row
    except Exception as exc:
        st.error(safe_error(exc))
        return

    kpis = completed_counts(apps, run_rows)
    st.markdown("### Workload overview")
    cols = st.columns(5)
    measures = (
        ("Applications", kpis["total"]),
        ("Approved", kpis["approved"]),
        ("Needs review", kpis["pending"]),
        ("Rejected", kpis["rejected"]),
        ("Mean automated check", f"{kpis['mean_seconds']:.2f}s" if kpis["mean_seconds"] is not None else "N/A"),
    )
    for col, (title, value) in zip(cols, measures):
        with col:
            if title == "Needs review":
                with st.container(key="vf-kpi-pending"):
                    st.metric(title, value)
            else:
                st.metric(title, value)
    st.caption(
        f"Synthetic prototype data · Mean automated evaluation time from "
        f"{kpis['run_count']} saved runs (not total vendor waiting time)."
    )

    if view == "Decision history":
        st.markdown("### Recent reviewer actions")
        st.markdown('<p class="vf-admin-subtitle">Read-only audit records. Open Needs review to make a decision.</p>',
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
                           "Action": ACTION_LABELS.get(str(e.get("action")), e.get("action")),
                           "Reason": e.get("reason"),
                           "Reviewer": e.get("actor"),
                           "Date": str(e.get("created_at", ""))[:19]}
                          for e in actions], hide_index=True, width="stretch")
        else:
            st.info("No administrator decisions have been recorded yet.")
        return

    heading = "Applications needing review" if view == "Needs review" else "All vendor applications"
    description = ("Pending Review cases, oldest first. Select a row to open the case."
                   if view == "Needs review" else
                   "Every submitted application. Final decisions are read-only.")
    st.markdown(f"### {heading}")
    st.markdown(f'<p class="vf-admin-subtitle">{escape(description)}</p>', unsafe_allow_html=True)
    if view == "Needs review":
        filter_status = "PENDING"
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
        message = ("No matching applications. Try another search."
                   if search else "All clear — no applications in this view.")
        st.info(message)
        return
    # The dataframe's selection state is read-only. Change the widget key after a
    # saved decision; changing filters/search also produces a fresh keyed view.
    if st.session_state.pop("admin_clear_selection", False):
        st.session_state["admin_queue_epoch"] = st.session_state.get("admin_queue_epoch", 0) + 1
    queue_key = f"admin_queue_{view}_{filter_status}_{search}_{st.session_state.get('admin_queue_epoch', 0)}"
    queue_rows = admin_queue_rows(subset, latest_runs, latest_reviews)
    import pandas as pd
    queue_df = pd.DataFrame(queue_rows)
    status_styles = {"Approved": "color:#067647;background:#ECFDF3",
                     "Pending Review": "color:#93600A;background:#FFFAEB",
                     "Rejected": "color:#B42318;background:#FEF3F2"}
    styled_queue = queue_df.style.map(lambda v: status_styles.get(v, ""), subset=["Status"])
    event = st.dataframe(styled_queue, hide_index=True, width="stretch", row_height=42,
                         height=min(400, 52 + 42 * len(subset)),
                         on_select="rerun", selection_mode="single-row", key=queue_key)
    st.caption("Select a case to view its evidence below. Selecting a row never changes its decision.")
    by_id = {a["id"]: a for a in subset}
    chosen = event.selection.rows
    selected_id = selected_review_case(queue_rows, chosen)
    if selected_id is None:
        st.markdown('<div class="vf-admin-select-hint">No case selected. Choose a specific application '
                    'above to inspect evidence. Nothing can be approved or rejected until a case is selected '
                    'and its ID is confirmed.</div>', unsafe_allow_html=True)
        return
    app = by_id[selected_id]
    try:
        runs = repo.runs_for_application(selected_id)
        reviews = repo.review_history(selected_id)
    except Exception as exc:
        st.error(safe_error(exc))
        return

    st.markdown('<div class="vf-admin-divider"></div>', unsafe_allow_html=True)
    st.markdown(f'<h3>Case <span class="vf-admin-caseid">{escape(selected_id)}</span> · '
                f'{escape(str((app.get("payload_json") or {}).get("legal_name", "")))}</h3>',
                unsafe_allow_html=True)
    # The split panel compressed evidence to ~2/3 width, left half the canvas
    # unused for final cases, and put the decision control beside rather than
    # after the evidence. The Stage 6.3 full-width review was easier to scan.
    result_banner(app["current_status"], selected_reasons(app, runs, reviews),
                  source=app.get("decision_source", "AUTOMATED"), audience="admin")
    from vendorflow.ux_support import primary_review_issue
    st.caption(f"Revision {int(app.get('revision', 0))} · "
               f"Next action: {next_action_owner(app, runs[0] if runs else None, reviews[0] if reviews else None)}"
               f" · {primary_review_issue(runs[0] if runs else None, reviews[0] if reviews else None)}")
    # Bound to this exact case+run, never to the latest uncommitted upload.
    selected_run = runs[0] if runs else None
    current_evidence_key = (selected_id, selected_run.get("id") if selected_run else None)

    if runs:
        checks = runs[0].get("checks_json") or []
        from vendorflow.ux_support import admin_review_issue_groups
        failed, unverified = admin_review_issue_groups(checks)
        st.markdown("#### Checks needing attention")
        if failed or unverified:
            st.markdown(
                f"**{len(failed)} needing correction · {len(unverified)} awaiting verification**"
            )

            def render_issue(issue: dict) -> None:
                kind = "vf-admin-issue-fail" if issue["state"] == "FAIL" else "vf-admin-issue-unknown"
                heading = "Correction needed" if issue["state"] == "FAIL" else "Not yet verified"
                st.markdown(
                    f'<div class="vf-admin-issue {kind}">'
                    f'<p class="vf-admin-issue-type">{heading}</p>'
                    f'<p class="vf-admin-issue-label">{escape(issue["label"])}</p>'
                    f'<p class="vf-admin-issue-note">{escape(issue["note"])}</p>'
                    '</div>', unsafe_allow_html=True,
                )

            priority = (failed + unverified)
            for issue in priority[:3]:
                render_issue(issue)
            if len(priority) > 3:
                with st.expander(f"Show {len(priority) - 3} more checks needing attention"):
                    for issue in priority[3:]:
                        render_issue(issue)
        else:
            st.markdown('<div class="vf-admin-ok">All automated checks passed.</div>',
                        unsafe_allow_html=True)
        st.markdown("#### Submitted information vs. PDF evidence")
        st.caption("Highlighted rows need attention. Sensitive identifiers are masked by default.")
        admin_evidence_table(app.get("payload_json") or {}, runs[0].get("extracted_json") or {}, checks)
        staff_check_results(runs[0])
    else:
        st.info("No completed automated evaluation is available for this case.")

    # A reviewer should have access to the exact verified PDFs BEFORE choosing a decision.
    # This remains read-only and stays bound to the selected committed run.
    with st.expander("Verified PDF evidence · staff only"):
        if selected_run:
            pdf_types = committed_pdf_types(selected_run)
            if pdf_types:
                st.caption("Only PDFs referenced by the latest committed run can be downloaded. "
                           "Files are checked against the saved SHA-256 before delivery.")
                if st.button("Load this run's verified PDFs", key=f"admin_load_evidence_{selected_id}"):
                    st.session_state["admin_evidence_requested"] = current_evidence_key
                if st.session_state.get("admin_evidence_requested") == current_evidence_key:
                    for doc_type in pdf_types:
                        try:
                            pdf = repo.load_run_document(selected_id, selected_run["id"], doc_type)
                            if pdf is not None:
                                st.download_button(
                                    f"Download {doc_type} · committed PDF",
                                    data=pdf.content,
                                    file_name=f"{selected_id}_{selected_run['id']}_{doc_type}.pdf",
                                    mime="application/pdf",
                                    key=f"admin_evidence_{selected_id}_{selected_run['id']}_{doc_type}",
                                )
                        except Exception:
                            st.error(f"The {doc_type} PDF could not be verified. No download was provided.")
            else:
                st.caption("No committed PDF references are available for this run.")
        else:
            st.caption("No completed run is available; there is no verified evidence to download.")

    def render_audit_details() -> None:
        """Supporting records, shown after the decision step (or after evidence for final cases)."""
        st.markdown("#### Documents and audit history")
        if runs:
            timeline(runs[0])
        with st.expander("Document versions and audit history"):
            st.markdown("**Exact PDF versions bound to each committed evaluation**")
            evidence_rows = []
            for run in runs:
                for entry in run.get("document_manifest") or []:
                    evidence_rows.append({"Run": run.get("id"),
                                          "Type": entry.get("doc_type"),
                                          "Version": entry.get("version"),
                                          "SHA-256": entry.get("file_sha256", "")[:16] + "…"})
            if evidence_rows:
                st.dataframe(evidence_rows, hide_index=True, width="stretch")
            else:
                st.caption("No committed document references; replacement PDFs must be uploaded for evaluation.")
            st.caption("Staged or interrupted uploads are not evidence for a completed run. "
                       "Private PDFs are never exposed through public links.")
            st.markdown("**Reviewer actions**")
            if reviews:
                st.dataframe([{"Action": ACTION_LABELS.get(str(e.get("action")), e.get("action")), "Reason": e.get("reason"),
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
        # Finalised: no decision controls at all, only the read-only records.
        st.caption("Final decision recorded. This case is read-only.")
        render_audit_details()
        return
    if not runs:
        st.info("The vendor must resume this interrupted application before a reviewer can decide.")
        render_audit_details()
        return
    st.markdown('<div class="vf-admin-divider"></div>', unsafe_allow_html=True)
    with st.container(border=True, key="vf-decision-panel"):
        st.markdown('<h2 class="vf-admin-heading">Record a decision</h2>', unsafe_allow_html=True)
        st.caption("Choose one action, write the reason the vendor will see, and confirm the application ID.")
        choice = st.segmented_control("Resolution", ("Request correction", "Approve", "Reject"),
                                      key=f"admin_choice_{selected_id}_{int(app.get('revision', 0))}")
        actions = {"Approve": "APPROVE", "Request correction": "REQUEST_CORRECTION", "Reject": "REJECT"}
        action = actions.get(choice)
        if action:
            with st.form(f"admin_decision_form_{selected_id}_{int(app.get('revision', 0))}"):
                st.markdown(f"**Decision target:** `{selected_id}`")
                reason = st.text_area("Message to vendor and audit history", max_chars=1000,
                                      placeholder="State the evidence reviewed or correction required.")
                confirm_case = st.checkbox(f"I confirm this decision applies to {selected_id}", value=False)
                reviewed_evidence = (st.checkbox("I reviewed the evidence and understand this is not official verification.", value=False)
                                     if action == "APPROVE" else True)
                action_labels = {"APPROVE": "Approve after review", "REQUEST_CORRECTION": "Send correction request",
                                 "REJECT": "Reject application"}
                with st.container(key="vf-danger" if action == "REJECT" else "vf-decision-submit"):
                    submitted = st.form_submit_button(action_labels[action],
                                                      type="secondary" if action == "REJECT" else "primary",
                                                      width="content")
        else:
            submitted = False

        def save_decision() -> None:
            """Validation errors render inside the decision panel, next to the form."""
            if len(reason.strip()) < 3:
                st.error("A specific written rationale is required before saving any decision.")
                return
            if not confirm_case:
                st.error(f"Confirm the application ID ({selected_id}) before saving.")
                return
            if action == "APPROVE" and not reviewed_evidence:
                st.error("Confirm that you reviewed the available evidence before recording manual approval.")
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
                repo.admin_review(selected_id, action, reason,
                                  expected_revision=int(app.get("revision", 0)),
                                  expected_latest_run_id=app.get("latest_run_id"))
                wording = {"APPROVE": "Approval recorded", "REQUEST_CORRECTION": "Correction request sent",
                           "REJECT": "Rejection recorded"}
                st.session_state["admin_action_notice"] = (
                    f"{wording[action]} for {selected_id}. Select another case to continue."
                )
                st.session_state["admin_clear_selection"] = True
                st.rerun()
            except Exception as exc:
                st.error(safe_error(exc))

        if submitted and action:
            save_decision()
    render_audit_details()


def _track_receipt(application_id: str, tracking_code: str) -> None:
    """Callback avoids mutating a navigation widget after it was rendered."""
    st.session_state.vendor_auth = (application_id, tracking_code)
    st.session_state.vendor_page = "Track / correct application"


def _choose_vendor_page(destination: str) -> None:
    """Button callback runs before the new Streamlit widget tree is rendered."""
    if destination in VENDOR_NAV:
        st.session_state.vendor_page = destination


def render_vendor_header() -> None:
    """Same heading on Welcome, New application and Track / correct."""
    st.markdown('<h1 class="vf-hero">Vendor onboarding made easy.</h1>', unsafe_allow_html=True)
    st.markdown('<p class="vf-lead">Use this portal to submit your business and bank details, upload supporting PDFs, '
                'check your application status and respond to correction requests.</p>',
                unsafe_allow_html=True)


def render_vendor_footer() -> None:
    """The demo limitation, stated once per page instead of in every banner."""
    st.markdown('<p class="vf-demo-note">Demo for GST-registered Indian businesses. Use synthetic details and PDFs only. '
                '"Approved" means your details match your documents; it is not an official GST, PAN or bank verification.</p>',
                unsafe_allow_html=True)


def vendor_welcome() -> None:
    st.subheader("How can we help you today?")
    first, second = st.columns(2)
    with first:
        with st.container(border=True, key="vf-welcome-new"):
            st.markdown('<p class="vf-welcome-title">Start a new application</p>', unsafe_allow_html=True)
            st.caption("Three short steps: business details, bank details, then upload your GST certificate and bank proof.")
            st.button("Start application", type="primary", width="stretch",
                      on_click=_choose_vendor_page, args=("New application",), key="welcome_new")
    with second:
        with st.container(border=True, key="vf-welcome-track"):
            st.markdown('<p class="vf-welcome-title">Track or correct your application</p>', unsafe_allow_html=True)
            st.caption("Use your application ID and private tracking code to check status or answer a correction request.")
            st.button("Track or correct", width="stretch",
                      on_click=_choose_vendor_page, args=("Track / correct application",), key="welcome_track")


ACTION_LABELS = {"APPROVE": "Approved", "REJECT": "Rejected", "REQUEST_CORRECTION": "Correction requested"}


def _return_to_vendor_portal() -> None:
    """Button callback: clear staff access and land on Vendor Welcome.

    Runs before the next script run (on_click), so the first click always takes
    effect and no admin content is drawn after sign-out. Streamlit reruns
    automatically after a callback; calling st.rerun() here would be a no-op.
    """
    st.session_state["admin_authorized"] = False
    for key in ("admin_selected_case_id", "admin_evidence_requested",
                "admin_password_input", "admin_action_notice"):
        st.session_state.pop(key, None)
    st.session_state["vendor_page"] = "Welcome"
    st.query_params["portal"] = "vendor"


def _open_staff_portal() -> None:
    st.query_params["portal"] = "admin"


def render_top_bar(is_admin_portal: bool) -> None:
    """One compact header row: brand + INDIA · DEMO on the left, navigation on the right."""
    with st.container(horizontal=True, vertical_alignment="center", key="vf-topnav"):
        st.markdown('<div class="vf-brand"><span class="vf-mark">V</span> VendorFlow AI '
                    '<span class="vf-tag">INDIA · DEMO</span></div>', unsafe_allow_html=True, width="content")
        with st.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center", gap="small"):
            if is_admin_portal:
                # Available before sign-in, after sign-in and after logout.
                st.button("Vendor portal", key="admin_header_vendor_portal", width="content",
                          on_click=_return_to_vendor_portal)
                if st.session_state.get("admin_authorized"):
                    st.button("Log out", key="admin_logout", width="content",
                              on_click=_return_to_vendor_portal)
            else:
                st.button("Staff sign-in", key="open_staff_portal", width="content",
                          on_click=_open_staff_portal)


# Vendor-first navigation: staff tools are not displayed on the applicant landing page.
# The ?portal=admin URL is a convenience only; admin_console() always authenticates.
is_admin_portal = st.query_params.get("portal") == "admin"
if is_admin_portal:
    st.markdown('<span class="vf-admin-view-marker" aria-hidden="true"></span>', unsafe_allow_html=True)
render_top_bar(is_admin_portal)

if is_admin_portal:
    admin_console()
else:
    render_vendor_header()
    # Initialise the keyed navigation once; callback updates its Session State.
    # Passing default= as well would trigger Streamlit's duplicate-default warning.
    if st.session_state.get("vendor_page") not in VENDOR_NAV:
        st.session_state["vendor_page"] = "Welcome"
    if st.session_state["vendor_page"] == "Welcome":
        # The two large task buttons already provide navigation here.
        # Avoid a second, redundant three-tab control above the same actions.
        page = "Welcome"
    else:
        page = st.segmented_control("Vendor navigation", VENDOR_NAV,
                                    required=True, key="vendor_page",
                                    label_visibility="collapsed")
    if page == "Track / correct application":
        track_application()
    elif page == "New application":
        new_application()
    else:
        vendor_welcome()
    render_vendor_footer()
