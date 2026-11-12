"""VendorFlow AI Stage 6.0: expected-to-fail regression tests.

Copy to tests/test_stage6_regressions.py in a LOCAL checkout of
Neritya-Singh/vendorflow-ai @ f213390. Run offline with pytest.
These tests intentionally specify desired v1.1 behavior and are expected
not to pass on the audited MVP. No provider secrets or live services needed.
"""

from __future__ import annotations

import re

import pytest

from tests.test_backend import OfflineTestExtractor, case
from tests.test_persistence_offline import FakeSupabase
from vendorflow.models import CheckState, Status
from vendorflow.persistence import SupabaseRepository, PersistentVendorService
from vendorflow.pipeline import ProcessingPipeline


def _current(vendor, gst, bank, extractor=None, lookup=None):
    return ProcessingPipeline(
        extractor or OfflineTestExtractor(),
        lookup if lookup is not None else (lambda _gstin, _app: []),
    ).evaluate(vendor, gst, bank)


@pytest.mark.parametrize("truncated", ["123456", "001234", "567890", "2345678"])
def test_H01_bank_account_substring_never_autoapproves(truncated):
    vendor, gst, bank = case("happy")

    class WrongAccountExtractor(OfflineTestExtractor):
        def extract(self, gst_text, bank_text):
            result = super().extract(gst_text, bank_text)
            result.bank.account_number = truncated
            return result

    result = _current(
        vendor.model_copy(update={"account_number": truncated}),
        gst,
        bank,
        extractor=WrongAccountExtractor(),
    )
    assert result.status == Status.PENDING, (
        "R13 source grounding must not accept a shortened account merely "
        "because it appears inside a longer printed account."
    )
    assert any(
        c.code == "EXTRACTION_INCOMPLETE" and c.state != CheckState.PASS
        for c in result.checks
    )


@pytest.mark.parametrize("gstin", [
    "09ABCDE 1234F1Z5",
    " 09ABCDE1234F1Z5 ",
    "09abcde1234f1z5",
    "09ABCDE\t1234F1Z5",
])
def test_H02_approved_registry_uses_canonical_gstin(gstin):
    db = FakeSupabase()
    service = PersistentVendorService(SupabaseRepository(db), OfflineTestExtractor())
    vendor, gst, bank = case("happy")
    previous = service.submit(vendor.model_copy(update={"gstin": gstin}), gst, bank)
    assert previous.result.status == Status.APPROVED
    duplicate = service.submit(vendor, gst, bank)
    assert duplicate.result.status == Status.PENDING, (
        "A second application with the same canonical GSTIN must never "
        "be automatically approved."
    )
    assert db.rows["applications"][0]["gstin_normalized"] == "09ABCDE1234F1Z5", (
        "The current FakeSupabase must eventually implement the same "
        "canonicalization as the PostgreSQL schema."
    )


def test_C1_missing_fields_and_invalid_email_report_both_without_mismatch():
    vendor, _gst, _bank = case("happy")
    result = _current(
        vendor.model_copy(update={
            "contact_email": "not-an-email",
            "pan": "",
            "gstin": "",
            "account_number": "",
            "ifsc": "",
        }),
        None,
        None,
    )
    assert result.status == Status.PENDING
    summary = " ".join(result.all_reasons).lower()
    assert "email" in summary and "valid" in summary
    assert "pan" in summary and "gstin" in summary
    assert not re.search(r"(?:pan|account|ifsc).{0,65}(?:does not match|differs)", summary), (
        "Do not state a comparison mismatch if a required value or PDF is missing."
    )


def test_C1_missing_bank_proof_never_called_document_mismatch():
    vendor, gst, _bank = case("happy")
    result = _current(vendor, gst, None)
    assert result.status == Status.PENDING
    summary = " ".join(result.reasons).lower()
    assert "bank" in summary and ("upload" in summary or "missing" in summary)
    assert "differs" not in summary and "does not match" not in summary


def test_H9_public_reason_never_exposes_duplicate_membership():
    vendor, gst, bank = case("happy")
    miss = _current(vendor, gst, bank, lookup=lambda _g, _a: [])
    hit = _current(vendor, gst, bank, lookup=lambda _g, _a: ["VF-OTHER"])
    assert miss.status == Status.APPROVED
    assert hit.status == Status.PENDING
    # The current UI renders `reasons` as the vendor-facing top summary.
    # A future audience-specific view model may move this contract there.
    public_reason = " ".join(hit.reasons + [hit.next_action]).lower()
    assert "duplicate" not in public_reason
    assert "already registered" not in public_reason
    assert "vf-other" not in public_reason

