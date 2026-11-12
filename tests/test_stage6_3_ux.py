"""Stage 6.3: deterministic presentation logic, no real credentials or API calls."""
from datetime import datetime, timezone
from pathlib import Path

from vendorflow.ux_support import (
    VENDOR_NAV, active_review_request, admin_queue_rows, age_label,
    committed_pdf_types, next_action_owner, primary_review_issue,
    valid_contact_email, vendor_next_step,
)
from vendorflow.ui_support import vendor_visible_checks, comparison_rows


NOW = datetime(2026, 11, 11, 9, 0, tzinfo=timezone.utc)
APP = {"id": "VF-DEMO-ALPHA", "payload_json": {"legal_name": "Synthetic Foods"},
       "current_status": "PENDING", "created_at": "2026-11-11T07:00:00+00:00",
       "latest_run_id": "RUN-ALPHA", "revision": 3}


def mk_run(*rule_states, error=False):
    return {"id": "RUN-ALPHA", "created_at": "2026-11-11T08:00:00Z",
            "checks_json": [{"rule_id": rule, "state": state, "label": label}
                            for rule, state, label in rule_states],
            "extraction_error": error}


def test_landing_offers_both_vendor_journeys_without_staff_branch():
    assert VENDOR_NAV == ("Welcome", "New application", "Track / correct application")


def test_email_validation_catches_typo_without_changing_backend():
    assert valid_contact_email(" vendor@example.com ")
    assert not valid_contact_email("vendor@")
    assert not valid_contact_email("vendor example.com")
    assert not valid_contact_email("")


def test_queue_age_is_grounded_in_created_at():
    assert age_label(APP["created_at"], now=NOW) == "2h"
    assert age_label("unknown", now=NOW) == "Unknown"
    assert age_label("2026-11-12T09:00:00Z", now=NOW) == "0m"
    assert age_label("2026-11-08T09:00:00Z", now=NOW) == "3d"


def test_active_request_is_cancelled_by_newer_committed_run():
    run = mk_run(("R09", "FAIL", "Bank account"))
    old = {"action": "REQUEST_CORRECTION", "created_at": "2026-11-11T07:59:00Z"}
    current = {"action": "REQUEST_CORRECTION", "created_at": "2026-11-11T08:01:00Z"}
    assert not active_review_request(old, run)
    assert active_review_request(current, run)
    assert not active_review_request({"action": "REJECT"}, run)


def test_reviewer_correction_owner_is_vendor():
    r = mk_run(("R12", "FAIL", "Duplicate GSTIN"))
    review = {"action": "REQUEST_CORRECTION", "created_at": "2026-11-11T08:01:00Z"}
    assert next_action_owner(APP, r, review) == "Vendor"
    assert "reviewer requested" in vendor_next_step(APP, r, review).lower()


def test_empty_saved_run_is_recoverable_vendor_action():
    assert next_action_owner(APP, None) == "Vendor"
    assert "same application" in vendor_next_step(APP, None)
    assert primary_review_issue(None) == "Submission incomplete"


def test_business_or_document_failure_goes_to_vendor():
    r = mk_run(("R09", "FAIL", "Bank account mismatch"))
    assert next_action_owner(APP, r) == "Vendor"
    assert primary_review_issue(r) == "Bank account mismatch"


def test_extraction_only_error_is_technical_retry_not_invalid_vendor():
    r = mk_run(("R08", "UNKNOWN", "GST evidence"), ("R14", "FAIL", "Extraction"), error=True)
    assert next_action_owner(APP, r) == "Technical retry"
    assert "interrupted" in vendor_next_step(APP, r)
    assert next_action_owner(APP, mk_run(("R01", "FAIL", "Required fields"),
                                              ("R14", "FAIL", "Extraction"), error=True)) == "Vendor"


def test_identity_screening_does_not_leak_prior_application_to_vendor():
    r = mk_run(("R12", "FAIL", "Approved GSTIN duplicate"))
    r["checks_json"][0]["admin_detail"] = "Possible matching approved application: VF-PRIVATE"
    assert next_action_owner(APP, r) == "Reviewer"
    public_text = vendor_next_step(APP, r)
    assert "VF-PRIVATE" not in public_text
    assert "duplicate" not in public_text.lower()
    assert "VF-PRIVATE" not in repr(vendor_visible_checks(r["checks_json"]))
    assert primary_review_issue(r) == "Identity screening"


def test_queue_enriched_from_exact_latest_run_only():
    r = mk_run(("R07", "FAIL", "IFSC structure"))
    stale = mk_run(("R09", "FAIL", "OLD PROBLEM"))
    stale["id"] = "RUN-OLD"
    rows = admin_queue_rows([APP], {"RUN-OLD": stale, "RUN-ALPHA": r}, {}, now=NOW)
    assert len(rows) == 1
    assert rows[0]["Age"] == "2h"
    assert rows[0]["Primary issue"] == "IFSC structure"
    assert rows[0]["Action owner"] == "Vendor"
    assert rows[0]["Application ID"] == APP["id"]
    assert "OLD PROBLEM" not in repr(rows)


def test_manual_final_decisions_not_assigned_to_vendor():
    for status in ("APPROVED", "REJECTED"):
        a = {**APP, "current_status": status}
        assert next_action_owner(a, mk_run(("R09", "FAIL", "Bank"))) == "Complete"
        assert "final decision" in vendor_next_step(a, None)


def test_staff_evidence_types_only_from_saved_manifest():
    run = {"document_manifest": [
        {"doc_type": "GST", "id": "id1", "version": 1, "storage_path": "gst", "file_sha256": "a"*64},
        {"doc_type": "BANK", "id": "id2", "version": 3, "storage_path": "bank", "file_sha256": "b"*64},
        {"doc_type": "BANK", "id": "id2", "version": 3, "storage_path": "bank", "file_sha256": "b"*64},
        {"doc_type": "OTHER", "id": "id3", "version": 1, "storage_path": "bad", "file_sha256": "x"*64},
    ]}
    assert committed_pdf_types(run) == ["GST", "BANK"]
    assert committed_pdf_types({"document_manifest": []}) == []
    assert committed_pdf_types({"document_manifest": [{"doc_type": "GST"}]}) == []


def test_bank_values_remain_masked_in_vendor_comparison():
    rows = comparison_rows({"account_number": "000123456789"},
                           {"bank": {"account_number": "000987656789"}})
    assert "000123456789" not in repr(rows)
    assert "000987656789" not in repr(rows)


def test_ui_submission_uses_single_receipt_rerun_and_authoritative_correction_rerun():
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text()
    assert "st.session_state.receipt = receipt\n                st.rerun()" in source
    assert "st.session_state.vendor_action_notice" in source
    assert "refresh the page to see" not in source.lower()
    assert "on_click=_track_receipt" in source
    assert "on_click=_choose_vendor_page" in source


def test_staff_only_document_access_is_run_version_bound():
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text()
    assert "repo.load_run_document(selected_id, selected_run[\"id\"], doc_type)" in source
    assert "admin_evidence_requested" in source
    assert "repo.load_latest_document" not in source
    assert "st.download_button" in source


def test_no_fourth_status_added_to_vendor_portal():
    source = (Path(__file__).resolve().parents[1] / "vendorflow/ux_support.py").read_text()
    assert "NEEDS_REVIEW" not in source
    assert "PENDING" in source


def test_incomplete_application_cannot_show_staff_resolution_actions():
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text()
    assert "if not runs:\n        st.info(\"The vendor must resume this interrupted application" in source
