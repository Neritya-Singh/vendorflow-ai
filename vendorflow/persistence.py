"""Supabase persistence, versioned private PDFs, token tracking, and audit trail.

All calls use a server-only Supabase secret. Never initialize this client in browser code.
The SQL `trg_vendorflow_commit_run` atomically records each immutable run AND updates
current application status. No local SQLite or fake 'saved' flags.
"""
from __future__ import annotations

import hashlib
import re
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


class StaleRevision(PersistenceError):
    """A newer run or reviewer action has superseded the displayed revision."""


@dataclass(frozen=True)
class PreparedIntake:
    application_id: str
    tracking_code: str


def prepare_intake() -> PreparedIntake:
    """Issue recoverable credentials BEFORE the first durable database write.

    The caller must display/save these privately before executing submit().
    Retrying with this same pair is idempotent at the application level.
    """
    return PreparedIntake("VF-" + uuid4().hex[:12].upper(), secrets.token_urlsafe(24))


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

    def create_application(self, vendor: VendorSubmission,
                           prepared: PreparedIntake | None = None) -> tuple[str, str]:
        if not vendor.legal_name.strip() or not vendor.contact_email.strip():
            raise MinimumIntakeError("Legal business name and contact email are required.")
        issued = prepared or prepare_intake()
        application_id, token = issued.application_id, issued.tracking_code
        if not (application_id.startswith("VF-") and len(application_id) == 15 and len(token) >= 20):
            raise PersistenceError("Invalid tracking credentials. Begin a new submission.")
        data = {
            "id": application_id,
            "payload_json": vendor.model_dump(),
            "tracking_token_hash": _token_digest(application_id, token),
            "current_status": "PENDING", "decision_source": "AUTOMATED"
        }
        try:
            response = self.client.table("applications").insert(data).execute()
            if not response.data:
                raise RuntimeError("Application creation was not acknowledged")
        except Exception as exc:
            # Network acknowledgment may be lost AFTER the insert commits. Check
            # ownership using the same secret; never generate another ID on retry.
            try:
                self.authenticate_vendor(application_id, token)
            except UnauthorizedTracking:
                raise PersistenceError(
                    "Application creation could not be confirmed. Retain the ID and tracking code "
                    "and retry with these same credentials."
                ) from exc
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

    # ---- v2 records screening (V2_01 §6). Drafts (zero runs) and the application
    # itself are excluded; every other status counts.
    @staticmethod
    def _v2_record(row: dict) -> dict:
        payload = row.get("payload_json") or {}
        return {"id": row.get("id"), "status": row.get("current_status"),
                "gstin": norm_id(payload.get("gstin")), "legal_name": str(payload.get("legal_name") or ""),
                "account_number": re.sub(r"\s+", "", str(payload.get("account_number") or "")),
                "ifsc": norm_id(payload.get("ifsc"))}

    _V2_COLUMNS = "id,current_status,latest_run_id,gstin_normalized,payload_json"

    def records_by_gstin(self, gstin: str, application_id: str) -> list[dict]:
        rows = (self.client.table("applications").select(self._V2_COLUMNS)
                .eq("gstin_normalized", norm_id(gstin)).neq("id", application_id).execute().data)
        return [self._v2_record(r) for r in rows if r.get("latest_run_id") and r.get("id") != application_id]

    def records_by_bank(self, account_number: str, ifsc: str, application_id: str) -> list[dict]:
        """Prototype scale: filters up to 5,000 submitted applications in process.
        Production would add an expression index on the normalised account + IFSC."""
        account = re.sub(r"\s+", "", account_number or "")
        rows = (self.client.table("applications").select(self._V2_COLUMNS)
                .neq("id", application_id).limit(5000).execute().data)
        records = [self._v2_record(r) for r in rows if r.get("latest_run_id") and r.get("id") != application_id]
        return [r for r in records if r["account_number"] == account and r["ifsc"] == norm_id(ifsc)]

    def _latest_document_row(self, application_id: str, doc_type: str) -> dict | None:
        response = (self.client.table("documents")
                    .select("*")
                    .eq("application_id", application_id)
                    .eq("doc_type", doc_type)
                    .order("version", desc=True)
                    .limit(1).execute())
        return response.data[0] if response.data else None

    def _document_by_id(self, document_id: str) -> dict:
        response = (self.client.table("documents").select("*")
                    .eq("id", document_id).limit(1).execute())
        if not response.data:
            raise PersistenceError("Referenced PDF version is no longer available.")
        return response.data[0]

    @staticmethod
    def _manifest_entry(row: dict) -> dict:
        return {key: row[key] for key in (
            "id", "doc_type", "version", "file_sha256", "storage_path"
        )}

    def upload_document(self, application_id: str, doc_type: str, uploaded: PDFInput) -> dict:
        if doc_type not in ("GST", "BANK"):
            raise ValueError("Unknown PDF document type")
        read_pdf(uploaded)
        old = self._latest_document_row(application_id, doc_type)
        version = int(old["version"]) + 1 if old else 1
        sha = hashlib.sha256(uploaded.content).hexdigest()
        path = f"{application_id}/{doc_type}/v{version}-{uuid4().hex}.pdf"
        stored = False
        try:
            self.client.storage.from_(self.BUCKET).upload(
                path=path,
                file=uploaded.content,
                file_options={"content-type": "application/pdf", "upsert": "false"},
            )
            stored = True
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
            if stored:
                # An insert may have COMMITTED although its acknowledgement was lost.
                # Check for its immutable metadata before compensating storage.
                try:
                    confirmed = (self.client.table("documents").select("*")
                                 .eq("storage_path", path).limit(1).execute().data)
                    if confirmed and confirmed[0]["file_sha256"] == sha:
                        return confirmed[0]
                except Exception:
                    pass
                try:
                    self.client.storage.from_(self.BUCKET).remove([path])
                except Exception:
                    pass
            raise PersistenceError(
                "PDF upload or metadata save failed. No decision was saved. "
                "Use your existing tracking credentials to retry."
            ) from exc

    def _download_verified(self, row: dict) -> PDFInput:
        try:
            content = self.client.storage.from_(self.BUCKET).download(row["storage_path"])
            if not isinstance(content, bytes):
                content = content.content
            if hashlib.sha256(content).hexdigest() != row["file_sha256"]:
                raise PersistenceError("Stored PDF integrity check failed.")
            return PDFInput(row["filename"], content)
        except Exception as exc:
            raise PersistenceError("Could not retrieve a verified stored PDF. No decision was issued.") from exc

    def load_committed_document(self, application_id: str, doc_type: str) -> tuple[PDFInput | None, dict | None]:
        """Only reuse a PDF referenced by the latest COMMITTED run manifest.

        Uploaded metadata not linked to a committed run is STAGED, never active.
        Historical runs retain immutable IDs, versions, paths and checksums.
        """
        app = self._application(application_id)
        run_id = app.get("latest_run_id")
        if not run_id:
            return None, None
        response = (self.client.table("runs").select("id,document_manifest")
                    .eq("id", run_id).eq("application_id", application_id)
                    .limit(1).execute())
        if not response.data:
            raise PersistenceError("Committed workflow evidence could not be located.")
        matches = [d for d in (response.data[0].get("document_manifest") or [])
                   if d.get("doc_type") == doc_type]
        if not matches:
            return None, None
        if len(matches) != 1:
            raise PersistenceError("Committed workflow evidence is inconsistent.")
        entry = matches[0]
        row = self._document_by_id(str(entry["id"]))
        if row["application_id"] != application_id or any(
            row[k] != entry[k] for k in ("doc_type", "version", "file_sha256", "storage_path")
        ):
            raise PersistenceError("Stored PDF version does not match the committed run.")
        return self._download_verified(row), row

    def load_latest_document(self, application_id: str, doc_type: str) -> PDFInput | None:
        """Backward-compatible API name; returns latest COMMITTED, never staged."""
        pdf, _ = self.load_committed_document(application_id, doc_type)
        return pdf

    def load_run_document(self, application_id: str, run_id: str, doc_type: str) -> PDFInput | None:
        """Read specific historical evidence after staff/vendor authorization."""
        resp = (self.client.table("runs").select("id,document_manifest")
                .eq("id", run_id).eq("application_id", application_id).limit(1).execute())
        if not resp.data:
            raise PersistenceError("Requested workflow run does not exist.")
        entries = [d for d in resp.data[0].get("document_manifest") or []
                   if d.get("doc_type") == doc_type]
        if not entries:
            return None
        if len(entries) != 1:
            raise PersistenceError("Historical PDF references are inconsistent.")
        row = self._document_by_id(str(entries[0]["id"]))
        if row["application_id"] != application_id or any(
            row[k] != entries[0][k] for k in ("doc_type", "version", "file_sha256", "storage_path")
        ):
            raise PersistenceError("Historical PDF does not match its recorded version.")
        return self._download_verified(row)

    def saved_result(self, application_id: str) -> WorkflowResult | None:
        """Recover a lost submit response without repeating the workflow."""
        app = self._application(application_id)
        if not app.get("latest_run_id"):
            return None
        response = (self.client.table("runs").select("*")
                    .eq("id", app["latest_run_id"]).limit(1).execute())
        if not response.data:
            raise PersistenceError("Saved workflow run could not be recovered.")
        row = response.data[0]
        return WorkflowResult.model_validate({
            "application_id": application_id, "run_id": row["id"],
            "trigger": row["trigger"], "status": row["status"],
            "reasons": row["reasons_json"], "all_reasons": row["all_reasons_json"],
            "next_action": row["next_action"], "checks": row["checks_json"],
            "extracted": row["extracted_json"], "stage_events": row["stages_json"],
            "started_at": row["started_at"], "finished_at": row["finished_at"],
            "elapsed_ms": row["elapsed_ms"], "persisted": True,
            "extraction_error": row.get("extraction_error", False),
        })

    def commit_run(self, result: WorkflowResult, vendor: VendorSubmission,
                   *, expected_revision: int | None = None,
                   document_manifest: list[dict] | None = None,
                   stage_callback: StageCallback | None = None) -> WorkflowResult:
        """Inserting a run fires an SQL trigger that updates the application atomically."""
        started = StageEvent(stage_id="S9", label="Persist application and run", event="STARTED")
        if stage_callback:
            stage_callback(started)
        completed = StageEvent(stage_id="S9", label="Persist application and run", event="COMPLETED",
                               note="Run, decision and application status saved")
        stages = [e for e in result.stage_events if e.stage_id != "S9"] + [started, completed]
        timestamp = datetime.now(timezone.utc)
        if expected_revision is None:
            expected_revision = int(self._application(result.application_id).get("revision", 0))
        run_record = {
            "expected_revision": expected_revision,
            "document_manifest": document_manifest or [],
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
            raise PersistenceError(
                "Database save was not acknowledged or the application changed. "
                "Check tracking with the existing ID and code before retrying."
            ) from exc
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
        query = self.client.table("applications").select("id,payload_json,current_status,decision_source,latest_run_id,revision,created_at,updated_at")
        if status != "ALL":
            query = query.eq("current_status", status)
        return query.order("created_at", desc=False).execute().data

    def admin_review(self, application_id: str, action: str, reason: str,
                     *, expected_latest_run_id: str | None = None,
                     expected_revision: int | None = None) -> dict:
        if action not in ("APPROVE", "REQUEST_CORRECTION", "REJECT"):
            raise ValueError("Unknown admin action")
        if len(reason.strip()) < 3:
            raise ValueError("A specific review reason is required.")
        app = self._application(application_id)
        reviewed_run_id = app.get("latest_run_id")
        if not reviewed_run_id or app.get("current_status") != "PENDING":
            raise TerminalApplication("Only completed pending applications can be reviewed.")
        if expected_latest_run_id is not None and expected_latest_run_id != reviewed_run_id:
            raise StaleRevision("This application changed. Refresh before reviewing it.")
        observed_revision = int(app.get("revision", 0))
        if expected_revision is not None and expected_revision != observed_revision:
            raise StaleRevision("This application changed. Refresh before reviewing it.")
        try:
            response = self.client.table("review_actions").insert({
                "application_id": application_id, "action": action,
                "reason": reason.strip(), "actor": "demo-admin",
                "reviewed_run_id": reviewed_run_id,
                "expected_revision": observed_revision,
            }).execute()
            if not response.data:
                raise RuntimeError("No review record returned")
            return response.data[0]
        except Exception as exc:
            raise PersistenceError(
                "Admin decision was not saved. The case may have changed or a "
                "conflicting approved identity exists. Refresh before retrying."
            ) from exc


class PersistentVendorService:
    """Vendor-facing boundaries: track only by ID+secret, never enumerate all apps."""
    def __init__(self, repo: SupabaseRepository, extractor: Extractor, *,
                 pipeline_options: dict | None = None):
        """`pipeline_options` passes optional v2 hooks (screening, name_key) to
        ProcessingPipeline; omitted, the v1.1 behaviour is unchanged."""
        self.repo = repo
        self.extractor = extractor
        self.pipeline_options = dict(pipeline_options or {})

    def submit(self, vendor: VendorSubmission, gst_upload: PDFInput | None,
               bank_upload: PDFInput | None, stage_callback: StageCallback | None = None,
               *, prepared: PreparedIntake | None = None) -> ApplicationReceipt:
        if gst_upload is not None:
            read_pdf(gst_upload)
        if bank_upload is not None:
            read_pdf(bank_upload)
        application_id, token = self.repo.create_application(vendor, prepared=prepared)
        # A lost HTTP/Streamlit acknowledgement is not a reason to create another
        # application. Return the previously committed receipt, unchanged.
        already_saved = self.repo.saved_result(application_id)
        if already_saved is not None:
            return ApplicationReceipt(application_id, token, already_saved)
        manifest: list[dict] = []
        if gst_upload:
            manifest.append(self.repo._manifest_entry(self.repo.upload_document(application_id, "GST", gst_upload)))
        if bank_upload:
            manifest.append(self.repo._manifest_entry(self.repo.upload_document(application_id, "BANK", bank_upload)))
        engine = ProcessingPipeline(self.extractor, approved_lookup=self.repo.approved_lookup,
                                    **self.pipeline_options)
        result = engine.evaluate(vendor, gst_upload, bank_upload, application_id=application_id,
                                 stage_callback=stage_callback, persistence_planned=True)
        try:
            result = self.repo.commit_run(result, vendor, expected_revision=0,
                                          document_manifest=manifest, stage_callback=stage_callback)
        except PersistenceError:
            # When DB committed but network lost the reply, recover the run.
            saved = self.repo.saved_result(application_id)
            if saved is None:
                raise
            result = saved
        return ApplicationReceipt(application_id, token, result)

    def resume_submission(self, application_id: str, tracking_code: str,
                          vendor: VendorSubmission, gst_upload: PDFInput | None = None,
                          bank_upload: PDFInput | None = None,
                          stage_callback: StageCallback | None = None) -> ApplicationReceipt:
        """Explicit recovery path for a session/browser restart during first save."""
        self.repo.authenticate_vendor(application_id, tracking_code)
        return self.submit(vendor, gst_upload, bank_upload, stage_callback,
                           prepared=PreparedIntake(application_id, tracking_code))

    def track(self, application_id: str, tracking_code: str) -> tuple[dict, list[dict]]:
        record = self.repo.authenticate_vendor(application_id, tracking_code)
        history = self.repo.runs_for_application(application_id)
        return record, history

    def resubmit(self, application_id: str, tracking_code: str, vendor: VendorSubmission,
                 gst_upload: PDFInput | None = None, bank_upload: PDFInput | None = None,
                 stage_callback: StageCallback | None = None,
                 *, expected_latest_run_id: str | None = None,
                 expected_revision: int | None = None) -> WorkflowResult:
        old = self.repo.authenticate_vendor(application_id, tracking_code)
        if old["current_status"] != Status.PENDING.value or not old.get("latest_run_id"):
            raise TerminalApplication("Only completed pending applications can be corrected and resubmitted.")
        if expected_latest_run_id is not None and old["latest_run_id"] != expected_latest_run_id:
            raise StaleRevision("A newer revision exists. Refresh your application before resubmitting.")
        revision = int(old.get("revision", 0))
        if expected_revision is not None and revision != expected_revision:
            raise StaleRevision("A newer revision exists. Refresh your application before resubmitting.")
        if not vendor.legal_name.strip() or not vendor.contact_email.strip():
            raise MinimumIntakeError("Legal name and contact email are required.")
        if gst_upload is not None:
            read_pdf(gst_upload)
        if bank_upload is not None:
            read_pdf(bank_upload)
        manifest = []
        if gst_upload:
            gst_row = self.repo.upload_document(application_id, "GST", gst_upload)
        else:
            gst_upload, gst_row = self.repo.load_committed_document(application_id, "GST")
        if gst_row:
            manifest.append(self.repo._manifest_entry(gst_row))
        if bank_upload:
            bank_row = self.repo.upload_document(application_id, "BANK", bank_upload)
        else:
            bank_upload, bank_row = self.repo.load_committed_document(application_id, "BANK")
        if bank_row:
            manifest.append(self.repo._manifest_entry(bank_row))
        engine = ProcessingPipeline(self.extractor, approved_lookup=self.repo.approved_lookup,
                                    **self.pipeline_options)
        result = engine.evaluate(vendor, gst_upload, bank_upload, application_id=application_id,
                                 trigger="resubmission", stage_callback=stage_callback,
                                 persistence_planned=True)
        try:
            return self.repo.commit_run(result, vendor, expected_revision=revision,
                                        document_manifest=manifest, stage_callback=stage_callback)
        except PersistenceError:
            # A saved revision may be committed even when the HTTP response is lost.
            # Recover ONLY our own exact run; never misreport a competing submission.
            latest = self.repo.saved_result(application_id)
            if latest is not None and latest.run_id == result.run_id:
                return latest
            raise
