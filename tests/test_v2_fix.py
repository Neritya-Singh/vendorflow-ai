"""B7 part 1 — fixing a submitted application item by item (upload-first).

OFFLINE: real PDF reader, rules, pipeline and SupabaseRepository code over the
in-memory Supabase double; the label-reading test extractor stands in for Gemini.
These are NOT live Supabase/Gemini tests.
"""
from __future__ import annotations

from vendorflow import v2_policy as v2

from tests.test_v2_api import admin, fixture, review, stream_events
from tests.test_v2_intake import counted, client, ready_draft, submit, upload  # noqa: F401  (pytest fixtures)


def team_case(client, name="ec2_bank_owner"):
    c, _view = ready_draft(client, name)
    result = submit(client, c)
    assert result["owner"] == "TEAM", result["owner"]
    return c


def open_fix(client, c):
    return client.post("/api/vendor/fix", json=c)


def fix_upload(client, c, slot, content, name=None):
    response = client.post("/api/vendor/fix/files", data={**c, "slot": slot},
                           files={"file": (name or f"{slot.lower()}.pdf", content, "application/pdf")})
    events = stream_events(response)
    assert events[-1]["type"] == "result", events[-1]
    return events[-1]["data"]


def fix_submit(client, c):
    response = client.post("/api/vendor/fix/submit", json=c)
    if response.status_code != 200:
        return response
    events = stream_events(response)
    assert events[-1]["type"] == "result", events[-1]
    return events[-1]["data"]


def test_reviewer_asks_for_new_bank_document_vendor_uploads_and_is_approved(counted):
    """The demo path: reviewer requests a new bank letter -> vendor uploads -> re-check -> approved."""
    client, provider = counted
    c = team_case(client)
    app_id = c["application_id"]
    csrf = admin(client)
    case = client.get(f"/api/admin/applications/{app_id}").json()
    assert case["suggested_items"] == ["doc:BANK"]  # holder differs from legal name
    assert {"id": "doc:BANK", "label": "New bank document"} in case["correction_items"]
    saved = review(client, csrf, app_id, "REQUEST_CORRECTION",
                   "Upload a bank letter that shows the company's legal name as account holder.", items=["doc:BANK"])
    assert saved.status_code == 200, saved.text
    assert saved.json()["reviews"][0]["requested"] == ["New bank document"]
    assert "Requested:" not in saved.json()["reviews"][0]["reason"]

    vendor = client.post("/api/vendor/track", json=c).json()
    assert vendor["editable"] and vendor["owner"] == "VENDOR"
    assert "Requested:" not in str(vendor) and "doc:BANK" not in str(vendor)

    view = open_fix(client, c).json()
    assert [i["id"] for i in view["items"]] == ["doc:BANK"]
    assert view["show_slots"] == ["BANK"] and view["shown_fields"] == [] and not view["show_contact"]
    assert view["files"]["BANK"]["on_file"] and view["files"]["BANK"]["status"] == "read"
    assert not view["ready"] and view["blockers"] == ["Upload a new bank document."]
    assert "001234567890" not in str(view)  # the account number stays masked
    assert fix_submit(client, c).status_code == 400  # the requested document is still the old one

    _f, gst, _b = fixture("happy")
    calls = len(provider.calls)
    wrong = fix_upload(client, c, "BANK", gst, "gst.pdf")  # same reading + wrong-slot warning
    assert wrong["files"]["BANK"]["status"] == "wrong_slot" and wrong["files"]["BANK"]["suggested_slot"] == "GST"
    # Read once as the GST certificate it is (so "Move it" would need no new call).
    assert not wrong["ready"] and len(provider.calls) == calls + 1
    calls = len(provider.calls)

    _f, _g, good_bank = fixture("happy")
    view = fix_upload(client, c, "BANK", good_bank, "new_bank_letter.pdf")
    assert view["files"]["BANK"]["status"] == "read" and not view["files"]["BANK"]["on_file"]
    holder = next(f for f in view["fields"] if f["key"] == "bank_holder")
    assert holder["value"] == "Acme Widgets Private Limited" and holder["status"] == "document"
    assert view["ready"], view["blockers"]
    assert len(provider.calls) == calls + 1  # one call for the one new file

    result = fix_submit(client, c)
    assert result["status"] == "APPROVED", result
    assert len(provider.calls) == calls + 1  # re-check reused both readings
    run = client.get(f"/api/admin/applications/{app_id}").json()
    docs = {d["doc_type"]: d["version"] for d in result["documents"]}
    assert docs == {"GST": 1, "BANK": 3}  # GST v1 kept; BANK v2 was the wrong-slot file
    assert run["status"] == "APPROVED"
    # The working copy is gone once the run is committed.
    assert open_fix(client, c).status_code == 409


