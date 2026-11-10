"""Offline adapter tests using an IN-MEMORY fake Supabase API, NOT a live database.
The genuine Postgres trigger, RLS, storage privacy and version history still require
verification on the user's real Supabase project before Stage 3.3 is complete.
"""
from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path
import pytest

from vendorflow.models import Status, VendorSubmission
from vendorflow.pdf_reader import PDFInput
from vendorflow.persistence import (
    SupabaseRepository, PersistentVendorService, UnauthorizedTracking,
    TerminalApplication, PersistenceError,
)
from tests.test_backend import OfflineTestExtractor, case
from vendorflow.rules import norm_id


class FakeQuery:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.predicates = []
        self.to_insert = None
        self.order_col = None
        self.desc = False
        self.num = None

    def select(self, *_): return self

    def eq(self, col, value):
        self.predicates.append(lambda r: (r.get(col) == value))
        return self

    def neq(self, col, value):
        self.predicates.append(lambda r: (r.get(col) != value))
        return self

    def order(self, col, desc=False):
        self.order_col, self.desc = col, desc
        return self

    def limit(self, count):
        self.num = count
        return self

    def insert(self, row):
        self.to_insert = deepcopy(row)
        return self

    def execute(self):
        if self.to_insert is None:
            matches = [deepcopy(r) for r in self.db.rows[self.name] if all(p(r) for p in self.predicates)]
            if self.order_col:
                matches.sort(key=lambda row: row[self.order_col], reverse=self.desc)
            if self.num is not None:
                matches = matches[:self.num]
            return SimpleNamespace(data=matches)
        if self.db.fail_table == self.name:
            raise RuntimeError("Mock database failure")
        row = self.to_insert
        if self.name == "applications":
            row["gstin_normalized"] = norm_id(row["payload_json"].get("gstin"))
            row.setdefault("latest_run_id", None)
        if self.name == "documents":
            assert not any(r["application_id"] == row["application_id"] and
                           r["doc_type"] == row["doc_type"] and r["version"] == row["version"]
                           for r in self.db.rows["documents"])
        if self.name == "runs":
            app = next(r for r in self.db.rows["applications"] if r["id"] == row["application_id"])
            assert app["current_status"] == "PENDING", "Cannot run after final decision"
            assert row["status"] != "REJECTED", "No automated rejection"
            app["payload_json"] = deepcopy(row["payload_json"])
            app["gstin_normalized"] = norm_id(row["payload_json"].get("gstin"))
            if row["status"] == "APPROVED" and any(
                other["id"] != app["id"] and other["current_status"] == "APPROVED"
                and other["gstin_normalized"] == app["gstin_normalized"]
                for other in self.db.rows["applications"]):
                raise RuntimeError("approved GSTIN uniqueness conflict")
            app["current_status"] = row["status"]
            app["decision_source"] = "AUTOMATED"
            app["latest_run_id"] = row["id"]
        if self.name == "review_actions":
            app = next(r for r in self.db.rows["applications"] if r["id"] == row["application_id"])
            assert app["current_status"] == "PENDING"
            status = {"APPROVE":"APPROVED","REJECT":"REJECTED","REQUEST_CORRECTION":"PENDING"}[row["action"]]
            if status == "APPROVED" and any(
                other["id"] != app["id"] and other["current_status"] == "APPROVED"
                and other["gstin_normalized"] == app["gstin_normalized"]
                for other in self.db.rows["applications"]):
                raise RuntimeError("approved GSTIN uniqueness conflict")
            app["current_status"] = status
            app["decision_source"] = "MANUAL"
        self.db.rows[self.name].append(row)
        return SimpleNamespace(data=[deepcopy(row)])


class FakeBucket:
    def __init__(self, storage): self.storage = storage

    def upload(self, path, file, file_options):
        assert file_options["upsert"] == "false"
        assert file_options["content-type"] == "application/pdf"
        self.storage.files[path] = file
        return SimpleNamespace(path=path)

    def download(self, path): return self.storage.files[path]


class FakeStorage:
    def __init__(self): self.files = {}

    def from_(self, bucket):
        assert bucket == "vendor-documents"
        return FakeBucket(self)


class FakeSupabase:
    def __init__(self):
        self.rows = {name: [] for name in ("applications", "documents", "runs", "review_actions")}
        self.storage = FakeStorage()
        self.fail_table = None

    def table(self, name): return FakeQuery(self, name)


@pytest.fixture
def prepared():
    client = FakeSupabase()
    repo = SupabaseRepository(client)
    service = PersistentVendorService(repo, OfflineTestExtractor())
    return client, repo, service


