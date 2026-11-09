"""REAL PDF parsing + FAKE extraction provider. Never presented as a live AI call."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import types
import pytest

from vendorflow.models import VendorSubmission, ExtractedDocuments, GSTExtraction, BankExtraction, Status, CheckState
from vendorflow.pdf_reader import PDFInput, read_pdf, UploadError, MAX_PDF_BYTES
from vendorflow.pipeline import ProcessingPipeline, MinimumIntakeError
from vendorflow.gemini_extractor import GeminiExtractor, ExtractionFailure

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def field(text: str, label: str) -> str | None:
    lines = [line.strip() for line in text.splitlines()]
    for index, line in enumerate(lines):
        if line.casefold() == (label + ":").casefold() and index + 1 < len(lines):
            return lines[index + 1]
    return None


class OfflineTestExtractor:
    """Deterministic TEST DOUBLE, never part of deployed Gemini integration."""

    def __init__(self):
        self.calls = 0

    def extract(self, gst_text: str, bank_text: str) -> ExtractedDocuments:
        self.calls += 1
        return ExtractedDocuments(
            gst=GSTExtraction(
                legal_name=field(gst_text, "Legal business name"),
                gstin=field(gst_text, "GSTIN"),
                state=field(gst_text, "Business state"),
                address=field(gst_text, "Business address"),
            ),
            bank=BankExtraction(
                holder_name=field(bank_text, "Account holder"),
                account_number=field(bank_text, "Account number"),
                ifsc=field(bank_text, "IFSC"),
            ),
        )


class FailingExtractor:
    def extract(self, gst_text, bank_text):
        raise ExtractionFailure("Synthetic provider outage in test")


def case(name="happy"):
    base = FIXTURES / name
    vendor = VendorSubmission.model_validate_json((base / "submission.json").read_text())
    gst_path, bank_path = base / "gst_certificate.pdf", base / "bank_confirmation.pdf"
    return vendor, PDFInput(gst_path.name, gst_path.read_bytes()), PDFInput(bank_path.name, bank_path.read_bytes())


def run(name="happy", *, extractor=None, lookup=lambda gstin, current: [], **overrides):
    vendor, gst, bank = case(name)
    vendor = vendor.model_copy(update=overrides)
    engine = ProcessingPipeline(extractor or OfflineTestExtractor(), approved_lookup=lookup)
    return engine.evaluate(vendor, gst, bank)


def failing_codes(result):
    return {check.code for check in result.checks if check.state != CheckState.PASS}


def test_happy_path_real_pdfs_with_offline_test_extractor():
    extractor = OfflineTestExtractor()
    result = run(extractor=extractor)
    assert result.status == Status.APPROVED
    assert len(result.checks) == 14
    assert all(check.state == CheckState.PASS for check in result.checks)
    assert extractor.calls == 1
    assert result.extracted.bank.account_number == "001234567890"
    assert result.elapsed_ms >= 0
    assert result.persisted is False  # NEVER pretend backend has saved it
    assert result.decision_source == "AUTOMATED"
    assert any(e.stage_id == "S9" and e.event == "SKIPPED" for e in result.stage_events)
    assert any(e.stage_id == "S3" and e.event == "COMPLETED" for e in result.stage_events)
    assert all("001234567890" not in e.note for e in result.stage_events)


def test_ec1_pan_gstin_cross_field():
    result = run("ec1_pan_gstin")
    assert result.status == Status.PENDING
    assert "PAN_GSTIN_MISMATCH" in failing_codes(result)


def test_ec2_bank_ownership_ambiguity():
    result = run("ec2_bank_owner")
    assert result.status == Status.PENDING
    assert "BANK_NAME_REVIEW" in failing_codes(result)


def test_ec3_duplicate_changed_bank():
    result = run("ec3_duplicate_changed_bank", lookup=lambda gstin, current: ["VF-PREVIOUS"])
    assert result.status == Status.PENDING
    duplicate = next(c for c in result.checks if c.code == "DUPLICATE_GSTIN")
    assert duplicate.state == CheckState.FAIL
    assert "VF-PREVIOUS" in duplicate.admin_detail
    assert "VF-PREVIOUS" not in duplicate.vendor_message


def test_ec4_unavailable_bank_holder_not_guessed():
    result = run("ec4_missing_bank_holder")
    assert result.status == Status.PENDING
    assert "BANK_NAME_REVIEW" in failing_codes(result)
    assert "EXTRACTION_INCOMPLETE" in failing_codes(result)
    assert result.extracted.bank.holder_name is None


def test_missing_bank_document_is_pending():
    vendor, gst, _ = case()
    result = ProcessingPipeline(OfflineTestExtractor(), lambda g, a: []).evaluate(vendor, gst, None)
    assert result.status == Status.PENDING
    assert "DOCUMENT_READABILITY" in failing_codes(result)
    assert "Bank proof" in " ".join(result.reasons)


def test_valid_pdf_but_unreadable_document_is_pending():
    vendor, gst, bank = case()
    # truncate while retaining PDF header to exercise damaged-document handling
    damaged = PDFInput("bank.pdf", bank.content[:50])
    result = ProcessingPipeline(OfflineTestExtractor(), lambda g, a: []).evaluate(vendor, gst, damaged)
    assert result.status == Status.PENDING
    assert "DOCUMENT_READABILITY" in failing_codes(result)


def test_non_pdf_upload_rejected_before_processing():
    vendor, gst, _ = case()
    bad = PDFInput("bank.pdf", b"not really a pdf")
    with pytest.raises(UploadError):
        ProcessingPipeline(OfflineTestExtractor(), lambda g, a: []).evaluate(vendor, gst, bad)


def test_oversized_pdf_rejected():
    with pytest.raises(UploadError, match="exceeds 5 MB"):
        read_pdf(PDFInput("large.pdf", b"%PDF-" + b"X" * MAX_PDF_BYTES))


def test_extraction_api_failure_cannot_approve():
    result = run(extractor=FailingExtractor())
    assert result.status == Status.PENDING
    assert result.extraction_error is True
    assert "EXTRACTION_UNAVAILABLE" in failing_codes(result)
    assert any(e.stage_id == "S3" and e.event == "FAILED" for e in result.stage_events)


def test_no_duplicate_registry_cannot_approve():
    result = run(lookup=None)
    assert result.status == Status.PENDING
    assert "DUPLICATE_GSTIN" in failing_codes(result)


def test_resubmission_new_run_same_application_id():
    vendor, gst, bank = case("happy")
    workflow = ProcessingPipeline(OfflineTestExtractor(), lambda g, a: [])
    first = workflow.evaluate(vendor.model_copy(update={"pan": "PQRST1234U"}), gst, bank,
                              application_id="VF-SAME")
    rerun = workflow.evaluate(vendor, gst, bank, application_id="VF-SAME", trigger="resubmission")
    assert first.status == Status.PENDING
    assert rerun.status == Status.APPROVED
    assert rerun.application_id == first.application_id
    assert first.run_id != rerun.run_id
    assert rerun.trigger == "resubmission"


def test_resubmission_does_not_match_own_application():
    vendor, gst, bank = case()
    result = ProcessingPipeline(OfflineTestExtractor(), lambda g, a: [a]).evaluate(
        vendor, gst, bank, application_id="VF-MYSELF", trigger="resubmission")
    assert result.status == Status.APPROVED


def test_blank_minimum_intake_declined():
    vendor, gst, bank = case()
    vendor.legal_name = ""
    with pytest.raises(MinimumIntakeError):
        ProcessingPipeline(OfflineTestExtractor()).evaluate(vendor, gst, bank)


def test_invalid_ifsc_goes_to_review():
    result = run(ifsc="AAAA12345")
    assert result.status == Status.PENDING
    assert "IFSC_FORMAT" in failing_codes(result)


def test_gst_document_name_discrepancy_goes_to_review():
    result = run(legal_name="Acme Widgets Limited")
    assert result.status == Status.PENDING
    assert "GST_DOCUMENT_MISMATCH" in failing_codes(result)


def test_missing_required_field_goes_to_review():
    result = run(contact_name="")
    assert result.status == Status.PENDING
    assert "REQUIRED_FIELDS" in failing_codes(result)


def test_duplicate_lookup_exception_never_approves():
    def fail_lookup(gstin, current):
        raise ConnectionError("test failure")
    result = run(lookup=fail_lookup)
    assert result.status == Status.PENDING
    assert "DUPLICATE_GSTIN" in failing_codes(result)


def test_no_automatic_rejection_on_any_fixture():
    for name in ["happy", "ec1_pan_gstin", "ec2_bank_owner", "ec3_duplicate_changed_bank", "ec4_missing_bank_holder"]:
        assert run(name).status != Status.REJECTED


class MockGeminiModels:
    def __init__(self, value: ExtractedDocuments):
        self.calls = []
        self.value = value

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        class Response:
            pass
        response = Response()
        response.text = self.value.model_dump_json()
        return response


class MockGeminiClient:
    def __init__(self, value):
        self.models = MockGeminiModels(value)


@pytest.fixture
def mocked_genai_sdk(monkeypatch):
    """A test-only import stub because this execution environment cannot install SDKs."""
    module = types.ModuleType("google.genai")
    types_module = types.ModuleType("google.genai.types")
    types_module.GenerateContentConfig = lambda **kwargs: types.SimpleNamespace(**kwargs)
    module.types = types_module
    monkeypatch.setitem(sys.modules, "google.genai", module)
    monkeypatch.setitem(sys.modules, "google.genai.types", types_module)
    import google
    monkeypatch.setattr(google, "genai", module, raising=False)
    return module


def test_gemini_sdk_adapter_schema_request_with_mock_client(mocked_genai_sdk):
    """Tests SDK wiring only, NOT a live Google request."""
    client = MockGeminiClient(OfflineTestExtractor().extract("GSTIN:\n09ABCDE1234F1Z5", ""))
    extractor = GeminiExtractor(api_key="TEST_FAKE_NOT_REAL", client=client)
    result = extractor.extract("GSTIN:\n09ABCDE1234F1Z5", "")
    assert len(client.models.calls) == 1
    assert client.models.calls[0]["config"].response_mime_type == "application/json"
    assert "additionalProperties" in str(client.models.calls[0]["config"].response_json_schema)
    assert result.bank.holder_name is None
    assert result.gst.gstin == "09ABCDE1234F1Z5"


def test_absent_document_cannot_be_filled_by_model_hallucination(mocked_genai_sdk):
    full = OfflineTestExtractor().extract(
        (FIXTURES / "happy" / "gst_certificate.pdf").name, "")
    # Deliberately return non-null data for the document not passed to the model.
    full.bank = BankExtraction(holder_name="MADE UP", account_number="123456", ifsc="DEMO0123456")
    client = MockGeminiClient(full)
    result = GeminiExtractor(client=client, api_key="TEST_FAKE_NOT_REAL").extract("GSTIN:\n09ABCDE1234F1Z5", "")
    assert result.bank.holder_name is None
    assert result.bank.account_number is None


def test_ai_hallucinated_matching_bank_value_cannot_approve():
    """Extraction agreeing with user does not pass if contradicted by source PDF."""
    class LyingExtractor(OfflineTestExtractor):
        def extract(self, gst_text, bank_text):
            result = super().extract(gst_text, bank_text)
            result.bank.account_number = "001234567890"
            return result
    # EC3 PDF actually says 009999887766. Simulated AI falsely says user's older value.
    result = run("ec3_duplicate_changed_bank", extractor=LyingExtractor(),
                 account_number="001234567890")
    assert result.status == Status.PENDING
    assert "EXTRACTION_INCOMPLETE" in failing_codes(result)


def test_document_extraction_evidence_is_not_verified_registration():
    result = run()
    assert result.status == Status.APPROVED
    assert any("prototype document-consistency" in msg for msg in result.reasons)
