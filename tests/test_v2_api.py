"""v2 FastAPI adapter tests — OFFLINE: real PDF reader, rules, pipeline and
SupabaseRepository code; in-memory Supabase double and a label-reading test
extractor in place of Gemini. These are NOT live Supabase/Gemini tests.
"""
from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from backend.config import Settings
from backend.main import create_app
from backend.services import ServiceProvider
from vendorflow.gemini_extractor import ExtractionFailure

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
ADMIN_PASSWORD = "offline-test-admin-password"


def settings(**overrides) -> Settings:
    base = dict(offline_mode=True, offline_extractor="labels", admin_password=ADMIN_PASSWORD,
                session_key=b"s" * 32, cookie_secure=False, frontend_dist=Path("/nonexistent"))
    base.update(overrides)
    return Settings(**base)


class OutageProvider(ServiceProvider):
    def extractor(self):
        class Down:
            last_diagnostic = None

            def extract(self, gst_text, bank_text):
                raise ExtractionFailure("synthetic outage", category="PROVIDER_UNAVAILABLE", attempts=3)
        return Down()


@pytest.fixture
def client():
    return TestClient(create_app(settings()))


def fixture(name: str) -> tuple[dict, bytes, bytes]:
    folder = FIXTURES / name
    return (json.loads((folder / "submission.json").read_text()),
            (folder / "gst_certificate.pdf").read_bytes(), (folder / "bank_confirmation.pdf").read_bytes())


def blank_pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page()
    return doc.tobytes()


def stream_events(response) -> list[dict]:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/x-ndjson")
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def submit(client, fields: dict, gst: bytes | None, bank: bytes | None, *, creds=None):
    creds = creds or client.post("/api/vendor/intake").json()
    files = {}
    if gst is not None:
        files["gst_pdf"] = ("gst_certificate.pdf", gst, "application/pdf")
    if bank is not None:
        files["bank_pdf"] = ("bank_confirmation.pdf", bank, "application/pdf")
    response = client.post("/api/vendor/applications", data={**fields, **creds}, files=files or None)
    return creds, response


def result_of(events: list[dict]) -> dict:
    final = events[-1]
    assert final["type"] == "result", final
    return final["data"]


def admin(client) -> str:
    response = client.post("/api/admin/session", json={"password": ADMIN_PASSWORD})
    assert response.status_code == 200
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=strict" in response.headers["set-cookie"].lower()
    return response.json()["csrf_token"]


# ---------------------------------------------------------------- happy path

def test_happy_path_streams_real_stages_and_approves(client):
    fields, gst, bank = fixture("happy")
    creds, response = submit(client, fields, gst, bank)
    events = stream_events(response)
    assert events[0]["type"] == "accepted"
    stages = [e for e in events if e["type"] == "stage"]
    assert {e["stage_id"] for e in stages} == {f"S{i}" for i in range(1, 10)}
    assert all(e["timestamp"] for e in stages)
    assert [e["event"] for e in stages if e["stage_id"] == "S9"] == ["STARTED", "COMPLETED"]
    result = result_of(events)
    assert result["status"] == "APPROVED" and result["persisted"] is True
    assert result["application_id"] == creds["application_id"]
    assert all(s["state"] == "COMPLETED" for s in result["stages"])
    assert creds["tracking_code"] not in response.text  # never echoed back in the stream

    tracked = client.post("/api/vendor/track", json=creds).json()
    assert tracked["status"] == "APPROVED" and tracked["editable"] is False
    assert tracked["timeline"][0]["documents"] == [{"doc_type": "GST", "version": 1},
                                                   {"doc_type": "BANK", "version": 1}]


def test_repeat_submit_with_same_credentials_is_idempotent(client):
    fields, gst, bank = fixture("happy")
    creds, first = submit(client, fields, gst, bank)
    first_run = result_of(stream_events(first))["latest_run_id"]
    _, second = submit(client, fields, gst, bank, creds=creds)
    assert result_of(stream_events(second))["latest_run_id"] == first_run


# ---------------------------------------------------------------- exceptions

