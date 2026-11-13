"""VendorFlow AI v2 — thin FastAPI adapter over the v1.1 Python services.

Run:  uvicorn backend.main:app --port 8000
Serves /api/* and (when built) the React app from frontend/dist with SPA fallback.
"""
from __future__ import annotations

import json
import logging
import os
import queue
import re
import secrets
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Literal

import pymupdf
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from vendorflow import v2_policy as v2
from vendorflow.gemini_extractor import safe_model_name
from vendorflow.models import StageEvent, VendorSubmission
from vendorflow.pdf_reader import MAX_PDF_BYTES, PDFInput, UploadError, read_pdf
from vendorflow.persistence import (
    PersistenceError, PreparedIntake, StaleRevision, TerminalApplication, UnauthorizedTracking,
    parallel, prepare_intake,
)
from vendorflow.pipeline import MinimumIntakeError
from vendorflow.rules import GST_STATE_CODES, normalize_submission
from vendorflow.ux_support import committed_pdf_types
from vendorflow.v2_scan import content_type as doc_content_type, file_kind, strip_metadata
from vendorflow.v2_intake import DraftInvalid, DraftLimit, DraftSubmitted, V2Submission, draft_view, fix_view

from . import presenters
from .config import Settings, load_settings
from .security import (
    COOKIE_NAME, LoginThrottle, SlidingWindowLimiter, client_key, issue_session, read_session,
    require_admin, require_admin_csrf,
)
from .services import ServiceProvider

log = logging.getLogger("vendorflow.api")
APP_ID = re.compile(r"^VF-[0-9A-F]{12}$")
TOKEN = re.compile(r"^[A-Za-z0-9_-]{20,64}$")
RUN_ID = re.compile(r"^RUN-[0-9A-F]{12}$")
MAX_REQUEST_BYTES = 2 * MAX_PDF_BYTES + 512 * 1024
MAX_PREVIEW_PAGES = 10
PDF_MIME = {"application/pdf", "application/x-pdf"}
DOC_MIME = PDF_MIME | {"image/jpeg", "image/png"}


class Credentials(BaseModel):
    application_id: str = Field(max_length=32)
    tracking_code: str = Field(max_length=80)


class DraftValues(Credentials):
    changes: dict[str, str] = Field(default_factory=dict, max_length=12)
    reset: list[str] = Field(default_factory=list, max_length=12)
    contact: dict[str, str] | None = None
    declaration: bool | None = None


class DraftSlot(Credentials):
    slot: Literal["GST", "BANK"]


class DraftSubmit(Credentials):
    declaration: bool = False


class Login(BaseModel):
    password: str = Field(max_length=256)


class Review(BaseModel):
    action: Literal["APPROVE", "REJECT", "REQUEST_CORRECTION"]
    reason: str = Field(min_length=3, max_length=1000)
    confirmation: str | None = Field(default=None, max_length=200)
    # REQUEST_CORRECTION only: what the vendor must change (v2.FIX_ITEM_IDS).
    items: list[str] = Field(default_factory=list, max_length=len(v2.FIX_ITEM_IDS))
    expected_revision: int
    expected_latest_run_id: str



