"""Supabase persistence, versioned private PDFs, token tracking, and audit trail.

All calls use a server-only Supabase secret. Never initialize this client in browser code.
The SQL `trg_vendorflow_commit_run` atomically records each immutable run AND updates
current application status. No local SQLite or fake 'saved' flags.
"""
from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from .models import StageEvent, Status, VendorSubmission, WorkflowResult
from .pdf_reader import PDFInput, read_pdf
from .pipeline import ProcessingPipeline, MinimumIntakeError, StageCallback
from .gemini_extractor import Extractor
from .rules import norm_id


class PersistenceError(RuntimeError):
    """Safe display message; NEVER include provider response or raw document data."""


class UnauthorizedTracking(PersistenceError):
    pass


class TerminalApplication(PersistenceError):
    pass


@dataclass
class ApplicationReceipt:
    application_id: str
    tracking_code: str  # shown ONCE to vendor; never stored as plaintext
    result: WorkflowResult


def _token_digest(application_id: str, token: str) -> str:
    return hashlib.sha256(f"{application_id}:{token}".encode("utf-8")).hexdigest()


class SupabaseRepository:
    BUCKET = "vendor-documents"

    def __init__(self, client):
        self.client = client

    @classmethod
    def from_env(cls) -> "SupabaseRepository":
        url = os.getenv("SUPABASE_URL", "").strip()
        # New Supabase secret keys preferred; legacy service_role key supported.
        secret = (os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
        if not url or not secret:
            raise PersistenceError("Supabase URL or server secret is not configured.")
        try:
            from supabase import create_client
            return cls(create_client(url, secret))
        except Exception as exc:
            raise PersistenceError("Could not connect to Supabase. Check server configuration.") from exc

    def create_application(self, vendor: VendorSubmission) -> tuple[str, str]:
        if not vendor.legal_name.strip() or not vendor.contact_email.strip():
            raise MinimumIntakeError("Legal business name and contact email are required.")
        application_id = "VF-" + uuid4().hex[:12].upper()
        token = secrets.token_urlsafe(24)
        data = {
            "id": application_id,
            "payload_json": vendor.model_dump(),
            "tracking_token_hash": _token_digest(application_id, token),
            "current_status": "PENDING", "decision_source": "AUTOMATED"
        }
        try:
            response = self.client.table("applications").insert(data).execute()
            if not response.data:
                raise PersistenceError("Application record was not confirmed by database.")
        except Exception as exc:
            raise PersistenceError("Could not create application. Please retry.") from exc
        return application_id, token

    def _application(self, application_id: str) -> dict:
        response = self.client.table("applications").select("*").eq("id", application_id).limit(1).execute()
        if not response.data:
            raise UnauthorizedTracking("Application ID or tracking code is incorrect.")
        return response.data[0]

    def authenticate_vendor(self, application_id: str, tracking_code: str) -> dict:
        # Constant-time compare and unpredictable token; no publicly queryable endpoint.
        try:
            record = self._application(application_id)
        except Exception as exc:
            raise UnauthorizedTracking("Application ID or tracking code is incorrect.") from exc
        expected = str(record.get("tracking_token_hash") or "")
        candidate = _token_digest(application_id, tracking_code)
        if not secrets.compare_digest(expected, candidate):
            raise UnauthorizedTracking("Application ID or tracking code is incorrect.")
        record.pop("tracking_token_hash", None)
        return record

    def approved_lookup(self, gstin: str, application_id: str) -> list[str]:
        """Fail closed on Supabase errors; pipeline catches and converts to UNKNOWN."""
        response = (self.client.table("applications")
                    .select("id")
                    .eq("current_status", "APPROVED")
                    .eq("gstin_normalized", norm_id(gstin))
                    .neq("id", application_id)
                    .execute())
        return [row["id"] for row in response.data]

    def _latest_document_row(self, application_id: str, doc_type: str) -> dict | None:
        response = (self.client.table("documents")
                    .select("*")
                    .eq("application_id", application_id)
                    .eq("doc_type", doc_type)
                    .order("version", desc=True)
                    .limit(1).execute())
        return response.data[0] if response.data else None

    def upload_document(self, application_id: str, doc_type: str, uploaded: PDFInput) -> dict:
        if doc_type not in ("GST", "BANK"):
            raise ValueError("Unknown PDF document type")
        # Blocks non-PDF and oversized uploads. Unreadable PDFs can be submitted for PENDING.
        read_pdf(uploaded)
        old = self._latest_document_row(application_id, doc_type)
        version = int(old["version"]) + 1 if old else 1
        sha = hashlib.sha256(uploaded.content).hexdigest()
        path = f"{application_id}/{doc_type}/v{version}-{uuid4().hex}.pdf"
        try:
            self.client.storage.from_(self.BUCKET).upload(
                path=path,
                file=uploaded.content,
                file_options={"content-type": "application/pdf", "upsert": "false"},
            )
            row = {
                "application_id": application_id,
                "doc_type": doc_type,
                "storage_path": path,
                "file_sha256": sha,
                "version": version,
                "filename": uploaded.filename,
            }
            response = self.client.table("documents").insert(row).execute()
            if not response.data:
                raise RuntimeError("No confirmed document metadata row")
            return response.data[0]
        except Exception as exc:
            # The private object may be orphaned after DB failure; no approval is claimed.
            raise PersistenceError("PDF upload or metadata save failed. No decision was saved.") from exc

    def load_latest_document(self, application_id: str, doc_type: str) -> PDFInput | None:
        row = self._latest_document_row(application_id, doc_type)
        if not row:
            return None
        try:
            content = self.client.storage.from_(self.BUCKET).download(row["storage_path"])
            if not isinstance(content, bytes):
                content = content.content
            if hashlib.sha256(content).hexdigest() != row["file_sha256"]:
                raise PersistenceError("Stored PDF integrity check failed.")
            return PDFInput(row["filename"], content)
        except Exception as exc:
            raise PersistenceError("Could not retrieve a stored PDF. No decision was issued.") from exc

    def commit_run(self, result: WorkflowResult, vendor: VendorSubmission,
                   *, stage_callback: StageCallback | None = None) -> WorkflowResult:
        """Inserting a run fires an SQL trigger that updates the application atomically."""
        started = StageEvent(stage_id="S9", label="Persist application and run", event="STARTED")
        if stage_callback:
            stage_callback(started)
        completed = StageEvent(stage_id="S9", label="Persist application and run", event="COMPLETED",
                               note="Run, decision and application status saved")
        stages = [e for e in result.stage_events if e.stage_id != "S9"] + [started, completed]
        timestamp = datetime.now(timezone.utc)
        run_record = {
            "id": result.run_id,
            "application_id": result.application_id,
            "trigger": result.trigger,
            "status": result.status.value,
            "decision": "AUTOMATED",
            "payload_json": vendor.model_dump(),
            "stages_json": [e.model_dump(mode="json") for e in stages],
            "extracted_json": result.extracted.model_dump(mode="json"),
            "checks_json": [c.model_dump(mode="json") for c in result.checks],
            "reasons_json": result.reasons,
            "all_reasons_json": result.all_reasons,
            "next_action": result.next_action,
            "extraction_error": result.extraction_error,
            "started_at": result.started_at.isoformat(),
            "finished_at": timestamp.isoformat(),
            "elapsed_ms": max(0, round((timestamp-result.started_at).total_seconds() * 1000)),
        }
        try:
            response = self.client.table("runs").insert(run_record).execute()
            if not response.data:
                raise RuntimeError("No database confirmation for run")
        except Exception as exc:
            if stage_callback:
                stage_callback(StageEvent(stage_id="S9", label="Persist application and run", event="FAILED",
                                          note="Database save failed; no saved decision claimed"))
            raise PersistenceError("Database save failed. Decision not confirmed; please retry.") from exc
        if stage_callback:
            stage_callback(completed)
        return result.model_copy(update={"persisted": True, "stage_events": stages,
                                         "elapsed_ms": run_record["elapsed_ms"], "finished_at": timestamp})

    def runs_for_application(self, application_id: str) -> list[dict]:
        response = (self.client.table("runs").select("*")
                    .eq("application_id", application_id)
                    .order("started_at", desc=True).execute())
        return response.data

    def review_history(self, application_id: str) -> list[dict]:
        response = (self.client.table("review_actions").select("*")
                    .eq("application_id", application_id)
                    .order("created_at", desc=True).execute())
        return response.data

    def admin_queue(self, status: str = "PENDING") -> list[dict]:
        query = self.client.table("applications").select("id,payload_json,current_status,decision_source,latest_run_id,created_at,updated_at")
        if status != "ALL":
            query = query.eq("current_status", status)
        return query.order("created_at", desc=False).execute().data

    def admin_review(self, application_id: str, action: str, reason: str) -> dict:
        if action not in ("APPROVE", "REQUEST_CORRECTION", "REJECT"):
            raise ValueError("Unknown admin action")
        if len(reason.strip()) < 3:
            raise ValueError("A specific review reason is required.")
        # SQL trigger only permits review actions against PENDING applications.
        try:
            response = self.client.table("review_actions").insert({
                "application_id": application_id, "action": action,
                "reason": reason.strip(), "actor": "demo-admin"
            }).execute()
            if not response.data:
                raise RuntimeError("No review record returned")
            return response.data[0]
        except Exception as exc:
            raise PersistenceError("Admin decision could not be saved. Try again.") from exc


class PersistentVendorService:
    """Vendor-facing boundaries: track only by ID+secret, never enumerate all apps."""
    def __init__(self, repo: SupabaseRepository, extractor: Extractor):
        self.repo = repo
        self.extractor = extractor

    def submit(self, vendor: VendorSubmission, gst_upload: PDFInput | None,
               bank_upload: PDFInput | None, stage_callback: StageCallback | None = None) -> ApplicationReceipt:
        # Validate PDF headers/types/sizes before writing any application record.
        if gst_upload is not None:
            read_pdf(gst_upload)
        if bank_upload is not None:
            read_pdf(bank_upload)
        application_id, token = self.repo.create_application(vendor)
        if gst_upload:
            self.repo.upload_document(application_id, "GST", gst_upload)
        if bank_upload:
            self.repo.upload_document(application_id, "BANK", bank_upload)
        engine = ProcessingPipeline(self.extractor, approved_lookup=self.repo.approved_lookup)
        result = engine.evaluate(vendor, gst_upload, bank_upload, application_id=application_id,
                                 stage_callback=stage_callback, persistence_planned=True)
        result = self.repo.commit_run(result, vendor, stage_callback=stage_callback)
        return ApplicationReceipt(application_id, token, result)

    def track(self, application_id: str, tracking_code: str) -> tuple[dict, list[dict]]:
        record = self.repo.authenticate_vendor(application_id, tracking_code)
        history = self.repo.runs_for_application(application_id)
        return record, history

    def resubmit(self, application_id: str, tracking_code: str, vendor: VendorSubmission,
                 gst_upload: PDFInput | None = None, bank_upload: PDFInput | None = None,
                 stage_callback: StageCallback | None = None) -> WorkflowResult:
        old = self.repo.authenticate_vendor(application_id, tracking_code)
        if old["current_status"] != Status.PENDING.value or not old.get("latest_run_id"):
            raise TerminalApplication("Only completed pending applications can be corrected and resubmitted.")
        if not vendor.legal_name.strip() or not vendor.contact_email.strip():
            raise MinimumIntakeError("Legal name and contact email are required.")
        if gst_upload is not None:
            read_pdf(gst_upload)
        if bank_upload is not None:
            read_pdf(bank_upload)
        if gst_upload:
            self.repo.upload_document(application_id, "GST", gst_upload)
        else:
            gst_upload = self.repo.load_latest_document(application_id, "GST")
        if bank_upload:
            self.repo.upload_document(application_id, "BANK", bank_upload)
        else:
            bank_upload = self.repo.load_latest_document(application_id, "BANK")
        engine = ProcessingPipeline(self.extractor, approved_lookup=self.repo.approved_lookup)
        result = engine.evaluate(vendor, gst_upload, bank_upload, application_id=application_id,
                                 trigger="resubmission", stage_callback=stage_callback,
                                 persistence_planned=True)
        return self.repo.commit_run(result, vendor, stage_callback=stage_callback)