def test_bank_holder_mismatch_correction_loop_to_approval(client):
    fields, gst, bank = fixture("ec2_bank_owner")
    creds, response = submit(client, fields, gst, bank)
    pending = result_of(stream_events(response))
    assert pending["status"] == "PENDING"
    assert all("R1" not in r and "R0" not in r for r in pending["reasons"])

    csrf = admin(client)
    queue = client.get("/api/admin/overview").json()["queue"]
    assert queue[0]["application_id"] == creds["application_id"]
    case = client.get(f"/api/admin/applications/{creds['application_id']}").json()
    assert case["can_review"] and case["issues"]["failed"]
    assert "tracking_token_hash" not in json.dumps(case)
    review = client.post(f"/api/admin/applications/{creds['application_id']}/review", headers={"x-csrf-token": csrf},
                         json={"action": "REQUEST_CORRECTION", "reason": "Upload a bank letter in the company's legal name.",
                               "expected_revision": case["revision"], "expected_latest_run_id": case["latest_run_id"]})
    assert review.status_code == 200, review.text
    assert review.json()["status"] == "PENDING"

    tracked = client.post("/api/vendor/track", json=creds).json()
    assert tracked["reviewer_note"]["message"].startswith("Upload a bank letter")
    assert tracked["editable"] is True

    happy_fields, _, happy_bank = fixture("happy")
    resubmitted = client.post("/api/vendor/resubmit", data={
        **happy_fields, **creds, "expected_revision": tracked["revision"],
        "expected_latest_run_id": tracked["latest_run_id"]},
        files={"bank_pdf": ("bank.pdf", happy_bank, "application/pdf")})
    final = result_of(stream_events(resubmitted))
    assert final["status"] == "APPROVED"
    runs = [t for t in final["timeline"] if t["kind"] == "run"]
    assert len(runs) == 2
    assert {"doc_type": "BANK", "version": 2} in runs[0]["documents"]
    assert {"doc_type": "GST", "version": 1} in runs[0]["documents"]  # old GST evidence reused


def test_swapped_pdfs_route_to_pending_with_swap_guidance(client):
    fields, gst, bank = fixture("happy")
    _, response = submit(client, fields, bank, gst)
    result = result_of(stream_events(response))
    assert result["status"] == "PENDING" and result["owner"] == "VENDOR"
    assert result["status_label"] == "Action needed from you" and result["editable"] is True
    assert "files look swapped" in result["todo"][0]["text"]
    s3 = next(s for s in result["stages"] if s["stage_id"] == "S3")
    assert s3["state"] == "SKIPPED"


def test_unreadable_bank_pdf_routes_to_pending(client):
    fields, gst, _ = fixture("happy")
    _, response = submit(client, fields, gst, blank_pdf())
    result = result_of(stream_events(response))
    assert result["status"] == "PENDING" and result["owner"] == "VENDOR"
    assert result["todo"][0]["text"].startswith("We couldn't read your bank document")


def test_gemini_outage_is_truthful_retry_not_unreadable_documents():
    client = TestClient(create_app(settings(), OutageProvider(settings())))
    fields, gst, bank = fixture("happy")
    creds, response = submit(client, fields, gst, bank)
    events = stream_events(response)
    s3 = [e for e in events if e["type"] == "stage" and e["stage_id"] == "S3"]
    assert s3[-1]["event"] == "FAILED"
    result = result_of(events)
    assert result["status"] == "PENDING" and result["owner"] == "TEAM"
    assert result["retry_available"] is True and result["editable"] is False and result["todo"] == []
    assert result["reasons"][0].startswith("We couldn't read your documents just now because of a temporary problem")
    assert result["heading"] == "With our team — no action needed"
    # An unchanged retry is allowed; edits are not, because the case is with the team.
    tracked = client.post("/api/vendor/track", json=creds).json()
    base = {**creds, "expected_revision": tracked["revision"], "expected_latest_run_id": tracked["latest_run_id"]}
    edited = client.post("/api/vendor/resubmit", data={**fields, **base, "ifsc": "HDFC0000001"})
    assert edited.status_code == 409
    retry = client.post("/api/vendor/resubmit", data={**fields, **base})
    assert result_of(stream_events(retry))["owner"] == "TEAM"


