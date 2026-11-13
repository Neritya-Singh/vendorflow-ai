"""Real execution stages, independently testable with injected providers."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4
from .models import CheckResult, VendorSubmission, WorkflowResult, StageEvent, Status, ExtractedDocuments
from .pdf_reader import PDFInput, read_pdf, ReadPDF, UploadError, likely_swapped_pdf_roles
from .gemini_extractor import Extractor, ExtractionFailure
from .rules import checks_without_duplicate, duplicate_check, make_decision, normalize_submission

StageCallback = Callable[[StageEvent], None]
Lookup = Callable[[str, str], list[str]]
Screening = Callable[[VendorSubmission, str], list[CheckResult]]
EvidenceChecks = Callable[[VendorSubmission, ExtractedDocuments], list[CheckResult]]


class MinimumIntakeError(ValueError):
    pass


class ProcessingPipeline:
    def __init__(self, extractor: Extractor, approved_lookup: Lookup | None = None, *,
                 screening: Screening | None = None, name_key: Callable[[str | None], str] | None = None,
                 evidence_checks: EvidenceChecks | None = None):
        """`screening`, `name_key` and `evidence_checks` are optional v2 policy hooks. When
        omitted the v1.1 behaviour (approved-only duplicate check, strict name compare,
        no extra rule checks) is unchanged."""
        self.extractor = extractor
        self.approved_lookup = approved_lookup
        self.screening = screening
        self.name_key = name_key
        self.evidence_checks = evidence_checks

    def evaluate(self, vendor: VendorSubmission, gst_upload: PDFInput | None, bank_upload: PDFInput | None,
                 *, application_id: str | None = None, trigger: str = "submission",
                 stage_callback: StageCallback | None = None,
                 persistence_planned: bool = False) -> WorkflowResult:
        if not vendor.legal_name.strip() or not vendor.contact_email.strip():
            raise MinimumIntakeError("Legal business name and contact email are needed to create an application.")
        if trigger not in ("submission", "resubmission"):
            raise ValueError("Unknown workflow trigger")
        application_id = application_id or ("VF-" + uuid4().hex[:12].upper())
        run_id = "RUN-" + uuid4().hex[:12].upper()
        started = datetime.now(timezone.utc)
        tick = perf_counter()
        stage_events: list[StageEvent] = []

        def emit(stage_id: str, label: str, event: str, note: str = "") -> None:
            entry = StageEvent(stage_id=stage_id, label=label, event=event, note=note)
            stage_events.append(entry)
            if stage_callback:
                stage_callback(entry)

        emit("S1", "Receive application", "STARTED")
        emit("S1", "Receive application", "COMPLETED", "Minimum intake accepted")

        emit("S2", "Read PDF documents", "STARTED")
        try:
            gst_pdf = read_pdf(gst_upload)
            bank_pdf = read_pdf(bank_upload)
        except UploadError:
            emit("S2", "Read PDF documents", "FAILED", "Invalid upload; no status issued")
            raise
        readable_count = sum(bool(pdf and pdf.readable) for pdf in (gst_pdf, bank_pdf))
        swapped_documents = likely_swapped_pdf_roles(gst_pdf, bank_pdf)
        emit("S2", "Read PDF documents", "COMPLETED", f"{readable_count}/2 PDFs readable")

        emit("S3", "Extract evidence with Gemini", "STARTED")
        extracted = ExtractedDocuments.empty()
        extraction_error = False
        try:
            if swapped_documents:
                emit("S3", "Extract evidence with Gemini", "SKIPPED",
                     "Likely reversed document uploads; no AI request issued")
            elif readable_count:
                extracted = self.extractor.extract(
                    gst_pdf.text if gst_pdf and gst_pdf.readable else "",
                    bank_pdf.text if bank_pdf and bank_pdf.readable else "",
                )
            else:
                emit("S3", "Extract evidence with Gemini", "SKIPPED", "No readable document text")
        except ExtractionFailure as failure:
            extraction_error = True
            diagnostic = getattr(self.extractor, "last_diagnostic", None)
            # Do NOT emit provider error text, exceptions, document data or keys.
            if diagnostic and diagnostic.category != "UNAVAILABLE":
                note = "AI extraction failed: " + diagnostic.summary() + "; routed to review"
            else:
                note = (f"AI extraction failed: {failure.category}; "
                        f"attempts={failure.attempts}; routed to review")
            emit("S3", "Extract evidence with Gemini", "FAILED", note)
        except Exception:
            extraction_error = True
            emit("S3", "Extract evidence with Gemini", "FAILED",
                 "AI extraction failed: UNAVAILABLE; routed to review")
        else:
            if readable_count and not swapped_documents:
                diagnostic = getattr(self.extractor, "last_diagnostic", None)
                note = ("Structured document fields extracted; " + diagnostic.summary()
                        if diagnostic and diagnostic.category == "SUCCESS"
                        else "Structured document fields extracted")
                emit("S3", "Extract evidence with Gemini", "COMPLETED", note)

        emit("S4", "Normalize input values", "STARTED")
        normalized = normalize_submission(vendor)
        emit("S4", "Normalize input values", "COMPLETED", "Comparable identity fields prepared")

        emit("S5", "Apply deterministic rules", "STARTED")
        checks = checks_without_duplicate(normalized, extracted, gst_pdf, bank_pdf, extraction_error,
                                          swapped_documents=swapped_documents,
                                          **({"name_key": self.name_key} if self.name_key else {}))
        if self.evidence_checks is not None:
            checks.extend(self.evidence_checks(normalized, extracted))
        failed_count = sum(c.state.value != "PASS" for c in checks)
        emit("S5", "Apply deterministic rules", "COMPLETED", f"{failed_count} checks require attention")

        if self.screening is not None:
            emit("S6", "Check our records", "STARTED")
            screened = self.screening(normalized, application_id)
            checks.extend(screened)
            unknown = any(c.state.value == "UNKNOWN" for c in screened)
            emit("S6", "Check our records", "FAILED" if unknown else "COMPLETED",
                 "Records check needs review" if unknown else "Records checked")
        else:
            emit("S6", "Check approved-vendor duplicates", "STARTED")
            duplicate = duplicate_check(normalized, self.approved_lookup, application_id)
            checks.append(duplicate)
            lookup_event = "FAILED" if (duplicate.state.value == "UNKNOWN" and self.approved_lookup is not None) else "COMPLETED"
            if self.approved_lookup is None:
                lookup_event = "SKIPPED"
            emit("S6", "Screen registration identity", lookup_event,
                 "Identity screening step completed" if duplicate.state.value != "UNKNOWN" else "Identity screening requires review")

        emit("S7", "Route policy decision", "STARTED")
        outcome, reasons, all_reasons, next_action = make_decision(checks)
        emit("S7", "Route policy decision", "COMPLETED", outcome)

        emit("S8", "Prepare actionable explanations", "STARTED")
        emit("S8", "Prepare actionable explanations", "COMPLETED", "Rule-derived explanations ready")

        if not persistence_planned:
            emit("S9", "Persist application and run", "SKIPPED", "Supabase connection pending (Stage 3.3)")
        finished = datetime.now(timezone.utc)
        return WorkflowResult(
            application_id=application_id,
            run_id=run_id,
            trigger=trigger,
            status=Status(outcome),
            reasons=reasons,
            all_reasons=all_reasons,
            next_action=next_action,
            checks=checks,
            extracted=extracted,
            stage_events=stage_events,
            started_at=started,
            finished_at=finished,
            elapsed_ms=max(0, round((perf_counter() - tick) * 1000)),
            persisted=False,
            extraction_error=extraction_error,
        )
