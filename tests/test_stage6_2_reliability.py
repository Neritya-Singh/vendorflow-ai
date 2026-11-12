"""Stage 6.2: revision CAS, PDF provenance, safe intake/retry (offline fakes)."""
from copy import deepcopy
from uuid import uuid4

import pytest

from tests.test_backend import OfflineTestExtractor, case
from tests.test_persistence_offline import FakeSupabase
from vendorflow.persistence import (
    SupabaseRepository, PersistentVendorService, PersistenceError,
    UnauthorizedTracking, StaleRevision, prepare_intake, PreparedIntake,
)
from vendorflow.models import Status


def setup():
    db = FakeSupabase()
    repo = SupabaseRepository(db)
    return db, repo, PersistentVendorService(repo, OfflineTestExtractor())


def test_stale_vendor_revision_rejected_even_if_latest_run_unchanged():
    db, repo, service = setup()
    vendor, gst, bank = case("ec1_pan_gstin")
    initial = service.submit(vendor, gst, bank)
    revision = db.rows["applications"][0]["revision"]
    repo.admin_review(initial.application_id, "REQUEST_CORRECTION", "Fix the PAN record", expected_revision=revision)
    with pytest.raises(StaleRevision):
        service.resubmit(initial.application_id, initial.tracking_code, vendor,
                         expected_latest_run_id=initial.result.run_id,
                         expected_revision=revision)
    assert len(db.rows["runs"]) == 1
    assert db.rows["applications"][0]["revision"] == revision + 1


def test_stale_admin_revision_rejected_after_vendor_update():
    db, repo, service = setup()
    vendor, gst, bank = case("ec1_pan_gstin")
    receipt = service.submit(vendor, gst, bank)
    old = deepcopy(db.rows["applications"][0])
    service.resubmit(receipt.application_id, receipt.tracking_code, vendor)
    with pytest.raises(StaleRevision):
        repo.admin_review(receipt.application_id, "APPROVE", "Old evidence decision",
                          expected_latest_run_id=old["latest_run_id"],
                          expected_revision=old["revision"])
    assert len(db.rows["review_actions"]) == 0
    assert db.rows["applications"][0]["current_status"] == "PENDING"


def test_revision_conflicts_do_not_stage_new_pdf():
    db, repo, service = setup()
    vendor, gst, bank = case("ec1_pan_gstin")
    receipt = service.submit(vendor, gst, bank)
    old_revision = db.rows["applications"][0]["revision"]
    repo.admin_review(receipt.application_id, "REQUEST_CORRECTION", "Updated reviewer note")
    before = len(db.rows["documents"])
    with pytest.raises(StaleRevision):
        service.resubmit(receipt.application_id, receipt.tracking_code, vendor,
                         bank_upload=bank, expected_revision=old_revision)
    assert len(db.rows["documents"]) == before


def test_each_run_manifest_has_original_and_replacement_bytes():
    db, repo, service = setup()
    vendor, gst, first_bank = case("ec4_missing_bank_holder")
    receipt = service.submit(vendor, gst, first_bank)
    first = deepcopy(db.rows["runs"][0]["document_manifest"])
    assert {d["doc_type"] for d in first} == {"GST", "BANK"}
    first_bank_reference = next(d for d in first if d["doc_type"] == "BANK")
    assert repo.load_run_document(receipt.application_id, receipt.result.run_id, "BANK").content == first_bank.content
    _, _, second_bank = case("happy")
    result = service.resubmit(receipt.application_id, receipt.tracking_code, vendor, bank_upload=second_bank)
    new_manifest = db.rows["runs"][1]["document_manifest"]
    new_bank_reference = next(d for d in new_manifest if d["doc_type"] == "BANK")
    assert new_bank_reference["version"] == first_bank_reference["version"] + 1
    assert new_bank_reference["id"] != first_bank_reference["id"]
    assert db.rows["runs"][0]["document_manifest"] == first
    assert repo.load_run_document(receipt.application_id, receipt.result.run_id, "BANK").content == first_bank.content
    assert repo.load_run_document(receipt.application_id, result.run_id, "BANK").content == second_bank.content
    assert repo.load_latest_document(receipt.application_id, "BANK").content == second_bank.content