def test_duplicate_gstin_is_staff_only(client):
    fields, gst, bank = fixture("happy")
    _, first = submit(client, fields, gst, bank)
    assert result_of(stream_events(first))["status"] == "APPROVED"
    creds, second = submit(client, fields, gst, bank)
    result = result_of(stream_events(second))
    assert result["status"] == "PENDING"
    blob = json.dumps(result).lower()
    assert "duplicate" not in blob and "vf-" not in blob.replace(creds["application_id"].lower(), "")
    admin(client)
    case = client.get(f"/api/admin/applications/{creds['application_id']}").json()
    assert any(c["rule_id"] == "R12" and c["state"] == "FAIL" for c in case["checks"])


# ---------------------------------------------------------------- security

def test_wrong_tracking_code_rejected_and_throttled(client):
    fields, gst, bank = fixture("happy")
    creds, response = submit(client, fields, gst, bank)
    stream_events(response)
    wrong = {"application_id": creds["application_id"], "tracking_code": "x" * 32}
    statuses = [client.post("/api/vendor/track", json=wrong).status_code for _ in range(11)]
    assert statuses[:10] == [401] * 10 and statuses[10] == 429
    assert client.post("/api/vendor/track", json=wrong).json()["detail"].startswith("Too many")


def test_submit_cannot_hijack_existing_application(client):
    fields, gst, bank = fixture("happy")
    creds, response = submit(client, fields, gst, bank)
    stream_events(response)
    _, hijack = submit(client, fields, gst, bank,
                       creds={"application_id": creds["application_id"], "tracking_code": "y" * 32})
    assert hijack.status_code == 401


def test_admin_endpoints_require_session_and_csrf(client):
    fields, gst, bank = fixture("ec2_bank_owner")
    creds, response = submit(client, fields, gst, bank)
    result = result_of(stream_events(response))
    app_id = creds["application_id"]
    for path in ("/api/admin/overview", f"/api/admin/applications/{app_id}",
                 f"/api/admin/applications/{app_id}/reveal",
                 f"/api/admin/applications/{app_id}/runs/{result['latest_run_id']}/documents/GST"):
        assert client.get(path).status_code == 401, path
    body = {"action": "APPROVE", "reason": "Looks fine", "expected_revision": 1,
            "expected_latest_run_id": result["latest_run_id"]}
    assert client.post(f"/api/admin/applications/{app_id}/review", json=body).status_code == 401
    assert client.post("/api/admin/session", json={"password": "wrong"}).status_code == 401
    admin(client)
    assert client.post(f"/api/admin/applications/{app_id}/review", json=body).status_code == 403
    assert client.post(f"/api/admin/applications/{app_id}/review", json=body,
                       headers={"x-csrf-token": "forged"}).status_code == 403


def test_forged_cookie_rejected(client):
    client.cookies.set("vf_admin", "eyJleHAiOjk5OTk5OTk5OTksImNzcmYiOiJ4In0.bad", path="/api")
    assert client.get("/api/admin/overview").status_code == 401


def test_admin_login_lockout(client):
    codes = [client.post("/api/admin/session", json={"password": "nope"}).status_code for _ in range(6)]
    assert codes[:4] == [401] * 4 and codes[4] == 429 and codes[5] == 429
    assert client.post("/api/admin/session", json={"password": ADMIN_PASSWORD}).status_code == 429


def test_admin_pdf_download_matches_committed_version(client):
    fields, gst, bank = fixture("ec2_bank_owner")
    creds, response = submit(client, fields, gst, bank)
    run_id = result_of(stream_events(response))["latest_run_id"]
    admin(client)
    pdf = client.get(f"/api/admin/applications/{creds['application_id']}/runs/{run_id}/documents/BANK")
    assert pdf.status_code == 200 and pdf.content == bank
    assert pdf.headers["content-type"] == "application/pdf"
    assert "no-store" in pdf.headers["cache-control"]