def create_app(settings: Settings | None = None, provider: ServiceProvider | None = None) -> FastAPI:
    settings = settings or load_settings()
    provider = provider or ServiceProvider(settings)
    app = FastAPI(title="VendorFlow AI v2 API", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.provider = provider
    app.state.trust_proxy = os.getenv("TRUST_PROXY", "").strip() == "1"
    admin_throttle = LoginThrottle()
    vendor_limiter = SlidingWindowLimiter(limit=10, window_seconds=15 * 60)
    # Each upload/move can cost one provider call: bound them per client (B5).
    reading_limiter = SlidingWindowLimiter(limit=40, window_seconds=15 * 60)

    # ------------------------------------------------------------ middleware
    @app.middleware("http")
    async def guard(request: Request, call_next):
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > MAX_REQUEST_BYTES:
            return JSONResponse({"detail": "Upload too large. Each PDF must be 5 MB or less."}, status_code=413)
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        else:
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                "font-src 'self' data:; object-src 'none'; frame-src 'self'; frame-ancestors 'none'; "
                "base-uri 'self'; form-action 'self'")
        return response

    # ------------------------------------------------------------ helpers
    def safe_error(exc: Exception) -> tuple[int, str, str]:
        if isinstance(exc, DraftSubmitted):
            return 409, "SUBMITTED", str(exc)
        if isinstance(exc, DraftLimit):
            return 429, "LIMIT", str(exc)
        if isinstance(exc, DraftInvalid):
            return 400, "INVALID", str(exc)
        if isinstance(exc, UnauthorizedTracking):
            return 401, "UNAUTHORIZED", "Application ID or tracking code is incorrect."
        if isinstance(exc, TerminalApplication):
            return 409, "TERMINAL", "This application has a final decision and can no longer be changed."
        if isinstance(exc, StaleRevision):
            return 409, "STALE", str(exc)
        if isinstance(exc, PersistenceError):
            return 503, "PERSISTENCE", str(exc)  # messages are written to be safe for display
        if isinstance(exc, (MinimumIntakeError, UploadError)):
            return 400, "INVALID", str(exc)
        log.error("Unexpected %s during request", type(exc).__name__)  # type only; no payload/secrets
        return 500, "UNEXPECTED", "The operation could not be completed. Please retry shortly."

    def fail(exc: Exception) -> HTTPException:
        status, _kind, message = safe_error(exc)
        return HTTPException(status_code=status, detail=message)

    async def read_upload(upload: UploadFile | None, label: str, *, images: bool = False) -> PDFInput | None:
        if upload is None or not (upload.filename or "").strip():
            return None
        name = upload.filename.replace("\\", "/").rsplit("/", 1)[-1][:120]
        if images:  # v2 B7 draft/fix uploads: PDF (text or scanned), JPG or PNG
            if (upload.content_type or "").split(";")[0].strip().lower() not in DOC_MIME:
                raise HTTPException(400, f"{label}: upload a PDF, JPG or PNG file.")
            content = await upload.read(MAX_PDF_BYTES + 1)
            if len(content) > MAX_PDF_BYTES:
                raise HTTPException(413, f"{label}: the file exceeds 5 MB. Upload a smaller file.")
            try:
                # Strip EXIF/GPS here so the reading, the hash and the stored original agree.
                content = strip_metadata(file_kind(name, content), content)
            except UploadError as exc:
                raise HTTPException(400, f"{label}: {exc}") from None
            return PDFInput(name, content)
        if not name.casefold().endswith(".pdf"):
            raise HTTPException(400, f"{label}: only .pdf files are accepted.")
        if (upload.content_type or "").split(";")[0].strip().lower() not in PDF_MIME:
            raise HTTPException(400, f"{label}: the file must be a PDF (application/pdf).")
        content = await upload.read(MAX_PDF_BYTES + 1)
        if len(content) > MAX_PDF_BYTES:
            raise HTTPException(413, f"{label}: the PDF exceeds 5 MB. Upload a smaller file.")
        pdf = PDFInput(name, content)
        try:
            read_pdf(pdf)  # magic bytes, empty file and size are checked by the v1.1 reader
        except UploadError as exc:
            raise HTTPException(400, f"{label}: {exc}") from None
        return pdf

    def check_credentials(application_id: str, tracking_code: str) -> None:
        if not APP_ID.fullmatch(application_id or "") or not TOKEN.fullmatch(tracking_code or ""):
            raise HTTPException(401, "Application ID or tracking code is incorrect.")

    def vendor_auth(request: Request, application_id: str, tracking_code: str) -> dict:
        key = client_key(request)
        if vendor_limiter.blocked(key):
            raise HTTPException(429, "Too many unsuccessful attempts. Wait 15 minutes and try again.")
        try:
            check_credentials(application_id, tracking_code)
            return provider.repo().authenticate_vendor(application_id, tracking_code)
        except (HTTPException, UnauthorizedTracking) as exc:
            vendor_limiter.hit(key)
            if isinstance(exc, HTTPException):
                raise
            raise fail(exc) from None
        except Exception as exc:
            raise fail(exc) from None

    def stream(work: Callable[[Callable[[StageEvent], None]], dict]) -> StreamingResponse:
        """Run the real pipeline in a worker thread; forward each REAL stage callback.

        The worker finishes and commits even if the browser disconnects, so the
        vendor can always recover the saved outcome with their tracking code.
        """
        events: queue.Queue = queue.Queue()

        def callback(event: StageEvent | dict) -> None:
            if isinstance(event, dict):  # a vendor-safe view to show before the result
                events.put({"type": "preview", "data": event})
                return
            # Vendor stream: real stage IDs, states and times only. Internal notes
            # (provider diagnostics, screening outcomes) stay in the saved run for staff.
            events.put({"type": "stage", **event.model_dump(mode="json"), "note": "",
                        "label": presenters.VENDOR_STAGES.get(event.stage_id)
                        or presenters.READING_STAGES.get(event.stage_id, "")})

        def worker() -> None:
            try:
                events.put({"type": "result", "data": work(callback)})
            except Exception as exc:  # noqa: BLE001 - mapped to safe messages
                status, kind, message = safe_error(exc)
                events.put({"type": "error", "status": status, "kind": kind, "message": message})
            finally:
                events.put(None)

        threading.Thread(target=worker, name="vf-evaluation", daemon=True).start()

        def body():
            yield json.dumps({"type": "accepted", "at": datetime.now(timezone.utc).isoformat()}) + "\n"
            while True:
                try:
                    item = events.get(timeout=10)
                except queue.Empty:
                    yield json.dumps({"type": "heartbeat"}) + "\n"
                    continue
                if item is None:
                    return
                yield json.dumps(item) + "\n"

        return StreamingResponse(body(), media_type="application/x-ndjson",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    def vendor_from_form(**fields: str) -> VendorSubmission:
        return VendorSubmission(**{k: (v or "")[:200] for k, v in fields.items()})

    # ------------------------------------------------------------ public meta
    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "mode": "offline" if settings.offline_mode else "live",
            "gemini_configured": settings.gemini_configured,
            "supabase_configured": settings.supabase_configured,
            "admin_configured": bool(settings.admin_password),
            "extractor": ("offline-label-test-double"
                          if settings.offline_mode and settings.offline_extractor != "gemini"
                          else safe_model_name(os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"))),
        }

    @app.get("/api/meta")
    def meta():
        return {"states": sorted(s.title().replace(" And ", " and ") for s in GST_STATE_CODES),
                "max_pdf_bytes": MAX_PDF_BYTES, "workspace_name": settings.workspace_name,
                "stages": [{"stage_id": s, "label": presenters.VENDOR_STAGES[s]} for s, _ in presenters.STAGES]}

    # ------------------------------------------------------------ vendor
    @app.post("/api/vendor/intake")
    def new_intake():
        """Issue credentials BEFORE any durable write (v1.1 recovery contract).

        Nothing is stored. The pair is only bound to an application on submit.
        """
        issued = prepare_intake()
        return {"application_id": issued.application_id, "tracking_code": issued.tracking_code}

    @app.post("/api/vendor/applications")
    async def submit_application(
        request: Request,
        application_id: str = Form(...), tracking_code: str = Form(...),
        legal_name: str = Form(""), business_state: str = Form(""), contact_name: str = Form(""),
        contact_email: str = Form(""), pan: str = Form(""), gstin: str = Form(""),
        bank_holder: str = Form(""), account_number: str = Form(""), ifsc: str = Form(""),
        gst_pdf: UploadFile | None = File(None), bank_pdf: UploadFile | None = File(None),
    ):
        check_credentials(application_id, tracking_code)
        vendor = vendor_from_form(legal_name=legal_name, business_state=business_state,
                                  contact_name=contact_name, contact_email=contact_email, pan=pan,
                                  gstin=gstin, bank_holder=bank_holder, account_number=account_number,
                                  ifsc=ifsc)
        if not vendor.legal_name.strip() or not vendor.contact_email.strip():
            raise HTTPException(400, "Legal business name and contact email are needed to create an application.")
        gst = await read_upload(gst_pdf, "GST certificate")
        bank = await read_upload(bank_pdf, "Bank proof")
        try:
            repo = provider.repo()
            exists = bool(repo.client.table("applications").select("id")
                          .eq("id", application_id).limit(1).execute().data)
        except Exception as exc:
            raise fail(exc) from None
        if exists:
            # Retry/resume of the SAME application: possession of its code is required.
            vendor_auth(request, application_id, tracking_code)
        service = provider.service()

        def work(callback):
            receipt = service.submit(vendor, gst, bank, stage_callback=callback,
                                     prepared=PreparedIntake(application_id, tracking_code))
            saved = service.repo.runs_for_application(application_id)
            manifest = next((r.get("document_manifest") or [] for r in saved
                             if r.get("id") == receipt.result.run_id), [])
            return presenters.receipt_view(application_id, receipt.result, vendor.model_dump(), manifest,
                                           buyer=settings.workspace_name)

        return stream(work)

    @app.post("/api/vendor/track")
    def track(request: Request, body: Credentials):
        application_id = body.application_id.strip().upper()
        record = vendor_auth(request, application_id, body.tracking_code.strip())
        try:
            repo = provider.repo()
            runs, reviews = parallel(lambda: repo.runs_for_application(application_id),
                                     lambda: repo.review_history(application_id))
        except Exception as exc:
            raise fail(exc) from None
        return presenters.vendor_view(record, runs, reviews, buyer=settings.workspace_name)

    @app.post("/api/vendor/resubmit")
    async def resubmit(
        request: Request,
        application_id: str = Form(...), tracking_code: str = Form(...),
        expected_revision: int = Form(...), expected_latest_run_id: str = Form(...),
        legal_name: str = Form(""), business_state: str = Form(""), contact_name: str = Form(""),
        contact_email: str = Form(""), pan: str = Form(""), gstin: str = Form(""),
        bank_holder: str = Form(""), account_number: str = Form(""), ifsc: str = Form(""),
        gst_pdf: UploadFile | None = File(None), bank_pdf: UploadFile | None = File(None),
    ):
        record = vendor_auth(request, application_id, tracking_code)
        if record.get("current_status") != "PENDING" or not record.get("latest_run_id"):
            raise HTTPException(409, "This application has a final decision and can no longer be changed.")
        if not RUN_ID.fullmatch(expected_latest_run_id or "") or expected_latest_run_id != record.get("latest_run_id") \
                or expected_revision != int(record.get("revision") or 0):
            raise HTTPException(409, "A newer revision exists. Refresh your application before resubmitting.")
        vendor = vendor_from_form(legal_name=legal_name, business_state=business_state,
                                  contact_name=contact_name, contact_email=contact_email, pan=pan,
                                  gstin=gstin, bank_holder=bank_holder, account_number=account_number,
                                  ifsc=ifsc)
        if not vendor.legal_name.strip() or not vendor.contact_email.strip():
            raise HTTPException(400, "Legal name and contact email are required.")
        gst = await read_upload(gst_pdf, "GST certificate")
        bank = await read_upload(bank_pdf, "Bank proof")
        # Ownership is enforced server-side: a case "with our team" cannot be edited by
        # the vendor. The only exception is an unchanged retry after a processing outage.
        try:
            repo = provider.repo()
            runs = repo.runs_for_application(application_id)
            reviews = repo.review_history(application_id)
        except Exception as exc:
            raise fail(exc) from None
        latest_run = runs[0] if runs else None
        owner = v2.case_owner(record, latest_run, reviews[0] if reviews else None)
        if owner != v2.VENDOR:
            saved = VendorSubmission(**(record.get("payload_json") or {}))
            unchanged = (gst is None and bank is None
                         and normalize_submission(vendor) == normalize_submission(saved))
            if not (v2.extraction_outage(latest_run) and unchanged):
                raise HTTPException(409, "Your application is with our team. No changes are needed from you right now.")
        saved_payload = record.get("payload_json") or {}
        if saved_payload.get("intake") == "upload_first":
            vendor = V2Submission(**vendor.model_dump(), contact_phone=str(saved_payload.get("contact_phone") or ""),
                                  address=str(saved_payload.get("address") or ""),
                                  declaration=bool(saved_payload.get("declaration")),
                                  declared_at=str(saved_payload.get("declared_at") or ""))
        service = provider.service()

        def work(callback):
            service.resubmit(application_id, tracking_code, vendor, gst_upload=gst, bank_upload=bank,
                             stage_callback=callback, expected_revision=expected_revision,
                             expected_latest_run_id=expected_latest_run_id)
            fresh, runs = service.track(application_id, tracking_code)
            return presenters.vendor_view(fresh, runs, service.repo.review_history(application_id),
                                          buyer=settings.workspace_name)

        return stream(work)

    # ------------------------------------------------------------ vendor drafts (B5)
    # Upload-first intake. The ID + tracking code from /api/vendor/intake identify the
    # draft; the first upload creates it. Every call re-checks the code server-side.

    def draft_auth(request: Request, application_id: str, tracking_code: str, *, create: bool = False) -> dict:
        """The authenticated application row (one round trip), or a new draft row when
        `create` and none exists yet. The callers reuse the row instead of reading it again."""
        application_id = (application_id or "").strip().upper()
        check_credentials(application_id, tracking_code)
        key = client_key(request)
        if vendor_limiter.blocked(key):
            raise HTTPException(429, "Too many unsuccessful attempts. Wait 15 minutes and try again.")
        try:
            record = provider.repo().find_application(application_id)
        except Exception as exc:
            raise fail(exc) from None
        if record is None and create:
            try:
                return provider.drafts().create_draft(application_id, tracking_code)
            except Exception as exc:
                raise fail(exc) from None
        try:
            if record is None:
                raise UnauthorizedTracking("Application ID or tracking code is incorrect.")
            return provider.repo().check_tracking(record, application_id, tracking_code)
        except UnauthorizedTracking as exc:
            vendor_limiter.hit(key)  # counts as a failed lookup
            raise fail(exc) from None

    def reading_budget(request: Request) -> None:
        key = client_key(request)
        if reading_limiter.blocked(key):
            raise HTTPException(429, "Too many uploads in a short time. Wait a few minutes and try again.")
        reading_limiter.hit(key)

    def drafts_view(application_id: str, draft: dict) -> dict:
        return draft_view(application_id, draft, buyer=settings.workspace_name)

    @app.post("/api/vendor/draft")
    def open_draft(request: Request, body: Credentials):
        application_id = body.application_id.strip().upper()
        app_row = draft_auth(request, application_id, body.tracking_code.strip())
        try:
            return drafts_view(application_id, provider.drafts().draft(application_id, app_row))
        except Exception as exc:
            raise fail(exc) from None

    @app.post("/api/vendor/draft/files")
    async def upload_draft_file(
        request: Request, application_id: str = Form(...), tracking_code: str = Form(...),
        slot: Literal["GST", "BANK"] = Form(...), file: UploadFile = File(...),
    ):
        application_id = application_id.strip().upper()
        pdf = await read_upload(file, "GST certificate" if slot == "GST" else "Bank document", images=True)
        if pdf is None:
            raise HTTPException(400, "Choose a file to upload.")
        app_row = draft_auth(request, application_id, tracking_code, create=True)
        reading_budget(request)
        service = provider.drafts()
        return stream(lambda callback: drafts_view(application_id, service.add_file(
            application_id, slot, pdf, callback, app=app_row)))

    @app.post("/api/vendor/draft/move")
    def move_draft_file(request: Request, body: DraftSlot):
        application_id = body.application_id.strip().upper()
        app_row = draft_auth(request, application_id, body.tracking_code.strip())
        reading_budget(request)
        service = provider.drafts()
        # The swapped view arrives as a preview at once; the result follows once the
        # moved files' evidence copies are saved (Continue waits for that).
        return stream(lambda callback: drafts_view(application_id, service.move_file(
            application_id, body.slot, callback, app=app_row,
            on_swapped=lambda d: callback(drafts_view(application_id, d)))))

    @app.post("/api/vendor/draft/remove")
    def remove_draft_file(request: Request, body: DraftSlot):
        application_id = body.application_id.strip().upper()
        app_row = draft_auth(request, application_id, body.tracking_code.strip())
        try:
            return drafts_view(application_id, provider.drafts().remove_file(application_id, body.slot, app=app_row))
        except Exception as exc:
            raise fail(exc) from None

    @app.put("/api/vendor/draft/values")
    def save_draft_values(request: Request, body: DraftValues):
        application_id = body.application_id.strip().upper()
        app_row = draft_auth(request, application_id, body.tracking_code.strip())
        try:
            draft = provider.drafts().save_values(application_id, changes=body.changes, reset=body.reset,
                                                  contact=body.contact, declaration=body.declaration, app=app_row)
            return drafts_view(application_id, draft)
        except Exception as exc:
            raise fail(exc) from None

    @app.post("/api/vendor/draft/submit")
    def submit_draft(request: Request, body: DraftSubmit):
        application_id = body.application_id.strip().upper()
        tracking_code = body.tracking_code.strip()
        app_row = draft_auth(request, application_id, tracking_code)
        service = provider.drafts()
        if not body.declaration and not app_row.get("latest_run_id"):
            raise fail(DraftInvalid("Confirm that these details are correct and belong to your business."))

        def work(callback):
            # The declaration is recorded with the run itself (its payload), not by a
            # separate draft write first; an already-submitted case returns its saved result.
            evidence: dict = {}
            result = service.submit(application_id, callback, app=app_row, declaration=body.declaration,
                                    evidence=evidence)
            if evidence:
                payload, manifest = evidence["payload"], evidence["manifest"]
            else:
                saved = service.repo.runs_for_application(application_id)
                run = next((r for r in saved if r.get("id") == result.run_id), {})
                payload, manifest = run.get("payload_json") or {}, run.get("document_manifest") or []
            return presenters.receipt_view(application_id, result, payload, manifest, buyer=settings.workspace_name)

        return stream(work)

    # ------------------------------------------------------------ vendor fixes (B7 part 1)
    # After a submit, a case "waiting on you" is fixed item by item: an upload slot for a
    # requested document, the field for a requested value. Same reading, same cache.

    def fix_auth(request: Request, application_id: str, tracking_code: str) -> tuple[str, tuple]:
        """(application ID, fix context). The context (application row, latest run, latest
        review) is loaded once here and reused; every write is still compare-and-swap guarded."""
        application_id = (application_id or "").strip().upper()
        check_credentials(application_id, tracking_code)
        record = vendor_auth(request, application_id, tracking_code)
        try:  # only a pending case waiting on the vendor can be fixed (checked again on write)
            return application_id, provider.drafts()._fix_context(application_id, app=record)
        except Exception as exc:
            raise fail(exc) from None

    def fixes_view(application_id: str, fix: dict, ctx: tuple) -> dict:
        return fix_view(application_id, fix, v2.fix_items(ctx[1], ctx[2]), buyer=settings.workspace_name)

    @app.post("/api/vendor/fix")
    def open_fix(request: Request, body: Credentials):
        application_id, ctx = fix_auth(request, body.application_id, body.tracking_code.strip())
        try:
            fix, items = provider.drafts().fix(application_id, ctx=ctx)
            return fix_view(application_id, fix, items, buyer=settings.workspace_name)
        except Exception as exc:
            raise fail(exc) from None

    @app.post("/api/vendor/fix/files")
    async def upload_fix_file(
        request: Request, application_id: str = Form(...), tracking_code: str = Form(...),
        slot: Literal["GST", "BANK"] = Form(...), file: UploadFile = File(...),
    ):
        pdf = await read_upload(file, "GST certificate" if slot == "GST" else "Bank document", images=True)
        if pdf is None:
            raise HTTPException(400, "Choose a file to upload.")
        application_id, ctx = fix_auth(request, application_id, tracking_code)
        reading_budget(request)
        service = provider.drafts()
        return stream(lambda callback: fixes_view(
            application_id, service.add_file(application_id, slot, pdf, callback, kind="fix", ctx=ctx), ctx))

    @app.post("/api/vendor/fix/move")
    def move_fix_file(request: Request, body: DraftSlot):
        application_id, ctx = fix_auth(request, body.application_id, body.tracking_code.strip())
        reading_budget(request)
        service = provider.drafts()
        return stream(lambda callback: fixes_view(
            application_id, service.move_file(application_id, body.slot, callback, kind="fix", ctx=ctx,
                                              on_swapped=lambda d: callback(fixes_view(application_id, d, ctx))), ctx))

    @app.put("/api/vendor/fix/values")
    def save_fix_values(request: Request, body: DraftValues):
        application_id, ctx = fix_auth(request, body.application_id, body.tracking_code.strip())
        try:
            fix = provider.drafts().save_values(application_id, changes=body.changes, reset=body.reset,
                                                contact=body.contact, kind="fix", ctx=ctx)
            return fixes_view(application_id, fix, ctx)
        except Exception as exc:
            raise fail(exc) from None

    @app.post("/api/vendor/fix/submit")
    def submit_fix(request: Request, body: Credentials):
        application_id, ctx = fix_auth(request, body.application_id, body.tracking_code.strip())
        service = provider.drafts()
        try:
            fix, items = service.fix(application_id, ctx=ctx)  # refuses final / with-our-team cases up front
            blockers = fix_view(application_id, fix, items)["blockers"]
            if blockers:
                raise DraftInvalid(blockers[0])
        except Exception as exc:
            raise fail(exc) from None

        def work(callback):
            service.submit_fix(application_id, callback, ctx=ctx)
            repo = service.repo
            fresh, runs, reviews = parallel(lambda: repo._application(application_id),
                                            lambda: repo.runs_for_application(application_id),
                                            lambda: repo.review_history(application_id))
            return presenters.vendor_view(fresh, runs, reviews, buyer=settings.workspace_name)

        return stream(work)

    # ------------------------------------------------------------ admin auth
    @app.post("/api/admin/session")
    def admin_login(request: Request, body: Login):
        if not settings.admin_password:
            raise HTTPException(503, "Administrator access is not configured on this server.")
        key = client_key(request)
        wait = admin_throttle.locked_for(key)
        if wait:
            raise HTTPException(429, f"Too many failed sign-in attempts. Try again in about {(wait + 59) // 60} minute(s).")
        if not secrets.compare_digest(body.password.encode(), settings.admin_password.encode()):
            locked = admin_throttle.failure(key)
            if locked:
                raise HTTPException(429, "Too many failed sign-in attempts. Sign-in is locked for 15 minutes.")
            raise HTTPException(401, "Incorrect administrator password.")
        admin_throttle.success(key)
        cookie, csrf = issue_session(settings)
        response = JSONResponse({"authenticated": True, "csrf_token": csrf})
        response.set_cookie(COOKIE_NAME, cookie, max_age=settings.session_hours * 3600, httponly=True,
                            secure=settings.cookie_secure, samesite="strict", path="/api")
        return response

    @app.get("/api/admin/session")
    def admin_session(request: Request):
        session = read_session(settings, request.cookies.get(COOKIE_NAME))
        if not session:
            return {"authenticated": False, "configured": bool(settings.admin_password)}
        return {"authenticated": True, "csrf_token": session["csrf"], "configured": True}

    @app.delete("/api/admin/session")
    def admin_logout(_session: dict = Depends(require_admin_csrf)):
        response = JSONResponse({"authenticated": False})
        response.delete_cookie(COOKIE_NAME, path="/api", secure=settings.cookie_secure,
                               httponly=True, samesite="strict")
        return response

    # ------------------------------------------------------------ admin data
    def valid_app_id(application_id: str) -> str:
        if not APP_ID.fullmatch(application_id):
            raise HTTPException(404, "Application not found.")
        return application_id

    @app.get("/api/admin/overview")
    def admin_overview(_session: dict = Depends(require_admin)):
        try:
            repo = provider.repo()
            apps = repo.admin_queue("ALL")
            run_rows = (repo.client.table("runs")
                        .select("id,application_id,trigger,status,checks_json,reasons_json,elapsed_ms,created_at,"
                                "finished_at,extraction_error,document_manifest")
                        .limit(1000).execute().data)
            review_rows = (repo.client.table("review_actions")
                           .select("application_id,action,reason,actor,created_at,reviewed_run_id")
                           .order("created_at", desc=True).limit(1000).execute().data)
        except Exception as exc:
            raise fail(exc) from None
        view = presenters.admin_overview(apps, run_rows, review_rows)
        names = {a.get("id"): (a.get("payload_json") or {}).get("legal_name", "") for a in apps}
        view["recent_actions"] = [{**presenters._review_dict(r), "application_id": r.get("application_id"),
                                   "business": names.get(r.get("application_id"), "")}
                                  for r in review_rows[:100]]
        return view

    def load_case(application_id: str):
        repo = provider.repo()
        rows, runs, reviews = parallel(
            lambda: repo.client.table("applications").select("*").eq("id", application_id).limit(1).execute().data,
            lambda: repo.runs_for_application(application_id),
            lambda: repo.review_history(application_id))
        if not rows:
            raise HTTPException(404, "Application not found.")
        app_row = rows[0]
        app_row.pop("tracking_token_hash", None)
        return repo, app_row, runs, reviews

    def linked_rows(repo, runs: list[dict]) -> list[dict]:
        """Applications named by the latest run's R12/R15 evidence (staff only)."""
        found = []
        for case_id in v2.linked_case_ids(runs[0] if runs else None)[:5]:
            rows = (repo.client.table("applications").select("id,current_status,payload_json,latest_run_id")
                    .eq("id", case_id).limit(1).execute().data)
            if rows and rows[0].get("latest_run_id"):
                other_runs = repo.runs_for_application(case_id)
                latest = next((r for r in other_runs if r.get("id") == rows[0]["latest_run_id"]), None)
                rows[0]["_documents"] = committed_pdf_types(latest)
                found.append(rows[0])
        return found

    @app.get("/api/admin/applications/{application_id}")
    def admin_case(application_id: str, _session: dict = Depends(require_admin)):
        valid_app_id(application_id)
        try:
            repo, app_row, runs, reviews = load_case(application_id)
            linked = linked_rows(repo, runs)
        except HTTPException:
            raise
        except Exception as exc:
            raise fail(exc) from None
        return presenters.admin_case(app_row, runs, reviews, linked, buyer=settings.workspace_name)

    @app.get("/api/admin/applications/{application_id}/reveal")
    def admin_reveal(application_id: str, _session: dict = Depends(require_admin)):
        valid_app_id(application_id)
        try:
            _repo, app_row, runs, _reviews = load_case(application_id)
        except HTTPException:
            raise
        except Exception as exc:
            raise fail(exc) from None
        extracted = (runs[0].get("extracted_json") if runs else {}) or {}
        return {"rows": presenters.unmasked_comparison(app_row.get("payload_json") or {}, extracted)}

    @app.get("/api/admin/applications/{application_id}/runs/{run_id}/documents/{doc_type}")
    def admin_document(application_id: str, run_id: str, doc_type: Literal["GST", "BANK"],
                       _session: dict = Depends(require_admin)):
        valid_app_id(application_id)
        if not RUN_ID.fullmatch(run_id):
            raise HTTPException(404, "Run not found.")
        try:
            pdf = provider.repo().load_run_document(application_id, run_id, doc_type)
        except Exception as exc:
            raise fail(exc) from None
        if pdf is None:
            raise HTTPException(404, "No PDF of this type was used in that run.")
        ext = "." + pdf.filename.rsplit(".", 1)[-1].casefold() if "." in pdf.filename else ".pdf"
        ext = ext if ext in (".pdf", ".jpg", ".jpeg", ".png") else ".pdf"
        filename = presenters.SAFE_FILENAME.sub("_", f"{application_id}_{run_id}_{doc_type}{ext}")
        return Response(pdf.content, media_type=doc_content_type(filename), headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "Content-Security-Policy": "sandbox; default-src 'none'; object-src 'self'",
        })

    def viewer_type(doc) -> str:
        try:
            return file_kind(doc.filename, doc.content)  # pdf | jpeg | png (a photo is one page)
        except UploadError:
            return "pdf"

    def load_pdf(application_id: str, run_id: str, doc_type: str):
        valid_app_id(application_id)
        if not RUN_ID.fullmatch(run_id):
            raise HTTPException(404, "Run not found.")
        try:
            pdf = provider.repo().load_run_document(application_id, run_id, doc_type)
        except Exception as exc:
            raise fail(exc) from None
        if pdf is None:
            raise HTTPException(404, "No document of this type was used in that run.")
        return pdf

    @app.get("/api/admin/applications/{application_id}/runs/{run_id}/documents/{doc_type}/pages")
    def admin_document_pages(application_id: str, run_id: str, doc_type: Literal["GST", "BANK"],
                             _session: dict = Depends(require_admin)):
        """Page count for the in-app viewer (hash-verified committed document)."""
        pdf = load_pdf(application_id, run_id, doc_type)
        try:
            with pymupdf.open(stream=pdf.content, filetype=viewer_type(pdf)) as doc:
                return {"pages": min(doc.page_count, MAX_PREVIEW_PAGES), "total_pages": doc.page_count}
        except Exception:
            raise HTTPException(422, "This document can't be previewed. Open the original instead.") from None

    @app.get("/api/admin/applications/{application_id}/runs/{run_id}/documents/{doc_type}/pages/{page}")
    def admin_document_page(application_id: str, run_id: str, doc_type: Literal["GST", "BANK"], page: int,
                            _session: dict = Depends(require_admin)):
        """One page rendered to PNG on the server, so the browser never runs a PDF
        plugin or script from an uploaded file. Signed-in reviewers only; not cached."""
        if not 1 <= page <= MAX_PREVIEW_PAGES:
            raise HTTPException(404, "Page not found.")
        pdf = load_pdf(application_id, run_id, doc_type)
        try:
            with pymupdf.open(stream=pdf.content, filetype=viewer_type(pdf)) as doc:
                if page > doc.page_count:
                    raise HTTPException(404, "Page not found.")
                png = doc[page - 1].get_pixmap(dpi=144).tobytes("png")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(422, "This document can't be previewed. Open the original instead.") from None
        return Response(png, media_type="image/png", headers={"Cache-Control": "private, no-store"})

    @app.post("/api/admin/applications/{application_id}/review")
    def admin_review(application_id: str, body: Review, _session: dict = Depends(require_admin_csrf)):
        valid_app_id(application_id)
        reason = body.reason.strip()
        if len(reason) < 3:
            raise HTTPException(400, "A specific written rationale is required.")
        if v2.CONFIRMATION_PREFIX.strip() in reason or v2.REQUESTED_PREFIX.strip() in reason:
            raise HTTPException(400, "Use the confirmation option instead of typing it into the reason.")
        if body.items and (body.action != "REQUEST_CORRECTION" or set(body.items) - set(v2.FIX_ITEM_IDS)):
            raise HTTPException(400, "Choose what the vendor should change from the listed items.")
        if body.action == "REQUEST_CORRECTION":
            reason = v2.join_requested(reason, body.items)
        try:
            repo, app_row, runs, reviews = load_case(application_id)
            if body.action == "APPROVE" and v2.requires_confirmation(runs[0] if runs else None):
                # Server-side guard (V2_02 §7): an unresolved duplicate / bank-reuse case
                # cannot be approved without the structured call-back confirmation.
                if (body.confirmation or "").strip() != v2.BANK_CHANGE_CONFIRMATION:
                    raise HTTPException(400, "Approving this case needs the bank-change confirmation: "
                                             + v2.BANK_CHANGE_CONFIRMATION + ".")
                reason = f"{reason}\n\n{v2.CONFIRMATION_PREFIX}{v2.BANK_CHANGE_CONFIRMATION}"
            if body.action == "REQUEST_CORRECTION" and reviews:
                latest = reviews[0]
                from vendorflow.ux_support import active_review_request
                if (latest.get("action") == "REQUEST_CORRECTION" and str(latest.get("reason") or "").strip() == reason
                        and active_review_request(latest, runs[0] if runs else None)):
                    raise HTTPException(409, "This identical correction request is already recorded.")
            repo.admin_review(application_id, body.action, reason,
                              expected_revision=body.expected_revision,
                              expected_latest_run_id=body.expected_latest_run_id)
            _repo, app_row, runs, reviews = load_case(application_id)
            linked = linked_rows(repo, runs)
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        except PersistenceError as exc:
            # Stale revision, terminal case, or a DB-trigger conflict (e.g. approved GSTIN).
            raise HTTPException(409, str(exc)) from None
        except Exception as exc:
            raise fail(exc) from None
        return presenters.admin_case(app_row, runs, reviews, linked, buyer=settings.workspace_name)

    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def api_not_found(path: str):
        raise HTTPException(404, "Not found.")

    # ------------------------------------------------------------ React SPA
    dist = settings.frontend_dist

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if not dist.is_dir():
            return JSONResponse({"detail": "Frontend not built. Run `npm run build` in frontend/ "
                                           "or use the Vite dev server."}, status_code=404)
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and dist.resolve() in candidate.parents:
            headers = {"Cache-Control": "public, max-age=31536000, immutable"} if path.startswith("assets/") else {}
            return FileResponse(candidate, headers=headers)
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

    return app


app = create_app()
