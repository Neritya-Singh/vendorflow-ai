"""P1 speed — round-trip budgets, OFFLINE (in-memory Supabase double + label test extractor).

Each Supabase call from a vendor's laptop costs 250-600 ms against staging, so these
tests pin how many calls each vendor step makes. They count calls, not milliseconds;
the live timings are measured separately against staging.
"""
from __future__ import annotations

import pytest

from vendorflow import v2_intake
from tests.test_v2_api import admin, fixture, review
from tests.test_v2_fix import open_fix, team_case
from tests.test_v2_intake import CONTACT, counted, client, creds, stream_events, submit, upload  # noqa: F401


class Calls:
    """Counts database round trips (one per executed query) on the offline double."""

    def __init__(self, provider):
        self.db = provider.repo().client
        self.storage = self.db.storage
        self.count = 0
        original = self.db.table

        def table(name):
            query = original(name)
            execute = query.execute

            def counted_execute():
                self.count += 1
                return execute()
            query.execute = counted_execute
            return query
        self.db.table = table

    def reset(self):
        self.count = 0
        self.downloads = self.storage.downloads


@pytest.fixture
def after_move(monkeypatch):
    """Collects the work Move it leaves for after the response, to run it when the test says."""
    queued = []
    monkeypatch.setattr(v2_intake, "_start_background", queued.append)
    return queued


def test_saving_a_detail_is_two_round_trips(counted):
    client, provider = counted
    c = creds(client)
    _f, gst, bank = fixture("happy")
    upload(client, c, "GST", gst)
    upload(client, c, "BANK", bank)
    calls = Calls(provider)
    calls.reset()
    assert client.put("/api/vendor/draft/values", json={**c, "contact": CONTACT}).status_code == 200
    assert calls.count == 2  # authenticate (the row is reused) + compare-and-swap write


def test_submit_reuses_the_uploaded_bytes_and_records_the_declaration_with_the_run(counted):
    client, provider = counted
    c = creds(client)
    _f, gst, bank = fixture("happy")
    upload(client, c, "GST", gst)
    upload(client, c, "BANK", bank)
    client.put("/api/vendor/draft/values", json={**c, "contact": CONTACT})
    calls = Calls(provider)
    calls.reset()
    result = submit(client, c)  # declaration=True
    assert result["status"] == "APPROVED"
    # authenticate, both document rows at once, the two records lookups, the run insert
    assert calls.count == 5
    assert calls.storage.downloads == calls.downloads  # bytes this server verified on upload
    run = provider.repo().client.rows["runs"][-1]
    assert run["payload_json"]["declaration"] is True and run["payload_json"]["declared_at"]


def test_submit_without_declaration_is_refused_before_any_work(counted):
    client, provider = counted
    c = creds(client)
    _f, gst, bank = fixture("happy")
    upload(client, c, "GST", gst)
    upload(client, c, "BANK", bank)
    client.put("/api/vendor/draft/values", json={**c, "contact": CONTACT})
    response = client.post("/api/vendor/draft/submit", json={**c, "declaration": False})
    assert response.status_code == 400
    assert provider.repo().client.rows["runs"] == []


def swapped_draft(client):
    c = creds(client)
    _f, gst, bank = fixture("happy")
    upload(client, c, "GST", bank)
    upload(client, c, "BANK", gst)
    return c


def test_move_it_is_a_label_swap_then_an_immutable_copy_after_the_response(counted, after_move):
    client, provider = counted
    c = swapped_draft(client)
    provider_calls = len(provider.calls)
    calls = Calls(provider)
    calls.reset()
    files_before = len(calls.storage.files)
    view = stream_events(client.post("/api/vendor/draft/move", json={**c, "slot": "GST"}))[-1]["data"]
    assert [view["files"][s]["status"] for s in ("GST", "BANK")] == ["read", "read"]
    assert len(provider.calls) == provider_calls  # the reading made at upload is reused
    assert calls.count == 2  # authenticate + compare-and-swap write; no storage work while waiting
    assert calls.storage.copies == 0 and calls.storage.downloads == calls.downloads
    # After the response: one server-side copy per file (no re-upload), as NEW rows.
    assert len(after_move) == 1
    after_move.pop()()
    assert calls.storage.copies == 2 and len(calls.storage.files) == files_before + 2
    docs = provider.repo().client.rows["documents"]
    assert sorted((d["doc_type"], d["version"]) for d in docs) == [("BANK", 1), ("BANK", 2), ("GST", 1), ("GST", 2)]
    # Submit uses those copies: no further copy, and both are in the run's manifest.
    client.put("/api/vendor/draft/values", json={**c, "contact": CONTACT})
    assert submit(client, c)["status"] == "APPROVED"
    assert calls.storage.copies == 2
    run = provider.repo().client.rows["runs"][-1]
    assert sorted((d["doc_type"], d["version"]) for d in run["document_manifest"]) == [("BANK", 2), ("GST", 2)]