def test_stale_review_and_terminal_application(client):
    fields, gst, bank = fixture("ec2_bank_owner")
    creds, response = submit(client, fields, gst, bank)
    result = result_of(stream_events(response))
    csrf = admin(client)
    url = f"/api/admin/applications/{creds['application_id']}/review"
    stale = client.post(url, headers={"x-csrf-token": csrf}, json={
        "action": "APPROVE", "reason": "ok after review", "expected_revision": 0,
        "expected_latest_run_id": result["latest_run_id"]})
    assert stale.status_code == 409
    rejected = client.post(url, headers={"x-csrf-token": csrf}, json={
        "action": "REJECT", "reason": "Bank account belongs to an individual.", "expected_revision": 1,
        "expected_latest_run_id": result["latest_run_id"]})
    assert rejected.status_code == 200 and rejected.json()["status"] == "REJECTED"

    tracked = client.post("/api/vendor/track", json=creds).json()
    assert tracked["status"] == "REJECTED" and tracked["editable"] is False
    assert tracked["reviewer_note"]["message"] == "Bank account belongs to an individual."
    again = client.post("/api/vendor/resubmit", data={
        **fields, **creds, "expected_revision": tracked["revision"],
        "expected_latest_run_id": tracked["latest_run_id"]})
    assert again.status_code == 409
    second = client.post(url, headers={"x-csrf-token": csrf}, json={
        "action": "APPROVE", "reason": "override", "expected_revision": tracked["revision"],
        "expected_latest_run_id": result["latest_run_id"]})
    assert second.status_code == 409


def test_upload_validation(client):
    fields, gst, bank = fixture("happy")
    creds = client.post("/api/vendor/intake").json()
    not_pdf = client.post("/api/vendor/applications", data={**fields, **creds},
                          files={"gst_pdf": ("gst.txt", b"hello", "text/plain")})
    assert not_pdf.status_code == 400
    fake = client.post("/api/vendor/applications", data={**fields, **creds},
                       files={"gst_pdf": ("gst.pdf", b"not really a pdf", "application/pdf")})
    assert fake.status_code == 400 and "does not appear to be a PDF" in fake.json()["detail"]
    big = client.post("/api/vendor/applications", data={**fields, **creds},
                      files={"gst_pdf": ("gst.pdf", b"%PDF-" + b"0" * (5 * 1024 * 1024), "application/pdf")})
    assert big.status_code == 413
    missing = client.post("/api/vendor/applications", data={**creds, "legal_name": "X"})
    assert missing.status_code == 400


def test_missing_documents_still_create_pending_application(client):
    fields, _, _ = fixture("happy")
    _, response = submit(client, fields, None, None)
    result = result_of(stream_events(response))
    assert result["status"] == "PENDING" and result["owner"] == "VENDOR"
    texts = [t["text"] for t in result["todo"]]
    assert "Upload your GST certificate." in texts and "Upload your bank document." in texts


def test_offline_mode_refuses_configured_supabase(monkeypatch):
    from backend.config import ConfigurationError, load_settings
    monkeypatch.setenv("VENDORFLOW_OFFLINE_MODE", "1")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    with pytest.raises(ConfigurationError):
        load_settings(env_file=False)


def test_unknown_api_route_and_health(client):
    assert client.get("/api/nope").status_code == 404
    health = client.get("/api/health").json()
    assert health["mode"] == "offline" and "key" not in json.dumps(health).lower()


# ---------------------------------------------------------------- B1 ownership

BANNED_VENDOR_WORDS = ("fraud", "duplicate", "suspicious", "failed", "identity screening", "gemini")


def vendor_safe(view: dict) -> None:
    blob = json.dumps(view).lower()
    for word in BANNED_VENDOR_WORDS:
        assert word not in blob, word
    assert '"checks"' not in blob and '"rule_id"' not in blob
    assert not any(s["note"] for s in view["stages"])


def test_with_our_team_case_is_not_editable_by_vendor(client):
    fields, gst, bank = fixture("ec2_bank_owner")
    creds, response = submit(client, fields, gst, bank)
    events = stream_events(response)
    assert all(e["note"] == "" for e in events if e["type"] == "stage")  # no internal notes streamed
    result = result_of(events)
    assert result["owner"] == "TEAM" and result["status_label"] == "With our team"
    assert result["editable"] is False and result["todo"] == []
    assert result["reasons"][0].startswith("Thanks, your application is with our team")
    vendor_safe(result)
    tracked = client.post("/api/vendor/track", json=creds).json()
    vendor_safe(tracked)
    blocked = client.post("/api/vendor/resubmit", data={
        **fields, **creds, "expected_revision": tracked["revision"],
        "expected_latest_run_id": tracked["latest_run_id"]})
    assert blocked.status_code == 409 and "with our team" in blocked.json()["detail"]


