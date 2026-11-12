"""Stage 6.5 vendor wording: documents are not approval evidence by themselves."""
from pathlib import Path

from tests.test_backend import case, OfflineTestExtractor
from vendorflow.pipeline import ProcessingPipeline
from vendorflow.pdf_reader import read_pdf, likely_swapped_pdf_roles
from vendorflow.ui_support import selected_reasons, vendor_readable_reasons
from vendorflow.ux_support import vendor_action_heading, vendor_next_step


APP = {"current_status": "PENDING", "decision_source": "AUTOMATED"}


def _check(rule, state, message):
    return {"rule_id": rule, "state": state, "vendor_message": message}


def _run(checks, reasons=None):
    return {"checks_json": checks, "reasons_json": reasons or []}


def test_real_frontend_pdfs_swapped_are_safely_detected():
    vendor, gst, bank = case("frontend_happy")
    assert not likely_swapped_pdf_roles(read_pdf(gst), read_pdf(bank))
    assert likely_swapped_pdf_roles(read_pdf(bank), read_pdf(gst))
    extractor = OfflineTestExtractor()
    result = ProcessingPipeline(extractor, lambda gstin, app_id: []).evaluate(vendor, bank, gst)
    assert result.status.value == "PENDING"
    assert extractor.calls == 0
    checks = [c.model_dump(mode="json") for c in result.checks]
    explanations = vendor_readable_reasons(_run(checks), result.reasons)
    assert len(explanations) == 1
    assert "wrong upload fields" in explanations[0]
    assert "not supported by PDF" not in str(explanations)
    assert vendor_action_heading(APP, _run(checks)) == "Next step: Check your uploaded PDFs"


def test_real_frontend_pdfs_normal_remain_in_normal_slots():
    vendor, gst, bank = case("frontend_happy")
    assert not likely_swapped_pdf_roles(read_pdf(gst), read_pdf(bank))


def test_scanned_bank_message_has_one_cause_and_one_action():
    c = [_check("R02", "FAIL", "Replace unreadable document(s): Bank proof."),
         _check("R09", "UNKNOWN", "Cannot compare bank account until the number and readable bank proof are supplied."),
         _check("R11", "UNKNOWN", "Bank account ownership cannot be compared until the holder and readable proof are supplied."),
         _check("R13", "FAIL", "Missing or unconfirmed document evidence: Bank account holder.")]
    run = _run(c, [x["vendor_message"] for x in c])
    explanations = selected_reasons(APP, [run], [], audience="vendor")
    assert len(explanations) == 1
    assert "couldn't read your bank document" in explanations[0]
    assert "selectable text" in explanations[0]
    assert "cannot be compared" not in str(explanations)
    assert vendor_action_heading(APP, run) == "Next step: Replace your bank document"
    assert "Your application ID will stay the same" in vendor_next_step(APP, run)
    # Staff have the original, complete technical evidence.
    assert selected_reasons(APP, [run], [], audience="admin") == run["reasons_json"]


def test_document_problem_does_not_hide_independent_pan_error():
    checks = [_check("R02", "FAIL", "Upload: Bank proof."),
              _check("R03", "FAIL", "Check the 10-character PAN format."),
              _check("R09", "UNKNOWN", "Bank account cannot be compared yet.")]
    messages = vendor_readable_reasons(_run(checks), [c["vendor_message"] for c in checks])
    assert len(messages) == 2
    assert "bank document is missing" in messages[0]
    assert "PAN" in messages[1]


def test_ungrounded_generic_evidence_is_rewritten_without_claiming_swapped():
    run = _run([_check("R13", "FAIL", "Missing or unconfirmed document evidence: not supported by PDF: GSTIN.")],
               ["Missing or unconfirmed document evidence: not supported by PDF: GSTIN."])
    messages = selected_reasons(APP, [run], [], audience="vendor")
    assert len(messages) == 1
    assert "couldn't confirm" in messages[0]
    assert "wrong upload" not in messages[0]
    assert "not supported by PDF" not in str(messages)
    assert "not supported by PDF" in str(selected_reasons(APP, [run], [], audience="admin"))


def test_manual_decision_message_and_identity_confidentiality_untouched():
    run = _run([_check("R12", "FAIL", "Potential duplicate application VF-PRIVATE")],
               ["Additional identity screening is required by our review team."])
    assert "VF-PRIVATE" not in str(selected_reasons(APP, [run], [], audience="vendor"))
    assert vendor_action_heading(APP, run) == "Your application is under review"
    manual = {**APP, "decision_source": "MANUAL"}
    reason = selected_reasons(manual, [run], [{"action": "REQUEST_CORRECTION", "reason": "Update the bank proof."}], audience="vendor")
    assert reason == ["Reviewer requested correction: Update the bank proof."]


def test_vendor_page_no_longer_exposes_internal_waiting_on_label():
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text()
    vendor = source[source.index("def new_application() -> None:"):source.index("def admin_console() -> None:")]
    assert "Waiting on: " not in vendor
    assert "vendor_action_heading(record, latest_run, latest_review)" in vendor
    assert "vendor_readable_reasons(receipt_run, receipt.result.reasons)" in vendor


def test_document_warning_does_not_hide_independent_verified_mismatch():
    checks = [_check("R02", "FAIL", "Replace unreadable document(s): Bank proof."),
              _check("R08", "FAIL", "Your GST certificate name differs from your submission."),
              _check("R09", "UNKNOWN", "Cannot compare bank account yet."),
              _check("R13", "FAIL", "Missing or unconfirmed document evidence.")]
    messages = vendor_readable_reasons(_run(checks), [c["vendor_message"] for c in checks])
    assert len(messages) == 2
    assert "couldn't read your bank document" in messages[0]
    assert "GST certificate name differs" in messages[1]
