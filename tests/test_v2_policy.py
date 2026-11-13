"""Unit tests for the v2 ownership and wording policy (V2_02 §6). Pure functions."""
from __future__ import annotations

from vendorflow import v2_policy as v2

ALL = ("R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09", "R10", "R11", "R12", "R13", "R14")
PENDING = {"id": "VF-000000000001", "current_status": "PENDING"}


def run(fails: dict[str, str] | None = None, unknown: tuple[str, ...] = (), **extra) -> dict:
    fails = fails or {}
    checks = []
    for rule in ALL:
        state = "FAIL" if rule in fails else "UNKNOWN" if rule in unknown else "PASS"
        checks.append({"rule_id": rule, "state": state, "label": rule, "vendor_message": fails.get(rule, "")})
    return {"id": "RUN-000000000001", "checks_json": checks, "created_at": "2026-11-13T10:00:00+00:00", **extra}


def test_terminal_and_draft_states():
    assert v2.case_owner({"current_status": "APPROVED"}, run()) == v2.COMPLETE
    assert v2.case_owner({"current_status": "REJECTED"}, run()) == v2.COMPLETE
    assert v2.case_owner(PENDING, None) == v2.DRAFT
    assert v2.queue_tab(PENDING, v2.DRAFT) is None


def test_vendor_fixable_problems_go_to_vendor():
    for fails in ({"R01": "Complete: PAN."}, {"R02": "Upload: Bank proof."}, {"R04": "x"}, {"R07": "x"},
                  {"R13": "Missing or unconfirmed document evidence: Bank IFSC."}):
        assert v2.case_owner(PENDING, run(fails)) == v2.VENDOR, fails


def test_vendor_items_are_plain_language():
    items = v2.vendor_items(run({"R01": "Complete: PAN, IFSC.", "R02": "Replace unreadable document(s): Bank proof."}))
    texts = [i["text"] for i in items]
    assert texts == ["Add the missing details: PAN, IFSC.", "We couldn't read your bank document. Upload a clearer copy."]
    swapped = v2.vendor_items(run({"R02": "The GST certificate and bank proof appear to be uploaded in the opposite slots.",
                                   "R14": "x"}))
    assert swapped[0]["text"].startswith("Your files look swapped")
    assert not any("R0" in t or "R1" in t for t in texts)


def test_reviewer_flags_go_to_team_with_risk():
    for fails, risk in (({"R11": "x"}, v2.MEDIUM), ({"R08": "x"}, v2.MEDIUM), ({"R09": "x"}, v2.MEDIUM),
                        ({"R12": "x"}, v2.HIGH)):
        r = run(fails)
        assert v2.case_owner(PENDING, r) == v2.TEAM
        assert v2.staff_summary(PENDING, r, None)["risk"] == risk
    assert v2.vendor_team_message(run({"R12": "x"})) == v2.ADDITIONAL_CHECK
    assert v2.vendor_team_message(run({"R11": "x"})) == v2.TEAM_MESSAGE


def test_vendor_part_first_when_both_kinds_present():
    r = run({"R07": "x", "R11": "x", "R12": "x"})
    assert v2.case_owner(PENDING, r) == v2.VENDOR
    assert [i["key"] for i in v2.vendor_items(r)] == ["R07"]


def test_outage_goes_to_team_unless_submitted_values_are_invalid():
    outage = run({"R13": "Missing or unconfirmed document evidence: GST legal name.", "R14": "x"},
                 unknown=("R08", "R09", "R10", "R11"), extraction_error=True)
    assert v2.case_owner(PENDING, outage) == v2.TEAM
    assert v2.staff_summary(PENDING, outage, None) == {
        "owner": v2.TEAM, "reason": "Document reading unavailable, re-run needed", "risk": v2.LOW}
    assert v2.vendor_team_message(outage) == v2.OUTAGE_MESSAGE
    with_bad_ifsc = run({"R07": "x", "R13": "x", "R14": "x"}, extraction_error=True)
    assert v2.case_owner(PENDING, with_bad_ifsc) == v2.VENDOR


def test_active_correction_request_puts_case_with_vendor():
    r = run({"R11": "x"})
    review = {"action": "REQUEST_CORRECTION", "created_at": "2026-11-13T11:00:00+00:00"}
    assert v2.case_owner(PENDING, r, review) == v2.VENDOR
    assert v2.staff_summary(PENDING, r, review)["reason"] == "Correction requested from vendor"
    older = {"action": "REQUEST_CORRECTION", "created_at": "2026-11-13T09:00:00+00:00"}
    assert v2.case_owner(PENDING, r, older) == v2.TEAM  # superseded by the newer run


# ---------------------------------------------------------------- B2 screening + names
from vendorflow.models import VendorSubmission  # noqa: E402
from vendorflow.rules import norm_legal_name, norm_name  # noqa: E402