def test_queue_tabs_risk_and_reason(client):
    fields, gst, bank = fixture("ec2_bank_owner")
    team_creds, response = submit(client, fields, gst, bank)
    stream_events(response)
    happy, hgst, hbank = fixture("happy")
    vendor_creds, response = submit(client, happy, hbank, hgst)  # swapped -> waiting on vendor
    stream_events(response)
    other, ogst, obank = fixture("frontend_happy")
    approved_creds, response = submit(client, other, ogst, obank)
    stream_events(response)
    admin(client)
    overview = client.get("/api/admin/overview").json()
    rows = {r["application_id"]: r for r in overview["queue"]}
    team = rows[team_creds["application_id"]]
    assert team["tab"] == "NEEDS_REVIEW" and team["risk"] == "MEDIUM"
    assert team["reason"] == "Bank account holder differs from legal name"
    vendor = rows[vendor_creds["application_id"]]
    assert vendor["tab"] == "WAITING_ON_VENDOR" and vendor["risk"] is None
    assert vendor["reason"] == "Waiting for vendor: files look swapped"
    assert rows[approved_creds["application_id"]]["tab"] == "APPROVED"
    assert overview["queue"][0]["tab"] == "NEEDS_REVIEW"
    m = overview["metrics"]
    assert (m["needs_review"], m["waiting_on_vendor"], m["approved"], m["total"]) == (1, 1, 1, 3)
    case = client.get(f"/api/admin/applications/{team_creds['application_id']}").json()
    assert case["owner"] == "TEAM" and case["owner_label"] == "Needs review"
    assert case["flags"][0]["rule_id"] == "R11"


def test_draft_rows_are_excluded_from_queue_and_metrics():
    provider = ServiceProvider(settings())
    client = TestClient(create_app(settings(), provider))
    fields, gst, bank = fixture("happy")
    creds, response = submit(client, fields, gst, bank)
    stream_events(response)
    # An application row with zero runs (interrupted intake / future invite).
    provider.repo().client.table("applications").insert({
        "id": "VF-0000000000AA", "payload_json": {"legal_name": "SAMPLE Draft Co", "gstin": fields["gstin"]},
        "current_status": "PENDING", "decision_source": "AUTOMATED", "tracking_token_hash": "x"}).execute()
    admin(client)
    overview = client.get("/api/admin/overview").json()
    assert "VF-0000000000AA" not in {r["application_id"] for r in overview["queue"]}
    assert overview["metrics"]["total"] == 1


# ---------------------------------------------------------------- B2 records screening

def approve_first(client, name: str = "happy") -> dict:
    fields, gst, bank = fixture(name)
    creds, response = submit(client, fields, gst, bank)
    assert result_of(stream_events(response))["status"] == "APPROVED"
    return creds


def test_same_gstin_as_approved_vendor_with_new_bank_is_high_risk_and_linked(client):
    first = approve_first(client)
    fields, gst, bank = fixture("ec3_duplicate_changed_bank")
    creds, response = submit(client, fields, gst, bank)
    result = result_of(stream_events(response))
    assert result["status"] == "PENDING" and result["owner"] == "TEAM"
    assert result["reasons"] == ["Our team is completing an additional check. No action is needed from you."]
    vendor_safe(result)
    assert first["application_id"] not in json.dumps(result)
    admin(client)
    case = client.get(f"/api/admin/applications/{creds['application_id']}").json()
    assert case["risk"] == "HIGH"
    assert case["primary_issue"] == "Same GSTIN as an approved vendor, different bank account"
    linked = case["linked_records"]
    assert [r["application_id"] for r in linked] == [first["application_id"]] and linked[0]["status"] == "APPROVED"
    rows = {r["field"]: r for r in linked[0]["comparison"]}
    assert rows["GSTIN"]["same"] is True and rows["Account no."]["same"] is False
    assert fields["account_number"] not in json.dumps(linked)  # masked
    queue = client.get("/api/admin/overview").json()["queue"]
    assert queue[0]["application_id"] == creds["application_id"] and queue[0]["risk"] == "HIGH"


