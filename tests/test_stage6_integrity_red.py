"""Stage 6.0 RED acceptance tests for database correctness, before migrations.

Run against OFFLINE FakeSupabase, not a production project. These intentionally
fail on audited v1.0 and cannot replace disposable PostgreSQL integration tests.
"""

from __future__ import annotations

from copy import deepcopy
import pytest

from tests.test_backend import OfflineTestExtractor, case
from tests.test_persistence_offline import FakeSupabase
from vendorflow.models import Status
from vendorflow.persistence import PersistenceError, SupabaseRepository, PersistentVendorService


def _service():
    db = FakeSupabase()
    repository = SupabaseRepository(db)
    return db, repository, PersistentVendorService(repository, OfflineTestExtractor())


def test_H03_two_manual_approvals_same_gstin_cannot_both_commit():
    """Even sequential manual decisions must satisfy approved identity uniqueness.

    This does NOT prove concurrency integrity; a real PostgreSQL two-connection
    test is still required after a staged uniqueness migration.
    """
    db, repo, service = _service()
    vendor, _gst, _bank = case("happy")
    first = service.submit(vendor, None, None)
    second = service.submit(vendor, None, None)
    assert first.result.status == second.result.status == Status.PENDING
    repo.admin_review(first.application_id, "APPROVE", "Synthetic manual approval test")
    try:
        repo.admin_review(second.application_id, "APPROVE", "Synthetic manual approval test")
    except PersistenceError:
        pass  # Expected after uniqueness is enforced in the transaction.
    approved = [a for a in db.rows["applications"] if a["current_status"] == "APPROVED"]
    assert len(approved) <= 1, "Two approved vendor identities share one GSTIN"


def test_H04_stale_reviewer_action_must_be_rejected():
    db, repo, service = _service()
    vendor, gst, bank = case("ec1_pan_gstin")
    initial = service.submit(vendor, gst, bank)
    old_run_id = initial.result.run_id
    # A corrected but still unresolved second run is the newer committed revision.
    pending_vendor = vendor.model_copy(update={"contact_name": "New Revised Contact"})
    updated = service.resubmit(initial.application_id, initial.tracking_code, pending_vendor)
    assert updated.status == Status.PENDING
    assert updated.run_id != old_run_id
    # Interface proposed by audited plan: stale preconditions must be checked
    # transactionally, not merely in a Streamlit form.
    with pytest.raises(PersistenceError):
        repo.admin_review(
            initial.application_id, "APPROVE", "Based only on older run evidence",
            expected_latest_run_id=old_run_id,
        )
    assert db.rows["applications"][0]["current_status"] == "PENDING"


def test_H04_stale_vendor_correction_must_be_rejected():
    db, _repo, service = _service()
    vendor, gst, bank = case("ec1_pan_gstin")
    initial = service.submit(vendor, gst, bank)
    old_run_id = initial.result.run_id
    newer_vendor = vendor.model_copy(update={"contact_name": "Newer Correction"})
    updated = service.resubmit(initial.application_id, initial.tracking_code, newer_vendor)
    assert updated.status == Status.PENDING
    with pytest.raises(PersistenceError):
        service.resubmit(
            initial.application_id, initial.tracking_code,
            vendor.model_copy(update={"contact_name": "Stale Correction"}),
            expected_latest_run_id=old_run_id,
        )
    assert db.rows["applications"][0]["latest_run_id"] == updated.run_id


def test_H06_failed_replacement_does_not_advance_active_bank_document():
    db, repo, service = _service()
    vendor, gst, old_bank = case("ec4_missing_bank_holder")
    initial = service.submit(vendor, gst, old_bank)
    assert initial.result.status == Status.PENDING
    committed = repo.load_latest_document(initial.application_id, "BANK")
    assert committed.content == old_bank.content
    _fixed_vendor, _fixed_gst, new_bank = case("happy")
    db.fail_table = "runs"
    with pytest.raises(PersistenceError):
        service.resubmit(initial.application_id, initial.tracking_code, vendor, bank_upload=new_bank)
    db.fail_table = None
    assert db.rows["applications"][0]["latest_run_id"] == initial.result.run_id
    # Last committed document must remain the active default even when a staged
    # replacement object/metadata row was successfully uploaded.
    selected = repo.load_latest_document(initial.application_id, "BANK")
    assert selected is not None
    assert selected.content == old_bank.content, "Failed correction selected an uncommitted PDF"


def test_H06_each_committed_run_binds_exact_document_ids():
    db, _repo, service = _service()
    vendor, gst, bank = case("ec4_missing_bank_holder")
    initial = service.submit(vendor, gst, bank)
    run = db.rows["runs"][0]
    # The migration may store a separate manifest or run_document mapping;
    # this expected form is the simplest proposed format to start with.
    assert "document_manifest" in run, "Committed runs have no immutable source-document manifest"
    manifest = run["document_manifest"]
    assert {d["doc_type"] for d in manifest} == {"GST", "BANK"}
    assert all(d.get("id") and d.get("file_sha256") for d in manifest)