def test_submit_makes_the_copy_when_the_after_move_work_never_ran(counted, after_move):
    client, provider = counted
    c = swapped_draft(client)
    stream_events(client.post("/api/vendor/draft/move", json={**c, "slot": "GST"}))
    after_move.clear()  # e.g. the server restarted before it ran
    storage = provider.repo().client.storage
    assert storage.copies == 0
    client.put("/api/vendor/draft/values", json={**c, "contact": CONTACT})
    assert submit(client, c)["status"] == "APPROVED"
    assert storage.copies == 2
    run = provider.repo().client.rows["runs"][-1]
    assert sorted(d["doc_type"] for d in run["document_manifest"]) == ["BANK", "GST"]


def test_moving_back_and_forth_needs_no_new_reading(counted, after_move):
    client, provider = counted
    c = creds(client)
    _f, _gst, bank = fixture("happy")
    view = None
    upload(client, c, "GST", bank)
    calls = len(provider.calls)
    view = stream_events(client.post("/api/vendor/draft/move", json={**c, "slot": "GST"}))[-1]["data"]
    assert view["files"]["GST"] is None and view["files"]["BANK"]["status"] == "read"
    view = stream_events(client.post("/api/vendor/draft/move", json={**c, "slot": "BANK"}))[-1]["data"]
    assert view["files"]["BANK"] is None and view["files"]["GST"]["status"] == "wrong_slot"
    view = stream_events(client.post("/api/vendor/draft/move", json={**c, "slot": "GST"}))[-1]["data"]
    assert view["files"]["BANK"]["status"] == "read" and len(provider.calls) == calls
    for work in after_move:
        work()


def test_track_and_open_fix_budgets(counted):
    client, provider = counted
    c = team_case(client)
    csrf = admin(client)
    case = client.get(f"/api/admin/applications/{c['application_id']}").json()
    assert case["suggested_items"] == ["doc:BANK"]
    review(client, csrf, c["application_id"], "REQUEST_CORRECTION", "Upload a bank letter for the company.",
           items=["doc:BANK"])
    calls = Calls(provider)
    calls.reset()
    assert client.post("/api/vendor/track", json=c).status_code == 200
    assert calls.count == 3  # authenticate, then runs and reviews (at the same time)
    calls.reset()
    view = open_fix(client, c).json()
    assert view["items"][0]["id"] == "doc:BANK"
    # authenticate, runs + reviews, document rows; the committed files come from this server's cache
    assert calls.count == 4
    assert calls.storage.downloads == calls.downloads


def test_document_preview_resolves_the_run_document_once(counted):
    client, provider = counted
    c = creds(client)
    _f, gst, bank = fixture("happy")
    upload(client, c, "GST", gst)
    upload(client, c, "BANK", bank)
    client.put("/api/vendor/draft/values", json={**c, "contact": CONTACT})
    submit(client, c)
    admin(client)
    case = client.get(f"/api/admin/applications/{c['application_id']}").json()
    base = f"/api/admin/applications/{c['application_id']}/runs/{case['latest_run_id']}/documents/GST"
    calls = Calls(provider)
    calls.reset()
    assert client.get(base + "/pages").status_code == 200
    first = calls.count
    calls.reset()
    assert client.get(base + "/pages/1").status_code == 200
    assert client.get(base + "/pages").status_code == 200
    assert first == 2 and calls.count == 0  # runs and documents are immutable: resolved once
    assert calls.storage.downloads == calls.downloads


def test_an_upload_after_a_move_replaces_the_moved_file(counted, after_move):
    """A moved file carries the version of the slot it was saved in; it must not block a
    newer upload to its new slot."""
    client, provider = counted
    c = creds(client)
    _f, gst, bank = fixture("happy")
    for _ in range(3):  # BANK reaches v3 in the bank slot's own sequence
        upload(client, c, "BANK", bank)
    upload(client, c, "GST", bank)  # wrong slot (GST v1)
    stream_events(client.post("/api/vendor/draft/move", json={**c, "slot": "GST"}))  # swap: BANK v3 -> GST
    view = stream_events(client.post("/api/vendor/draft/files", data={**c, "slot": "GST"},
                                     files={"file": ("gst.pdf", gst, "application/pdf")}))[-1]["data"]
    assert view["files"]["GST"]["filename"] == "gst.pdf" and view["files"]["GST"]["status"] == "read"