def test_same_gstin_as_pending_or_rejected_application_goes_to_team(client):
    fields, gst, bank = fixture("ec2_bank_owner")
    pending, response = submit(client, fields, gst, bank)
    first_run = result_of(stream_events(response))
    happy, hgst, hbank = fixture("happy")
    creds, response = submit(client, happy, hgst, hbank)
    assert result_of(stream_events(response))["owner"] == "TEAM"
    csrf = admin(client)
    case = client.get(f"/api/admin/applications/{creds['application_id']}").json()
    assert case["primary_issue"] == "Same GSTIN as an open application"
    assert case["linked_records"][0]["application_id"] == pending["application_id"]
    client.post(f"/api/admin/applications/{pending['application_id']}/review", headers={"x-csrf-token": csrf},
                json={"action": "REJECT", "reason": "Bank account belongs to an individual.",
                      "expected_revision": 1, "expected_latest_run_id": first_run["latest_run_id"]})
    again, response = submit(client, happy, hgst, hbank)
    stream_events(response)
    case = client.get(f"/api/admin/applications/{again['application_id']}").json()
    # The rejected application outranks the still-open one in the reason.
    assert case["primary_issue"] == "Same GSTIN as a rejected application"
    assert case["risk"] == "HIGH"


def test_bank_account_reused_under_different_gstin(client):
    approve_first(client)
    happy = fixture("happy")[0]
    fields, gst, _ = fixture("frontend_happy")
    _, _, happy_bank = fixture("happy")
    fields = {**fields, "account_number": happy["account_number"], "ifsc": happy["ifsc"],
              "bank_holder": fields["legal_name"]}
    creds, response = submit(client, fields, gst, happy_bank)
    result = result_of(stream_events(response))
    assert result["owner"] == "TEAM"
    vendor_safe(result)
    admin(client)
    case = client.get(f"/api/admin/applications/{creds['application_id']}").json()
    assert case["primary_issue"] == "Bank account used under a different GSTIN" and case["risk"] == "HIGH"
    assert case["linked_records"][0]["match"] == ["Same bank account, different GSTIN"]
    r15 = next(c for c in case["checks"] if c["rule_id"] == "R15")
    assert r15["state"] == "FAIL" and "under a different GSTIN" in r15["evidence"]


def test_drafts_and_self_never_count_as_duplicates():
    provider = ServiceProvider(settings())
    client = TestClient(create_app(settings(), provider))
    fields, gst, bank = fixture("happy")
    provider.repo().client.table("applications").insert({
        "id": "VF-0000000000AB", "payload_json": dict(fields), "current_status": "PENDING",
        "decision_source": "AUTOMATED", "tracking_token_hash": "x"}).execute()
    creds, response = submit(client, fields, gst, bank)
    result = result_of(stream_events(response))
    assert result["status"] == "APPROVED"  # the zero-run draft with the same GSTIN is ignored
    # Self-exclusion on resubmission is covered by test_bank_holder_mismatch_correction_loop_to_approval.


def test_legal_suffix_variant_of_bank_holder_is_approved(client):
    fields, gst, bank = fixture("happy")
    assert fields["legal_name"] == "Acme Widgets Private Limited"
    _, response = submit(client, {**fields, "bank_holder": "ACME WIDGETS PVT. LTD."}, gst, bank)
    assert result_of(stream_events(response))["status"] == "APPROVED"


# ---------------------------------------------------------------- B3 messages + decisions

def review(client, csrf, app_id, action, reason, **extra):
    case = client.get(f"/api/admin/applications/{app_id}").json()
    return client.post(f"/api/admin/applications/{app_id}/review", headers={"x-csrf-token": csrf}, json={
        "action": action, "reason": reason, "expected_revision": case["revision"],
        "expected_latest_run_id": case["latest_run_id"], **extra})