V = VendorSubmission(legal_name="Acme Widgets Private Limited", gstin="09ABCDE1234F1Z5", pan="ABCDE1234F",
                     account_number="001234567890", ifsc="DEMO0123456", bank_holder="Acme Widgets Private Limited",
                     contact_email="a@example.com", contact_name="A", business_state="UTTAR PRADESH")


class Registry:
    def __init__(self, by_gstin=(), by_bank=(), boom=False):
        self.by_gstin, self.by_bank, self.boom = list(by_gstin), list(by_bank), boom

    def records_by_gstin(self, gstin, application_id):
        if self.boom:
            raise RuntimeError("down")
        return self.by_gstin

    def records_by_bank(self, account, ifsc, application_id):
        if self.boom:
            raise RuntimeError("down")
        return self.by_bank


def rec(case_id, status, gstin="09ABCDE1234F1Z5", account="001234567890", ifsc="DEMO0123456"):
    return {"id": case_id, "status": status, "gstin": gstin, "legal_name": "x", "account_number": account, "ifsc": ifsc}


def test_gstin_check_across_statuses():
    assert v2.gstin_check(V, "VF-AAAAAAAAAAAA", Registry()).state.value == "PASS"
    c = v2.gstin_check(V, "VF-AAAAAAAAAAAA", Registry([rec("VF-000000000002", "PENDING"),
                                                       rec("VF-000000000001", "APPROVED", account="999")]))
    assert c.state.value == "FAIL" and c.label == "Same GSTIN as an approved vendor, different bank account"
    assert v2.CASE_ID.findall(c.admin_detail) == ["VF-000000000001", "VF-000000000001", "VF-000000000002"]
    assert c.vendor_message == v2.ADDITIONAL_CHECK and "VF-" not in c.vendor_message
    assert v2.gstin_check(V, "x", Registry([rec("VF-000000000003", "REJECTED")])).label == "Same GSTIN as a rejected application"
    assert v2.gstin_check(V, "x", Registry(boom=True)).state.value == "UNKNOWN"
    assert v2.gstin_check(V, "x", None).state.value == "UNKNOWN"


def test_bank_reuse_only_counts_other_gstins():
    same_gstin = rec("VF-000000000004", "APPROVED")
    assert v2.bank_reuse_check(V, "x", Registry(by_bank=[same_gstin])).state.value == "PASS"
    other = rec("VF-000000000005", "REJECTED", gstin="27ZZZZZ9999Z1Z5")
    c = v2.bank_reuse_check(V, "x", Registry(by_bank=[same_gstin, other]))
    assert c.state.value == "FAIL" and "VF-000000000005" in c.admin_detail and "VF-000000000004" not in c.admin_detail
    assert v2.bank_reuse_check(V.model_copy(update={"ifsc": "bad"}), "x", Registry()).state.value == "UNKNOWN"
    flags = v2.team_flags({"checks_json": [{"rule_id": "R15", "state": "FAIL", "label": c.label, "admin_detail": c.admin_detail}]})
    assert flags == [{"rule_id": "R15", "risk": v2.HIGH, "reason": "Bank account used under a different GSTIN"}]


def test_legal_suffix_normaliser():
    assert norm_legal_name("Acme Widgets Pvt. Ltd.") == norm_legal_name("ACME WIDGETS PRIVATE LIMITED")
    assert norm_legal_name("M/s Sample & Sons Co.") == norm_legal_name("Sample and Sons Company")
    assert norm_legal_name("Acme Widgets") != norm_legal_name("Acme Widgets Private Limited")  # suffix still matters
    assert norm_legal_name("Ravi Example") != norm_legal_name("Acme Widgets Private Limited")
    # v1.1 strict comparison is untouched for callers that do not opt in.
    assert norm_name("Acme Widgets Pvt Ltd") != norm_name("Acme Widgets Private Limited")


# ---------------------------------------------------------------- B3 decisions

def test_correction_draft_uses_flagged_items_without_naming_other_cases():
    assert v2.correction_draft(run({"R11": "x"}), "SAMPLE Traders Pvt Ltd") == (
        "Upload a bank letter or cancelled cheque that shows SAMPLE Traders Pvt Ltd as the account holder.")
    draft = v2.correction_draft(run({"R12": "x", "R15": "x"}))
    assert draft == "Upload a recent letter from your bank confirming that this account belongs to your business."
    assert "VF-" not in draft and "duplicate" not in draft.lower()
    assert v2.correction_draft(run({"R07": "x"})).startswith("Check your IFSC")


def test_confirmation_requirement_and_storage_format():
    assert v2.requires_confirmation(run({"R12": "x"})) and v2.requires_confirmation(run(unknown=("R12",)))
    assert not v2.requires_confirmation(run({"R11": "x"}))
    stored = "Called the contact.\n\nConfirmation: " + v2.BANK_CHANGE_CONFIRMATION
    assert v2.split_confirmation(stored) == ("Called the contact.", v2.BANK_CHANGE_CONFIRMATION)
    assert v2.split_confirmation("plain") == ("plain", None)