def test_field_item_shows_only_that_field_with_its_source(client):
    c = team_case(client)
    csrf = admin(client)
    assert review(client, csrf, c["application_id"], "REQUEST_CORRECTION",
                  "Check your IFSC against your cheque.", items=["field:ifsc"]).status_code == 200
    view = open_fix(client, c).json()
    assert [i["id"] for i in view["items"]] == ["field:ifsc"]
    assert view["show_slots"] == [] and view["shown_fields"] == ["ifsc"] and view["ready"]
    view = client.put("/api/vendor/fix/values", json={**c, "changes": {"ifsc": "DEMO0654321"}}).json()
    ifsc = next(f for f in view["fields"] if f["key"] == "ifsc")
    assert ifsc["status"] == "edited" and ifsc["document_value"] == "DEMO0123456"
    bad = client.put("/api/vendor/fix/values", json={**c, "changes": {"ifsc": "NOPE"}}).json()
    assert not bad["ready"] and "IFSC" in bad["blockers"][0]
    client.put("/api/vendor/fix/values", json={**c, "changes": {"ifsc": "DEMO0654321"}})
    result = fix_submit(client, c)
    assert result["owner"] == "TEAM"  # a value that differs from the document goes to the team (R16)


def test_fix_is_only_for_cases_waiting_on_the_vendor(client):
    c = team_case(client)
    assert open_fix(client, c).status_code == 409  # with our team: nothing to fix
    assert client.post("/api/vendor/fix/files", data={**c, "slot": "BANK"},
                       files={"file": ("b.pdf", fixture("happy")[2], "application/pdf")}).status_code == 409
    assert open_fix(client, {**c, "tracking_code": "x" * 30}).status_code == 401
    csrf = admin(client)
    assert review(client, csrf, c["application_id"], "APPROVE", "Ownership confirmed by phone").status_code == 200
    assert open_fix(client, c).status_code == 409  # final


def test_request_items_are_validated_and_never_typed(client):
    c = team_case(client)
    csrf = admin(client)
    app_id = c["application_id"]
    assert review(client, csrf, app_id, "REQUEST_CORRECTION", "Upload it", items=["doc:PASSPORT"]).status_code == 400
    assert review(client, csrf, app_id, "APPROVE", "Fine", items=["doc:BANK"]).status_code == 400
    assert review(client, csrf, app_id, "REQUEST_CORRECTION",
                  "Upload it\n\nRequested: doc:GST").status_code == 400


def test_request_without_items_falls_back_to_the_flagged_items(client):
    c = team_case(client)
    csrf = admin(client)
    assert review(client, csrf, c["application_id"], "REQUEST_CORRECTION", "Please send a new bank letter").status_code == 200
    view = open_fix(client, c).json()
    assert [i["id"] for i in view["items"]] == ["doc:BANK"]


def test_split_review_round_trip():
    stored = v2.join_requested("Upload a new letter.", ["field:ifsc", "doc:BANK", "doc:NOPE"])
    assert stored == "Upload a new letter.\n\nRequested: doc:BANK, field:ifsc"
    assert v2.split_review(stored) == ("Upload a new letter.", None, ["doc:BANK", "field:ifsc"])
    assert v2.split_review("Plain") == ("Plain", None, [])
    assert v2.join_requested("Plain", []) == "Plain"