def test_application_persisted_and_tracking_secret_hashed(prepared):
    client, repo, service = prepared
    vendor, gst, bank = case("happy")
    receipt = service.submit(vendor, gst, bank)
    assert receipt.result.persisted is True
    assert receipt.result.status == Status.APPROVED
    assert client.rows["applications"][0]["current_status"] == "APPROVED"
    assert client.rows["applications"][0]["latest_run_id"] == receipt.result.run_id
    assert receipt.tracking_code not in str(client.rows)
    assert len(client.rows["documents"]) == 2
    assert len(client.rows["runs"]) == 1
    assert client.rows["runs"][0]["stages_json"][-1]["event"] == "COMPLETED"
    assert "S9" == client.rows["runs"][0]["stages_json"][-1]["stage_id"]
    record, history = service.track(receipt.application_id, receipt.tracking_code)
    assert record["current_status"] == "APPROVED"
    assert "tracking_token_hash" not in record
    assert history[0]["id"] == receipt.result.run_id
    with pytest.raises(UnauthorizedTracking):
        service.track(receipt.application_id, "wrong-guess")


def test_unapproved_can_resubmit_and_new_run_keeps_old(prepared):
    client, repo, service = prepared
    vendor, gst, bank = case("ec1_pan_gstin")
    receipt = service.submit(vendor, gst, bank)
    assert receipt.result.status == Status.PENDING
    first_run = deepcopy(client.rows["runs"][0])
    fixed_vendor, _, _ = case("happy")
    rerun = service.resubmit(receipt.application_id, receipt.tracking_code, fixed_vendor)
    assert rerun.status == Status.APPROVED
    assert rerun.run_id != receipt.result.run_id
    assert len(client.rows["runs"]) == 2
    assert client.rows["runs"][0] == first_run
    assert client.rows["applications"][0]["current_status"] == "APPROVED"
    assert all(row["version"] == 1 for row in client.rows["documents"])
    with pytest.raises(TerminalApplication):
        service.resubmit(receipt.application_id, receipt.tracking_code, fixed_vendor)


def test_updated_bank_pdf_gets_new_version(prepared):
    client, repo, service = prepared
    vendor, gst, bank = case("ec4_missing_bank_holder")
    receipt = service.submit(vendor, gst, bank)
    _, _, corrected_bank = case("happy")
    assert service.resubmit(receipt.application_id, receipt.tracking_code, vendor, bank_upload=corrected_bank).status == Status.APPROVED
    versions = [r["version"] for r in client.rows["documents"] if r["doc_type"] == "BANK"]
    assert versions == [1, 2]
    assert repo.load_latest_document(receipt.application_id, "BANK").content == corrected_bank.content


def test_db_duplicate_detection_is_real_lookup_not_empty_assumption(prepared):
    client, repo, service = prepared
    vendor, gst, bank = case("happy")
    prior = service.submit(vendor, gst, bank)
    assert prior.result.status == Status.APPROVED
    next_vendor, next_gst, next_bank = case("ec3_duplicate_changed_bank")
    second = service.submit(next_vendor, next_gst, next_bank)
    assert second.result.status == Status.PENDING
    check = next(c for c in second.result.checks if c.code == "DUPLICATE_GSTIN")
    assert check.state.value == "FAIL"
    assert prior.application_id in check.admin_detail
    assert prior.application_id not in check.vendor_message


def test_fail_closed_if_commit_not_confirmed(prepared):
    client, repo, service = prepared
    client.fail_table = "runs"
    vendor, gst, bank = case("happy")
    events = []
    with pytest.raises(PersistenceError):
        service.submit(vendor, gst, bank, stage_callback=events.append)
    assert client.rows["applications"][0]["current_status"] == "PENDING"
    assert client.rows["applications"][0]["latest_run_id"] is None
    assert any(e.stage_id == "S9" and e.event == "FAILED" for e in events)
    assert not any(e.stage_id == "S9" and e.event == "COMPLETED" for e in events)


def test_admin_decision_requires_reason_and_audit(prepared):
    client, repo, service = prepared
    vendor, gst, bank = case("ec1_pan_gstin")
    receipt = service.submit(vendor, gst, bank)
    with pytest.raises(ValueError):
        repo.admin_review(receipt.application_id, "APPROVE", "")
    audit = repo.admin_review(receipt.application_id, "REJECT", "PAN discrepancy unresolved")
    assert audit["action"] == "REJECT"
    app, _ = service.track(receipt.application_id, receipt.tracking_code)
    assert app["current_status"] == "REJECTED"
    assert app["decision_source"] == "MANUAL"
    assert len(client.rows["review_actions"]) == 1


def test_no_key_produces_safe_config_error(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    with pytest.raises(PersistenceError):
        SupabaseRepository.from_env()
