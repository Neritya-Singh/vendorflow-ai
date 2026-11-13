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