def test_message_log_one_entry_per_outcome_and_action_honest_delivery(client):
    fields, gst, bank = fixture("ec2_bank_owner")
    creds, response = submit(client, fields, gst, bank)
    first = result_of(stream_events(response))
    assert [m["title"] for m in first["messages"]] == ["With our team"]
    assert first["messages"][0]["text"].startswith("Thanks, your application is with our team")
    csrf = admin(client)
    case = client.get(f"/api/admin/applications/{creds['application_id']}").json()
    assert case["correction_draft"] == ("Upload a bank letter or cancelled cheque that shows "
                                        "Acme Widgets Private Limited as the account holder.")
    assert review(client, csrf, creds["application_id"], "REQUEST_CORRECTION", case["correction_draft"]).status_code == 200
    tracked = client.post("/api/vendor/track", json=creds).json()
    titles = [m["title"] for m in tracked["messages"]]
    assert titles == ["Our team asked for a change", "With our team"]
    assert tracked["messages"][0]["text"].startswith("Our team needs one change: Upload a bank letter")
    for m in tracked["messages"]:
        assert m["delivery"] == "Message added to the vendor's application page (no email sent)"
        assert "email sent" not in m["text"].lower()
    vendor_safe(tracked)
    admin_case = client.get(f"/api/admin/applications/{creds['application_id']}").json()
    assert [m["title"] for m in admin_case["messages"]] == titles


def test_vendor_items_produce_waiting_on_you_message(client):
    fields, gst, bank = fixture("happy")
    _, response = submit(client, fields, bank, gst)
    result = result_of(stream_events(response))
    assert result["messages"][0]["title"] == "Action needed from you"
    assert "Your files look swapped" in result["messages"][0]["text"]


def test_approving_bank_reuse_case_requires_server_side_confirmation(client):
    approve_first(client)
    happy = fixture("happy")[0]
    fields, gst, _ = fixture("frontend_happy")
    _, _, happy_bank = fixture("happy")
    fields = {**fields, "account_number": happy["account_number"], "ifsc": happy["ifsc"],
              "bank_holder": fields["legal_name"]}
    creds, response = submit(client, fields, gst, happy_bank)
    stream_events(response)
    csrf = admin(client)
    app_id = creds["application_id"]
    case = client.get(f"/api/admin/applications/{app_id}").json()
    assert case["requires_confirmation"] is True
    missing = review(client, csrf, app_id, "APPROVE", "Checked with the bank.")
    assert missing.status_code == 400 and "bank-change confirmation" in missing.json()["detail"]
    wrong = review(client, csrf, app_id, "APPROVE", "Checked with the bank.", confirmation="yes")
    assert wrong.status_code == 400
    typed = review(client, csrf, app_id, "APPROVE", "Confirmation: trust me")
    assert typed.status_code == 400
    ok = review(client, csrf, app_id, "APPROVE", "Shared group treasury account; confirmed by phone.",
                confirmation="Bank change confirmed by call-back to the contact on the existing record")
    assert ok.status_code == 200, ok.text
    saved = ok.json()["reviews"][0]
    assert saved["reason"] == "Shared group treasury account; confirmed by phone."
    assert saved["confirmation"] == "Bank change confirmed by call-back to the contact on the existing record"
    tracked = client.post("/api/vendor/track", json=creds).json()
    assert tracked["status"] == "APPROVED" and tracked["reviewer_note"] is None  # approval reason is internal
    assert "treasury" not in json.dumps(tracked) and "call-back" not in json.dumps(tracked)


def test_plain_case_approval_needs_no_confirmation_and_reject_reason_reaches_vendor(client):
    fields, gst, bank = fixture("ec2_bank_owner")
    creds, response = submit(client, fields, gst, bank)
    stream_events(response)
    csrf = admin(client)
    assert client.get(f"/api/admin/applications/{creds['application_id']}").json()["requires_confirmation"] is False
    assert review(client, csrf, creds["application_id"], "REJECT", "Bank account not owned by the business").status_code == 200
    tracked = client.post("/api/vendor/track", json=creds).json()
    assert tracked["messages"][0]["text"] == ("We couldn't approve your application: Bank account not owned by the "
                                              "business. Questions: contact Zamp AI's finance team.")