def test_failed_commit_never_activates_staged_replacement_even_on_next_retry():
    db, repo, service = setup()
    vendor, gst, bank = case("ec4_missing_bank_holder")
    receipt = service.submit(vendor, gst, bank)
    _, _, fixed_bank = case("happy")
    db.fail_table = "runs"
    with pytest.raises(PersistenceError):
        service.resubmit(receipt.application_id, receipt.tracking_code, vendor, bank_upload=fixed_bank)
    db.fail_table = None
    assert repo.load_latest_document(receipt.application_id, "BANK").content == bank.content
    pending_again = service.resubmit(receipt.application_id, receipt.tracking_code, vendor)
    manifest = next(d for d in db.rows["runs"][-1]["document_manifest"] if d["doc_type"] == "BANK")
    assert pending_again.status == Status.PENDING
    assert manifest["version"] == 1
    assert repo.load_run_document(receipt.application_id, pending_again.run_id, "BANK").content == bank.content


def test_corrupt_file_refuses_historical_reuse():
    db, repo, service = setup()
    vendor, gst, bank = case("ec1_pan_gstin")
    receipt = service.submit(vendor, gst, bank)
    doc = next(d for d in db.rows["documents"] if d["doc_type"] == "BANK")
    db.storage.files[doc["storage_path"]] = b"tampered"
    with pytest.raises(PersistenceError):
        repo.load_latest_document(receipt.application_id, "BANK")
    with pytest.raises(PersistenceError):
        service.resubmit(receipt.application_id, receipt.tracking_code, vendor)


def test_failed_document_metadata_insert_cleans_uploaded_object():
    db, repo, service = setup()
    vendor, gst, bank = case("happy")
    db.fail_table = "documents"
    with pytest.raises(PersistenceError):
        service.submit(vendor, gst, bank)
    assert db.storage.files == {}
    assert db.rows["documents"] == []
    assert db.rows["runs"] == []
    assert len(db.rows["applications"]) == 1


def test_lost_document_metadata_ack_is_not_deleted():
    db, repo, service = setup()
    vendor, gst, bank = case("happy")
    db.lost_ack_table = "documents"
    receipt = service.submit(vendor, gst, bank)
    assert receipt.result.status == Status.APPROVED
    assert len(db.rows["documents"]) == 2
    assert len(db.storage.files) == 2
    assert repo.load_latest_document(receipt.application_id, "GST").content == gst.content


def test_retry_after_interrupted_first_save_uses_same_credentials_and_id():
    db, repo, service = setup()
    vendor, gst, bank = case("happy")
    prepared = prepare_intake()
    db.fail_table = "runs"
    with pytest.raises(PersistenceError):
        service.submit(vendor, gst, bank, prepared=prepared)
    assert db.rows["applications"][0]["id"] == prepared.application_id
    assert db.rows["applications"][0]["latest_run_id"] is None
    db.fail_table = None
    receipt = service.resume_submission(prepared.application_id, prepared.tracking_code,
                                        vendor, gst, bank)
    assert receipt.application_id == prepared.application_id
    assert receipt.tracking_code == prepared.tracking_code
    assert len(db.rows["applications"]) == len(db.rows["runs"]) == 1
    assert db.rows["applications"][0]["revision"] == 1


def test_lost_application_ack_can_be_recovered_from_prepared_credentials():
    db, repo, service = setup()
    vendor, gst, bank = case("happy")
    prepared = prepare_intake()
    db.lost_ack_table = "applications"
    receipt = service.submit(vendor, gst, bank, prepared=prepared)
    assert receipt.application_id == prepared.application_id
    assert receipt.result.persisted
    assert len(db.rows["applications"]) == 1


def test_lost_run_ack_returns_same_receipt_and_prevents_second_run():
    db, repo, service = setup()
    vendor, gst, bank = case("happy")
    prepared = prepare_intake()
    db.lost_ack_table = "runs"
    initial = service.submit(vendor, gst, bank, prepared=prepared)
    assert initial.result.persisted
    db.lost_ack_table = None
    replay = service.submit(vendor, gst, bank, prepared=prepared)
    assert replay.result.run_id == initial.result.run_id
    assert len(db.rows["applications"]) == 1
    assert len(db.rows["runs"]) == 1
    assert len(db.rows["documents"]) == 2


