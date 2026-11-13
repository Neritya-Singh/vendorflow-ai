"""B5 upload-first intake tests — OFFLINE: real PDF reader, rules, pipeline and
SupabaseRepository code over the in-memory Supabase double; the label-reading test
extractor stands in for Gemini. These are NOT live Supabase/Gemini tests.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.offline import OfflineLabelExtractor
from backend.services import ServiceProvider
from vendorflow import v2_intake
from vendorflow import v2_policy as v2
from vendorflow.gemini_extractor import ExtractionFailure
from vendorflow.pdf_reader import PDFInput, read_pdf

from tests.test_v2_api import admin, blank_pdf, fixture, settings, stream_events

ALL_STAGES = ["U1", "U2", "U3"]


class CountingProvider(ServiceProvider):
    calls: list[tuple[bool, bool]]

    def extractor(self):
        provider = self

        class Counting(OfflineLabelExtractor):
            def extract(self, gst_text, bank_text):
                provider.calls.append((bool(gst_text.strip()), bool(bank_text.strip())))
                return super().extract(gst_text, bank_text)
        return Counting()


class DownProvider(ServiceProvider):
    def extractor(self):
        class Down:
            last_diagnostic = None

            def extract(self, gst_text, bank_text):
                raise ExtractionFailure("synthetic outage", category="PROVIDER_UNAVAILABLE", attempts=3)
        return Down()


@pytest.fixture
def counted():
    s = settings()
    provider = CountingProvider(s)
    provider.calls = []
    return TestClient(create_app(s, provider)), provider


@pytest.fixture
def client(counted):
    return counted[0]


def creds(client) -> dict:
    return client.post("/api/vendor/intake").json()


def upload(client, c, slot, content, name=None):
    response = client.post("/api/vendor/draft/files", data={**c, "slot": slot},
                           files={"file": (name or f"{slot.lower()}.pdf", content, "application/pdf")})
    events = stream_events(response)
    assert events[-1]["type"] == "result", events[-1]
    return events


def draft_of(events) -> dict:
    return events[-1]["data"]


def field(view, key) -> dict:
    return next(f for f in view["fields"] if f["key"] == key)


CONTACT = {"name": "Demo Contact", "email": "demo@example.com", "phone": "+91 98765 43210"}


def ready_draft(client, name="happy", **values):
    c = creds(client)
    _fields, gst, bank = fixture(name)
    upload(client, c, "GST", gst)
    upload(client, c, "BANK", bank)
    view = client.put("/api/vendor/draft/values", json={**c, "contact": CONTACT, "changes": values}).json()
    return c, view


def submit(client, c, declaration=True):
    response = client.post("/api/vendor/draft/submit", json={**c, "declaration": declaration})
    if response.status_code != 200:
        return response
    events = stream_events(response)
    assert events[-1]["type"] == "result", events[-1]
    return events[-1]["data"]


# ---------------------------------------------------------------- happy path + cache

def test_upload_first_prefills_values_with_source_and_reuses_cache_on_submit(counted):
    client, provider = counted
    c = creds(client)
    _fields, gst, bank = fixture("happy")
    events = upload(client, c, "GST", gst)
    stages = [e for e in events if e["type"] == "stage"]
    assert [e["stage_id"] for e in stages if e["event"] == "COMPLETED"] == ALL_STAGES
    assert {e["label"] for e in stages} == {"Received", "Identified the document type", "Read the details"}
    assert all(e["note"] == "" for e in stages)
    view = draft_of(upload(client, c, "BANK", bank))
    assert provider.calls == [(True, False), (False, True)]  # one provider call per file

    assert view["files"]["GST"]["status"] == "read"
    assert view["files"]["GST"]["message"].startswith("Read: legal name, GSTIN, state")
    assert field(view, "legal_name") | {} == {**field(view, "legal_name"), "value": "Acme Widgets Private Limited",
                                              "status": "document", "document": "GST"}
    assert field(view, "gstin")["value"] == "09ABCDE1234F1ZY"
    assert view["pan"] == {"value": "ABCDE1234F", "source": "GSTIN"}
    # The account number is masked to its last 4 digits even on the vendor's own draft.
    assert field(view, "account_number")["value"] == "•••• 7890"
    assert "001234567890" not in str(view)
    assert view["documents_ready"] and not view["details_ready"]  # contact still missing
    assert "cache" not in str(view) and "document_id" not in str(view)

    view = client.put("/api/vendor/draft/values", json={**c, "contact": CONTACT}).json()
    assert view["details_ready"] and view["blockers"] == []
    result = submit(client, c)
    assert result["status"] == "APPROVED"
    assert provider.calls == [(True, False), (False, True)]  # submit used the cache: no new call

    # Contact phone and declaration are stored with the run.
    csrf = admin(client)
    assert csrf
    case = client.get(f"/api/admin/applications/{c['application_id']}").json()
    assert case["contact"]["phone"] == "+91 98765 43210" and case["declared"] is True
    assert {p["status"] for p in case["provenance"]} == {"document"}


def test_declaration_is_required_to_submit(client):
    c, _view = ready_draft(client)
    response = submit(client, c, declaration=False)
    assert response.status_code == 400 and "Confirm" in response.json()["detail"]
    assert client.post("/api/vendor/draft", json=c).status_code == 200  # still a draft


def test_draft_resumes_with_tracking_code_and_is_closed_after_submit(client):
    c, _ = ready_draft(client)
    resumed = client.post("/api/vendor/draft", json=c).json()
    assert resumed["contact"] == CONTACT and resumed["files"]["GST"]["status"] == "read"
    tracked = client.post("/api/vendor/track", json=c).json()
    assert tracked["owner"] == "DRAFT" and tracked["needs_resume"] is True
    assert "draft" not in tracked["submitted"]
    submit(client, c)
    assert client.post("/api/vendor/draft", json=c).status_code == 409
    assert client.put("/api/vendor/draft/values", json={**c, "changes": {"ifsc": "DEMO0123457"}}).status_code == 409
    again = submit(client, c)  # lost response: the saved result is returned, no second run
    assert again["status"] == "APPROVED"


def test_draft_endpoints_need_the_tracking_code(client):
    c, _ = ready_draft(client)
    wrong = {**c, "tracking_code": "x" * 32}
    assert client.post("/api/vendor/draft", json=wrong).status_code == 401
    assert client.put("/api/vendor/draft/values", json={**wrong, "changes": {}}).status_code == 401
    assert client.post("/api/vendor/draft/submit", json={**wrong, "declaration": True}).status_code == 401
    _f, gst, _b = fixture("happy")
    response = client.post("/api/vendor/draft/files", data={**wrong, "slot": "GST"},
                           files={"file": ("g.pdf", gst, "application/pdf")})
    assert response.status_code == 401
    unknown = creds(client)
    assert client.post("/api/vendor/draft", json=unknown).status_code == 401  # no draft created by a read


def test_non_pdf_upload_rejected_before_a_draft_exists(client):
    c = creds(client)
    response = client.post("/api/vendor/draft/files", data={**c, "slot": "GST"},
                           files={"file": ("g.txt", b"hello", "text/plain")})
    assert response.status_code == 400
    assert client.post("/api/vendor/draft", json=c).status_code == 401


def test_drafts_never_reach_the_queue_or_metrics(client):
    ready_draft(client)
    admin(client)
    overview = client.get("/api/admin/overview").json()
    assert overview["queue"] == []


# ---------------------------------------------------------------- wrong slot

def test_wrong_slot_warns_without_reading_and_move_it_fixes(counted):
    client, provider = counted
    c = creds(client)
    _fields, _gst, bank = fixture("happy")
    view = draft_of(upload(client, c, "GST", bank))
    assert view["files"]["GST"]["status"] == "wrong_slot"
    assert view["files"]["GST"]["suggested_slot"] == "BANK"
    assert view["files"]["GST"]["message"] == ("This looks like a bank document. "
                                               "Did you mean to put it in the bank slot?")
    assert provider.calls == []  # no provider call for a file in the wrong slot
    assert not view["documents_ready"]
    response = client.post("/api/vendor/draft/move", json={**c, "slot": "GST"})
    view = stream_events(response)[-1]["data"]
    assert view["files"]["GST"] is None and view["files"]["BANK"]["status"] == "read"
    assert field(view, "ifsc")["value"] == "DEMO0123456"
    assert provider.calls == [(False, True)]


def test_swapped_files_both_warn_and_one_move_swaps_both(counted):
    client, provider = counted
    c = creds(client)
    _fields, gst, bank = fixture("happy")
    upload(client, c, "GST", bank)
    view = draft_of(upload(client, c, "BANK", gst))
    assert [view["files"][s]["status"] for s in ("GST", "BANK")] == ["wrong_slot", "wrong_slot"]
    view = stream_events(client.post("/api/vendor/draft/move", json={**c, "slot": "BANK"}))[-1]["data"]
    assert [view["files"][s]["status"] for s in ("GST", "BANK")] == ["read", "read"]
    assert sorted(provider.calls) == [(False, True), (True, False)]
    client.put("/api/vendor/draft/values", json={**c, "contact": CONTACT})
    assert submit(client, c)["status"] == "APPROVED"


def test_classifier_on_fixtures_and_blank_pages():
    for name in ("happy", "ec2_bank_owner", "frontend_happy", "frontend_ec2_review"):
        _f, gst, bank = fixture(name)
        assert v2_intake.classify_document(read_pdf(PDFInput("g.pdf", gst))) == "GST"
        assert v2_intake.classify_document(read_pdf(PDFInput("b.pdf", bank))) == "BANK"
    assert v2_intake.classify_document(read_pdf(PDFInput("x.pdf", blank_pdf()))) is None


def test_unreadable_file_asks_for_a_clearer_copy(client):
    c = creds(client)
    view = draft_of(upload(client, c, "GST", blank_pdf()))
    assert view["files"]["GST"]["status"] == "unreadable"
    assert "Upload a clearer copy" in view["files"]["GST"]["message"]  # blank scan: OCR finds no text
    assert field(view, "gstin")["status"] == "unread"


# ---------------------------------------------------------------- vendor values

def test_edited_value_is_kept_flagged_and_goes_to_the_team_with_both_values(client):
    c, view = ready_draft(client, account_number="009999000011")
    row = field(view, "account_number")
    assert row["status"] == "edited" and row["value"] == "•••• 0011" and row["document_value"] == "•••• 7890"
    assert view["flagged"] == ["account_number"]
    result = submit(client, c)
    assert result["status"] == "PENDING" and result["owner"] == "TEAM" and result["todo"] == []
    assert "R16" not in str(result) and "009999000011" not in str(result.get("todo"))

    admin(client)
    case = client.get(f"/api/admin/applications/{c['application_id']}").json()
    assert case["owner"] == "TEAM"
    assert {"field": "account_number", "label": "Account number", "status": "edited"} in case["provenance"]
    r16 = next(x for x in case["checks"] if x["rule_id"] == "R16")
    assert r16["state"] == "FAIL" and r16["label"] == "Vendor changed a value from the documents"
    assert any(f["rule_id"] == "R16" for f in case["flags"])
    compared = next(r for r in case["comparison"] if r["Kind"] == "flag")
    assert compared["Assessment"] == "Different"  # both values shown side by side


def test_reset_returns_a_field_to_the_document_value(client):
    c, view = ready_draft(client, ifsc="DEMO0999999")
    assert field(view, "ifsc")["status"] == "edited"
    view = client.put("/api/vendor/draft/values", json={**c, "reset": ["ifsc"]}).json()
    assert field(view, "ifsc") | {} == {**field(view, "ifsc"), "status": "document", "value": "DEMO0123456"}
    # Typing the document's own value back is not an edit.
    view = client.put("/api/vendor/draft/values", json={**c, "changes": {"legal_name": "acme widgets pvt ltd"}}).json()
    assert field(view, "legal_name")["status"] == "document"


def test_value_not_on_document_typed_by_vendor_goes_to_the_team(client):
    c = creds(client)
    _fields, gst, bank = fixture("ec4_missing_bank_holder")
    upload(client, c, "GST", gst)
    view = draft_of(upload(client, c, "BANK", bank))
    assert field(view, "bank_holder")["status"] == "missing"
    assert "Add your account holder." in view["blockers"]
    view = client.put("/api/vendor/draft/values", json={
        **c, "contact": CONTACT, "changes": {"bank_holder": "Acme Widgets Private Limited"}}).json()
    assert field(view, "bank_holder")["status"] == "vendor" and view["details_ready"]
    result = submit(client, c)
    assert result["owner"] == "TEAM" and result["todo"] == []

    admin(client)
    case = client.get(f"/api/admin/applications/{c['application_id']}").json()
    assert {"field": "bank_holder", "label": "Account holder", "status": "vendor"} in case["provenance"]
    r16 = next(x for x in case["checks"] if x["rule_id"] == "R16")
    assert r16["state"] == "FAIL" and r16["label"] == "Vendor entered a value not on the documents"


def test_unknown_field_and_oversized_change_rejected(client):
    c, _ = ready_draft(client)
    assert client.put("/api/vendor/draft/values", json={**c, "changes": {"pan": "X"}}).status_code == 400


# ---------------------------------------------------------------- GSTIN check digit

def test_gstin_check_digit():
    assert v2.gstin_check_digit_ok("09ABCDE1234F1ZY") is True
    assert v2.gstin_check_digit_ok("09ABCDE1234F1Z5") is False
    assert v2.gstin_check_digit_ok("27ABCDE1234F1Z0") is True
    assert v2.gstin_check_digit_ok("not a gstin") is None


def test_all_fixture_gstins_have_valid_check_digits():
    import json
    from pathlib import Path
    for path in (Path(__file__).resolve().parents[1] / "fixtures").glob("*/submission.json"):
        assert v2.gstin_check_digit_ok(json.loads(path.read_text())["gstin"]) is True, path


def test_mistyped_gstin_is_shown_on_the_field_and_sent_back_to_the_vendor(client):
    c, view = ready_draft(client, gstin="09ABCDE1234F1Z5")
    assert field(view, "gstin")["error"] == "Check your GSTIN. Its last character doesn't match the rest of the number."
    result = submit(client, c)
    assert result["owner"] == "VENDOR"
    assert any("last character" in t["text"] for t in result["todo"])


# ---------------------------------------------------------------- limits and outages

def test_upload_count_is_bounded_per_draft(client, monkeypatch):
    monkeypatch.setattr(v2_intake, "MAX_DRAFT_DOCUMENTS", 2)
    c = creds(client)
    _fields, gst, bank = fixture("happy")
    upload(client, c, "GST", gst)
    upload(client, c, "BANK", bank)
    response = client.post("/api/vendor/draft/files", data={**c, "slot": "GST"},
                           files={"file": ("g.pdf", gst, "application/pdf")})
    last = stream_events(response)[-1]
    assert last["type"] == "error" and last["status"] == 429


def test_reading_outage_at_upload_is_honest_and_fails_closed():
    s = settings()
    client = TestClient(create_app(s, DownProvider(s)))
    c = creds(client)
    _fields, gst, _bank = fixture("happy")
    view = draft_of(upload(client, c, "GST", gst))
    assert view["files"]["GST"]["status"] == "unavailable"
    assert "temporary problem on our side" in view["files"]["GST"]["message"]
    assert field(view, "gstin")["status"] == "unread"
    # An outage never traps the vendor: the documents step is not blocked by it.
    _f2, _g2, bank = fixture("happy")
    view = draft_of(upload(client, c, "BANK", bank))
    assert view["documents_ready"]
    fields, _g, _b = fixture("happy")
    values = {k: fields[k] for k in ("legal_name", "gstin", "business_state", "bank_holder", "account_number", "ifsc")}
    view = client.put("/api/vendor/draft/values", json={**c, "contact": CONTACT, "changes": values}).json()
    assert view["details_ready"]
    result = submit(client, c)
    assert result["owner"] == "TEAM" and result["retry_available"] is True


def test_cached_extractor_only_calls_provider_for_misses():
    calls = []

    class Inner(OfflineLabelExtractor):
        def extract(self, gst_text, bank_text):
            calls.append((gst_text, bank_text))
            return super().extract(gst_text, bank_text)
    gst_text = "GSTIN: 09ABCDE1234F1ZY\nLegal name: Acme"
    cached = {"legal_name": "Acme", "gstin": "09ABCDE1234F1ZY", "state": None, "address": None}
    extractor = v2_intake.CachedExtractor(Inner(), {("GST", v2_intake.text_sha(gst_text)): cached})
    out = extractor.extract(gst_text, "IFSC: DEMO0123456")
    assert calls == [("", "IFSC: DEMO0123456")] and out.gst.gstin == "09ABCDE1234F1ZY"
    assert out.bank.ifsc == "DEMO0123456"
    calls.clear()
    extractor.extract(gst_text, "")
    assert calls == []