def test_wrong_token_cannot_hijack_recovery():
    db, repo, service = setup()
    vendor, gst, bank = case("happy")
    prepared = prepare_intake()
    db.fail_table = "runs"
    with pytest.raises(PersistenceError):
        service.submit(vendor, gst, bank, prepared=prepared)
    db.fail_table = None
    with pytest.raises(UnauthorizedTracking):
        service.resume_submission(prepared.application_id, "a" * 32, vendor, gst, bank)
    assert len(db.rows["runs"]) == 0


def test_forged_manifest_checksum_rejected_before_state_change():
    db, repo, service = setup()
    vendor, gst, bank = case("ec1_pan_gstin")
    receipt = service.submit(vendor, gst, bank)
    old_rev = db.rows["applications"][0]["revision"]
    fake_run = deepcopy(db.rows["runs"][0])
    fake_run["id"] = "RUN-FORGED-" + uuid4().hex[:8]
    fake_run["trigger"] = "resubmission"
    fake_run["document_manifest"][0]["file_sha256"] = "9" * 64
    fake_run["expected_revision"] = old_rev
    with pytest.raises(RuntimeError, match="manifest mismatch"):
        db.table("runs").insert(fake_run).execute()
    assert db.rows["applications"][0]["revision"] == old_rev


def test_reviewed_run_id_recorded_and_revision_monotonic():
    db, repo, service = setup()
    vendor, gst, bank = case("ec1_pan_gstin")
    receipt = service.submit(vendor, gst, bank)
    assert db.rows["applications"][0]["revision"] == 1
    audit = repo.admin_review(receipt.application_id, "REQUEST_CORRECTION", "Fix the PAN")
    assert audit["reviewed_run_id"] == receipt.result.run_id
    assert audit["expected_revision"] == 1
    assert db.rows["applications"][0]["revision"] == 2
    subsequent = service.resubmit(receipt.application_id, receipt.tracking_code, vendor,
                                  expected_revision=2)
    assert db.rows["applications"][0]["revision"] == 3
    assert subsequent.status == Status.PENDING


def test_lost_resubmission_ack_recovers_exact_revision():
    db, repo, service = setup()
    vendor, gst, bank = case("ec4_missing_bank_holder")
    initial = service.submit(vendor, gst, bank)
    db.lost_ack_table = "runs"
    updated = service.resubmit(initial.application_id, initial.tracking_code, vendor)
    assert updated.persisted
    assert updated.run_id != initial.result.run_id
    assert len(db.rows["runs"]) == 2
    assert db.rows["applications"][0]["revision"] == 2


def test_interrupted_upload_then_resume_does_not_reuse_uncommitted_pdf():
    db, repo, service = setup()
    vendor, gst, bank = case("ec1_pan_gstin")
    prepared = prepare_intake()
    db.fail_table = "runs"
    with pytest.raises(PersistenceError):
        service.submit(vendor, gst, bank, prepared=prepared)
    assert len(db.rows["applications"]) == 1
    assert len(db.rows["documents"]) == 2
    db.fail_table = None
    recovered = service.resume_submission(prepared.application_id, prepared.tracking_code, vendor)
    assert recovered.result.status == Status.PENDING
    assert db.rows["runs"][0]["document_manifest"] == []
    assert repo.load_latest_document(prepared.application_id, "GST") is None


def test_resume_existing_application_with_wrong_identity_is_rejected():
    db, repo, service = setup()
    vendor, gst, bank = case("happy")
    first = service.submit(vendor, gst, bank)
    fake = PreparedIntake(first.application_id, "wrong-secret-cannot-authorize-any-existing-app")
    with pytest.raises(PersistenceError):
        service.submit(vendor, gst, bank, prepared=fake)
    assert len(db.rows["applications"]) == 1
    assert len(db.rows["runs"]) == 1
