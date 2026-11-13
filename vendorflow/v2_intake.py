"""VendorFlow v2 upload-first intake (V2_01 §5–6, V2_02 §5–7). New beside the v1.1 code.

A *draft* is an ordinary `applications` row with no runs yet (owner decision 3:
drafts never appear in the queue, metrics or duplicate checks). Its working state
lives in `payload_json["draft"]`; the run trigger replaces the payload with the
submitted values on the first submit, so no schema change is needed.

Each uploaded file is stored at once as a normal, immutable `documents` version,
then read, classified and extracted ONCE for its slot. The extraction is cached
by file hash (and checked against the hash of the parsed text). Submit reuses the
cache through `CachedExtractor`, so the provider is called once per file. The
same deterministic rules, R13 grounding and records screening run on submit.
"""
from __future__ import annotations

import hashlib
import os
import re
from uuid import uuid4
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timezone

from pydantic import Field

from . import v2_policy as v2
from .models import BankExtraction, ExtractedDocuments, GSTExtraction, StageEvent, VendorSubmission, WorkflowResult
from .pdf_reader import PDFInput, ReadPDF
from .persistence import (
    PersistenceError, SupabaseRepository, UnauthorizedTracking, _token_digest,
)
from .pipeline import ProcessingPipeline, StageCallback
from .v2_scan import OCR_UNAVAILABLE, ReadDocument, content_type, file_kind, read_document, strip_metadata
from .rules import EMAIL_PATTERN, GST_STATE_CODES, GSTIN_PATTERN, IFSC_PATTERN, norm_id, norm_state

SLOTS = ("GST", "BANK")
OTHER = {"GST": "BANK", "BANK": "GST"}
MAX_DRAFT_DOCUMENTS = 12  # stored versions per draft (uploads + moves); bounds provider cost
FIELDS = tuple(f[0] for f in v2.PROVENANCE_FIELDS)
DOC_OF = {f[0]: f[3] for f in v2.PROVENANCE_FIELDS}
DOC_KEY = {f[0]: f[4] for f in v2.PROVENANCE_FIELDS}
LABEL = {f[0]: f[1] for f in v2.PROVENANCE_FIELDS}
PHONE = re.compile(r"^\+?[0-9][0-9 -]{8,15}[0-9]$")
DOC_WORDS = {"GST": "GST certificate", "BANK": "bank document"}
READ_WORDS = {"legal_name": "legal name", "gstin": "GSTIN", "state": "state", "address": "address",
              "holder_name": "account holder", "account_number": "account number", "ifsc": "IFSC"}


class DraftError(PersistenceError):
    """Safe-to-display draft problems."""


class DraftSubmitted(DraftError):
    pass


class DraftLimit(DraftError):
    pass


class DraftInvalid(DraftError):
    pass


class V2Submission(VendorSubmission):
    """v1.1 submission plus the v2 intake fields. Saved in runs.payload_json; the
    v1.1 code reads only the base fields (pydantic ignores the extras)."""
    contact_phone: str = ""
    address: str = ""
    declaration: bool = False
    declared_at: str = ""
    intake: str = Field(default="upload_first")


# ---------------------------------------------------------------- classification

_GST_MARKERS = (r"(?i)\bGST\s+REG(?:ISTRATION)?\b", r"(?im)^\s*GSTIN\b", r"(?i)\blegal (?:business )?name\b",
                r"(?i)\btrade name\b", r"(?i)certificate of registration|REG-06")
_BANK_MARKERS = (r"(?i)\bbank\b[^\n]{0,30}\b(?:confirmation|letter|statement)\b|cancell?ed cheque",
                 r"(?im)^\s*account (?:holder|number|no)\b", r"(?im)^\s*IFSC\b", r"(?i)\baccount type\b")


def classify_document(read: ReadPDF | None) -> str | None:
    """'GST', 'BANK' or None (not sure). A hint for the slot warning only, never evidence."""
    if not read or not read.readable:
        return None
    gst = sum(bool(re.search(p, read.text)) for p in _GST_MARKERS)
    bank = sum(bool(re.search(p, read.text)) for p in _BANK_MARKERS)
    if gst >= 2 and gst > bank:
        return "GST"
    if bank >= 2 and bank > gst:
        return "BANK"
    return None


# ---------------------------------------------------------------- cache

def text_sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


class CachedExtractor:
    """Extractor that answers from the per-file upload cache; only a miss reaches the
    provider (and then only for the missing document)."""

    def __init__(self, inner, cache: dict[tuple[str, str], dict], scans: dict[str, ReadDocument | None] | None = None):
        self.inner = inner
        self.cache = cache
        self.scans = scans or {}
        self.provider_calls = 0
        self.last_diagnostic = None

    def extract(self, gst_text: str, bank_text: str) -> ExtractedDocuments:
        gst = self.cache.get(("GST", text_sha(gst_text))) if gst_text.strip() else None
        bank = self.cache.get(("BANK", text_sha(bank_text))) if bank_text.strip() else None
        result = ExtractedDocuments.empty()
        if (gst_text.strip() and gst is None) or (bank_text.strip() and bank is None):
            need_gst, need_bank = gst_text if gst is None else "", bank_text if bank is None else ""
            fresh = provider_extract(self.inner, need_gst, need_bank,
                                     self.scans.get("GST") if need_gst else None,
                                     self.scans.get("BANK") if need_bank else None)
            self.provider_calls += 1
            self.last_diagnostic = getattr(self.inner, "last_diagnostic", None)
            result = fresh
        if gst is not None:
            result.gst = GSTExtraction(**gst)
        if bank is not None:
            result.bank = BankExtraction(**bank)
        return result


def provider_extract(extractor, gst_text: str, bank_text: str,
                     gst_scan: ReadDocument | None = None, bank_scan: ReadDocument | None = None) -> ExtractedDocuments:
    """Photos and scans go to the provider as images (their OCR text is only for R13
    grounding); text PDFs go as text. One call for whatever needs reading."""
    scanned = [s for s in (gst_scan, bank_scan) if s is not None and getattr(s, "ocr", False) and s.images]
    if scanned and hasattr(extractor, "extract_images"):
        g_img = list(gst_scan.images) if gst_scan in scanned else []
        b_img = list(bank_scan.images) if bank_scan in scanned else []
        # The OCR text of a scanned document is passed only so the OFFLINE test double can
        # fall back to it; the real provider ignores the text of a document given as images.
        return extractor.extract_images(g_img, b_img, gst_text, bank_text)
    return extractor.extract(gst_text, bank_text)


def store_document(repo: SupabaseRepository, application_id: str, slot: str, upload: PDFInput) -> dict:
    """v2 counterpart of SupabaseRepository.upload_document for PDF, JPG and PNG files
    (the original file is kept as evidence; same versioning, hash and compensation)."""
    if slot not in SLOTS:
        raise ValueError("Unknown document type")
    kind = file_kind(upload.filename, upload.content)
    if kind == "pdf":
        return repo.upload_document(application_id, slot, upload)
    upload = PDFInput(upload.filename, strip_metadata(kind, upload.content))  # no EXIF/GPS in evidence
    old = repo._latest_document_row(application_id, slot)
    version = int(old["version"]) + 1 if old else 1
    sha = hashlib.sha256(upload.content).hexdigest()
    ext = os.path.splitext(upload.filename.casefold())[1]
    path = f"{application_id}/{slot}/v{version}-{uuid4().hex}{ext}"
    stored = False
    try:
        repo.client.storage.from_(repo.BUCKET).upload(
            path=path, file=upload.content,
            file_options={"content-type": content_type(upload.filename), "upsert": "false"})
        stored = True
        row = {"application_id": application_id, "doc_type": slot, "storage_path": path,
               "file_sha256": sha, "version": version, "filename": upload.filename}
        response = repo.client.table("documents").insert(row).execute()
        if not response.data:
            raise RuntimeError("No confirmed document metadata row")
        return response.data[0]
    except Exception as exc:
        if stored:
            try:
                confirmed = (repo.client.table("documents").select("*")
                             .eq("storage_path", path).limit(1).execute().data)
                if confirmed and confirmed[0]["file_sha256"] == sha:
                    return confirmed[0]
            except Exception:
                pass
            try:
                repo.client.storage.from_(repo.BUCKET).remove([path])
            except Exception:
                pass
        raise PersistenceError("The upload could not be saved. Try again.") from exc


# ---------------------------------------------------------------- helpers

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def empty_draft() -> dict:
    return {"rev": 0, "files": {"GST": None, "BANK": None}, "cache": {}, "overrides": {},
            "contact": {"name": "", "email": "", "phone": ""}, "declaration": False, "declared_at": ""}


def doc_fields(draft: dict, slot: str) -> dict | None:
    """Extracted fields of the file currently in `slot`, or None when it was not read."""
    file = (draft.get("files") or {}).get(slot)
    if not file or file.get("status") not in ("read", "nothing_found"):
        return None
    return (draft.get("cache") or {}).get(f"{slot}:{file['sha256']}", {}).get("fields")


def extracted_view(draft: dict) -> dict:
    empty = ExtractedDocuments.empty().model_dump()
    return {"gst": doc_fields(draft, "GST") or empty["gst"], "bank": doc_fields(draft, "BANK") or empty["bank"]}


def current_values(draft: dict) -> dict:
    extracted = extracted_view(draft)
    overrides = draft.get("overrides") or {}
    values = {}
    for field in FIELDS:
        part = extracted["gst" if DOC_OF[field] == "GST" else "bank"]
        values[field] = overrides[field] if field in overrides else str(part.get(DOC_KEY[field]) or "")
    return values


def derived_pan(gstin: str) -> str:
    value = norm_id(gstin)
    return value[2:12] if GSTIN_PATTERN.fullmatch(value) else ""


def _mask(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    return f"•••• {digits[-4:]}" if digits else ""


def field_errors(values: dict) -> dict[str, str]:
    errors: dict[str, str] = {}
    gstin = norm_id(values.get("gstin"))
    if gstin and not GSTIN_PATTERN.fullmatch(gstin):
        errors["gstin"] = "Check your GSTIN. It should be 15 characters, like 27ABCDE1234F1Z0."
    elif gstin and v2.gstin_check_digit_ok(gstin) is False:
        errors["gstin"] = "Check your GSTIN. Its last character doesn't match the rest of the number."
    elif gstin and values.get("business_state"):
        code = GST_STATE_CODES.get(norm_state(values.get("business_state")))
        if code and code != gstin[:2]:
            errors["business_state"] = "This state doesn't match the state code at the start of your GSTIN."
    ifsc = norm_id(values.get("ifsc"))
    if ifsc and not IFSC_PATTERN.fullmatch(ifsc):
        errors["ifsc"] = "Check your IFSC. It should be 11 characters, like SBIN0001234."
    account = str(values.get("account_number") or "").strip()
    if account and not re.fullmatch(r"[0-9][0-9 -]*[0-9]|[0-9]", account):
        errors["account_number"] = "Use digits only for the account number."
    return errors


def contact_errors(contact: dict) -> dict[str, str]:
    errors = {}
    email = str(contact.get("email") or "").strip()
    phone = str(contact.get("phone") or "").strip()
    if email and not EMAIL_PATTERN.fullmatch(email):
        errors["email"] = "Enter a valid email address, like name@business.in."
    if phone and not (PHONE.fullmatch(phone) and 10 <= len(re.sub(r"\D", "", phone)) <= 13):
        errors["phone"] = "Enter a valid phone number, like +91 98765 43210."
    return errors


_FILE_MESSAGES = {
    "nothing_found": "We couldn't find the details on this document. Check it's the right file or upload a clearer copy.",
    "unreadable": "We couldn't read this file. Upload a clearer copy: a sharp, well-lit photo or a PDF.",
    "unavailable": ("We couldn't read this file just now because of a temporary problem on our side. "
                    "This isn't a problem with your file. Type the details from it on the next step."),
}


def file_view(slot: str, file: dict | None, draft: dict) -> dict | None:
    if not file:
        return None
    status = file.get("status")
    suggested = None
    if status == "wrong_slot":
        suggested = OTHER[slot]
        message = (f"This looks like a {DOC_WORDS[suggested]}. Did you mean to put it in the "
                   f"{'bank' if suggested == 'BANK' else 'GST'} slot?")
    elif status == "read":
        found = [READ_WORDS[k] for k, v in (doc_fields(draft, slot) or {}).items() if str(v or "").strip()]
        message = "Read: " + ", ".join(found)
    else:
        message = _FILE_MESSAGES.get(status, "")
    return {"filename": file.get("filename"), "status": status, "message": message,
            "suggested_slot": suggested, "pages": file.get("pages"), "uploaded_at": file.get("uploaded_at"),
            "on_file": bool(file.get("on_file")), "version": file.get("version")}


def draft_view(application_id: str, draft: dict, *, buyer: str = "Zamp AI") -> dict:
    """Vendor-safe draft: pre-filled values with their source. No rule IDs, no cache,
    no document IDs. The account number is masked to its last 4 digits."""
    values = current_values(draft)
    provenance = {r["field"]: r for r in v2.field_provenance(values, extracted_view(draft))}
    errors = field_errors(values)
    fields = []
    for field in FIELDS:
        row = provenance[field]
        value, doc_value = row["value"], row["document_value"] or ""
        if field == "account_number":
            value, doc_value = _mask(value), _mask(doc_value)
        fields.append({"key": field, "label": LABEL[field], "document": DOC_OF[field],
                       "value": value, "document_value": doc_value or None,
                       "status": row["status"], "error": errors.get(field)})
    files = {slot: file_view(slot, (draft.get("files") or {}).get(slot), draft) for slot in SLOTS}
    contact = dict(draft.get("contact") or {})
    c_errors = contact_errors(contact)

    documents_blockers, details_blockers = [], []
    for slot in SLOTS:
        file = files[slot]
        if not file:
            documents_blockers.append(f"Upload your {DOC_WORDS[slot]}.")
        elif file["status"] == "wrong_slot":
            documents_blockers.append(f"Move the {DOC_WORDS[file['suggested_slot']]} to its slot.")
        elif file["status"] in ("unreadable", "nothing_found"):
            documents_blockers.append(f"Upload a clearer copy of your {DOC_WORDS[slot]}.")
        # "unavailable" (provider outage) does not block: the vendor types the values and
        # the case goes to the team; submit tries the reading again (V2_01 §6).
    for row in fields:
        if not row["value"]:
            details_blockers.append(f"Add your {row['label'] if row['key'] in ('gstin', 'ifsc') else row['label'].lower()}.")
        elif row["error"]:
            details_blockers.append(row["error"])
    for key, label in (("name", "contact name"), ("email", "contact email"), ("phone", "contact phone")):
        if not str(contact.get(key) or "").strip():
            details_blockers.append(f"Add your {label}.")
        elif key in c_errors:
            details_blockers.append(c_errors[key])
    gst = doc_fields(draft, "GST") or {}
    return {
        "application_id": application_id, "owner": v2.DRAFT, "buyer": buyer,
        "rev": int(draft.get("rev") or 0),  # parallel uploads: the client keeps the newest
        "files": files, "fields": fields,
        "pan": {"value": derived_pan(values["gstin"]), "source": "GSTIN"},
        "address": gst.get("address") or None,
        "contact": {"name": contact.get("name") or "", "email": contact.get("email") or "",
                    "phone": contact.get("phone") or ""},
        "contact_errors": c_errors,
        "declaration": bool(draft.get("declaration")),
        "documents_ready": not documents_blockers, "details_ready": not documents_blockers and not details_blockers,
        "blockers": documents_blockers + details_blockers,
        "documents_blockers": documents_blockers, "details_blockers": details_blockers,
        "flagged": [r["key"] for r in fields if r["status"] in ("edited", "vendor")],
    }


def fix_view(application_id: str, fix: dict, items: list[dict], *, buyer: str = "Zamp AI") -> dict:
    """The vendor's fix page: only the requested items, each an upload slot or a field.
    A requested document needs a NEW upload that we could read; a field that became
    missing or invalid (for example after a new upload) is shown and blocks too."""
    view = draft_view(application_id, fix, buyer=buyer)
    doc_items = {i["slot"] for i in items if i["kind"] == "document"}
    field_items = {i["field"] for i in items if i["kind"] == "field"}
    blockers = []
    for slot in SLOTS:
        file = view["files"][slot]
        if slot in doc_items and (not file or file["on_file"]):
            blockers.append(f"Upload a new {DOC_WORDS[slot]}.")
    blockers += [b for b in view["documents_blockers"] if b not in blockers]
    shown = [f["key"] for f in view["fields"]
             if f["key"] in field_items or not f["value"] or f["error"] or f["status"] == "unread"]
    contact = "contact" in field_items or bool(view["contact_errors"]) \
        or not all(view["contact"].get(k) for k in ("name", "email", "phone"))
    blockers += view["details_blockers"]
    view.update(owner=v2.VENDOR, items=items, shown_fields=shown, show_contact=contact,
                show_slots=[s for s in SLOTS if s in doc_items or (view["files"][s] or {}).get("status") not in ("read", "unavailable")],
                blockers=blockers, ready=not blockers)
    return view


# ---------------------------------------------------------------- service

class DraftService:
    def __init__(self, repo: SupabaseRepository, extractor_factory: Callable[[], object], *,
                 pipeline_options: dict | None = None):
        self.repo = repo
        self.client = repo.client
        self.extractor_factory = extractor_factory
        self.pipeline_options = dict(pipeline_options or {})

    # --- rows
    def create_draft(self, application_id: str, tracking_code: str) -> dict:
        if not (re.fullmatch(r"VF-[0-9A-F]{12}", application_id) and len(tracking_code) >= 20):
            raise UnauthorizedTracking("Application ID or tracking code is incorrect.")
        row = {"id": application_id, "payload_json": {"draft": empty_draft()},
               "tracking_token_hash": _token_digest(application_id, tracking_code),
               "current_status": "PENDING", "decision_source": "AUTOMATED"}
        try:
            response = self.client.table("applications").insert(row).execute()
            if not response.data:
                raise RuntimeError("not acknowledged")
        except Exception as exc:
            # Lost acknowledgement or a parallel first upload: the row may exist already.
            try:
                self.repo.authenticate_vendor(application_id, tracking_code)
            except UnauthorizedTracking:
                raise PersistenceError("Your application could not be started. Try again.") from exc
        return self.draft(application_id)

    def draft(self, application_id: str) -> dict:
        app = self.repo._application(application_id)
        if app.get("latest_run_id"):
            raise DraftSubmitted("This application was already submitted. Open it to see its status.")
        payload = app.get("payload_json") or {}
        return deepcopy(payload.get("draft") or empty_draft())

    def _load(self, application_id: str, kind: str) -> tuple[dict, dict, Callable]:
        """(application row, working copy, compare-and-swap filter) for a draft or a fix."""
        if kind == "draft":
            draft = self.draft(application_id)
            rev = str(int(draft.get("rev") or 0))
            return ({}, draft, lambda q: q.eq("payload_json->draft->>rev", rev).is_("latest_run_id", "null"))
        app, run, _review = self._fix_context(application_id)
        stored = (app.get("payload_json") or {}).get("fix")
        if stored and stored.get("base_run_id") == app["latest_run_id"]:
            fix = deepcopy(stored)
        else:
            fix = self._fresh_fix(application_id, app, run)
        base = app["latest_run_id"]
        if stored:
            rev = str(int(stored.get("rev") or 0))
            return app, fix, lambda q: q.eq("latest_run_id", base).eq("payload_json->fix->>rev", rev)
        return app, fix, lambda q: q.eq("latest_run_id", base).is_("payload_json->fix", "null")

    def _mutate(self, application_id: str, change: Callable[[dict], None], kind: str = "draft") -> dict:
        """Compare-and-swap on the working copy's rev so parallel uploads never lose each other's update."""
        for _attempt in range(6):
            app, draft, guard = self._load(application_id, kind)
            rev = int(draft.get("rev") or 0)
            change(draft)
            draft["rev"] = rev + 1
            if kind == "draft":
                payload = {"draft": draft}
            else:  # the submitted values stay as they are; the fix sits beside them
                payload = {k: v for k, v in (app.get("payload_json") or {}).items() if k != "fix"}
                payload["fix"] = draft
            query = self.client.table("applications").update({"payload_json": payload, "updated_at": _now()})
            response = guard(query.eq("id", application_id)).execute()
            if response.data:
                return draft
        raise PersistenceError("Your application is being updated in another tab. Refresh and try again.")

    def _count_documents(self, application_id: str) -> int:
        return len(self.client.table("documents").select("id").eq("application_id", application_id).execute().data)

    # --- fixes (B7 part 1): the vendor changes only the requested items of a SUBMITTED
    # application. The fix lives in payload_json["fix"] beside the submitted values; the
    # run trigger replaces the payload on re-check, which drops it. Nothing else changes.
    def _fix_context(self, application_id: str) -> tuple[dict, dict, dict | None]:
        app = self.repo._application(application_id)
        if app.get("current_status") != "PENDING" or not app.get("latest_run_id"):
            raise DraftSubmitted("This application has a final decision and can no longer be changed.")
        runs = self.repo.runs_for_application(application_id)
        reviews = self.repo.review_history(application_id)
        run = runs[0] if runs else None
        review = reviews[0] if reviews else None
        if not run or run.get("id") != app["latest_run_id"]:
            raise PersistenceError("Your application is being updated. Refresh and try again.")
        if v2.case_owner(app, run, review) != v2.VENDOR:
            raise DraftSubmitted("Your application is with our team. No changes are needed from you right now.")
        return app, run, review

    def _fresh_fix(self, application_id: str, app: dict, run: dict) -> dict:
        """Working copy seeded from the latest run: its committed documents (with the
        extraction that run already made, so re-check reuses it) and the submitted values."""
        payload = run.get("payload_json") or {}
        extracted = run.get("extracted_json") or {}
        outage = v2.extraction_outage(run)
        fix = empty_draft()
        fix.update(base_run_id=app["latest_run_id"], doc_base=self._count_documents(application_id),
                   declaration=bool(payload.get("declaration")), declared_at=str(payload.get("declared_at") or ""),
                   contact={"name": str(payload.get("contact_name") or ""), "email": str(payload.get("contact_email") or ""),
                            "phone": str(payload.get("contact_phone") or "")})
        for item in run.get("document_manifest") or []:
            slot = item.get("doc_type")
            if slot not in SLOTS:
                continue
            row = self._own_document(application_id, str(item["id"]))
            read = read_document(self.repo._download_verified(row))
            fields = (extracted.get("gst" if slot == "GST" else "bank") or {})
            kind = classify_document(read)
            entry = {"document_id": str(row["id"]), "version": int(row["version"]), "filename": row.get("filename"),
                     "sha256": row["file_sha256"], "pages": read.pages, "kind": kind,
                     "uploaded_at": str(row.get("created_at") or ""), "on_file": True}
            if not read.readable:
                entry["status"] = "unreadable"
            elif kind and kind != slot:
                entry["status"] = "wrong_slot"
            elif outage:
                entry["status"] = "unavailable"  # not cached: re-check reads it again
            else:
                fix["cache"][f"{slot}:{row['file_sha256']}"] = {"text_sha": text_sha(read.text), "fields": dict(fields)}
                entry["status"] = "read" if any(str(v or "").strip() for k, v in fields.items() if k != "address") \
                    else "nothing_found"
            fix["files"][slot] = entry
        # What the vendor submitted stays; a value that differs from its document is an override.
        view = extracted_view(fix)
        for field in FIELDS:
            value = str(payload.get(field) or "").strip()
            doc_value = str(view["gst" if DOC_OF[field] == "GST" else "bank"].get(DOC_KEY[field]) or "")
            if not (doc_value and value and v2._same(field, value, doc_value)) and (value or doc_value):
                fix["overrides"][field] = value
        return fix

    def fix(self, application_id: str) -> tuple[dict, list[dict]]:
        """(working copy, requested items). Opening it stores nothing."""
        app, fix, _guard = self._load(application_id, "fix")
        _app, run, review = self._fix_context(application_id)
        return fix, v2.fix_items(run, review)

    def fix_items(self, application_id: str) -> list[dict]:
        _app, run, review = self._fix_context(application_id)
        return v2.fix_items(run, review)

    # --- files
    def _extract_one(self, slot: str, read: ReadPDF) -> dict:
        extractor = self.extractor_factory()
        if slot == "GST":
            out = provider_extract(extractor, read.text, "", gst_scan=read)  # type: ignore[arg-type]
        else:
            out = provider_extract(extractor, "", read.text, bank_scan=read)  # type: ignore[arg-type]
        return (out.gst if slot == "GST" else out.bank).model_dump()

    def _process(self, application_id: str, slot: str, pdf: PDFInput, read: ReadPDF, cache: dict,
                 emit: Callable[[str, str, str], None], doc_base: int = 0) -> tuple[dict, dict]:
        """Store, identify and read ONE file for `slot`. Returns (file entry, new cache entries)."""
        if self._count_documents(application_id) - doc_base >= MAX_DRAFT_DOCUMENTS:
            raise DraftLimit("Too many uploads for this application. Contact the finance team if you need help.")
        emit("U1", "STARTED", "")
        row = store_document(self.repo, application_id, slot, pdf)
        emit("U1", "COMPLETED", "")
        emit("U2", "STARTED", "")
        kind = classify_document(read)
        emit("U2", "COMPLETED", "")
        entry = {"document_id": str(row["id"]), "version": int(row["version"]), "filename": pdf.filename,
                 "sha256": row["file_sha256"], "pages": read.pages, "kind": kind, "uploaded_at": _now()}
        new_cache: dict = {}
        if not read.readable and read.issue == OCR_UNAVAILABLE:
            entry["status"] = "unavailable"  # our side, not the vendor's file
            emit("U3", "FAILED", "")
        elif not read.readable:
            entry["status"] = "unreadable"
            emit("U3", "SKIPPED", "")
        elif kind and kind != slot:
            entry["status"] = "wrong_slot"  # no provider call for a file in the wrong slot
            emit("U3", "SKIPPED", "")
        else:
            key = f"{slot}:{entry['sha256']}"
            emit("U3", "STARTED", "")
            hit = cache.get(key)
            if hit and hit.get("text_sha") == text_sha(read.text):
                fields = hit["fields"]
            else:
                try:
                    fields = self._extract_one(slot, read)
                except Exception:  # provider outage: sanitised, never the provider text
                    entry["status"] = "unavailable"
                    emit("U3", "FAILED", "")
                    return entry, new_cache
                new_cache[key] = {"text_sha": text_sha(read.text), "fields": fields}
            entry["status"] = "read" if any(str(v or "").strip() for k, v in fields.items() if k != "address") \
                else "nothing_found"
            emit("U3", "COMPLETED" if entry["status"] == "read" else "FAILED", "")
        return entry, new_cache

    def _place(self, application_id: str, placements: list[tuple[str, dict]], cache: dict,
               clear: tuple[str, str] | None = None, kind: str = "draft") -> dict:
        def change(draft: dict) -> None:
            draft.setdefault("cache", {}).update(cache)
            if clear and (draft["files"].get(clear[0]) or {}).get("document_id") == clear[1]:
                draft["files"][clear[0]] = None  # moved to the empty slot
            for slot, entry in placements:
                current = draft["files"].get(slot)
                if current and current.get("document_id") != entry.get("document_id") \
                        and int(current.get("version") or 0) > int(entry.get("version") or 0):
                    continue  # a newer upload to this slot already won
                draft["files"][slot] = entry
                # A new document is a fresh reading: earlier edits of its fields no longer apply.
                for field in FIELDS:
                    if DOC_OF[field] == slot:
                        draft["overrides"].pop(field, None)
        return self._mutate(application_id, change, kind)

    def add_file(self, application_id: str, slot: str, pdf: PDFInput,
                 stage_callback: StageCallback | None = None, kind: str = "draft") -> dict:
        if slot not in SLOTS:
            raise DraftInvalid("Unknown document slot.")
        _app, draft, _guard = self._load(application_id, kind)
        entry, cache = self._process(application_id, slot, pdf, read_document(pdf), draft.get("cache") or {},
                                     _emitter(stage_callback), int(draft.get("doc_base") or 0))
        return self._place(application_id, [(slot, entry)], cache, kind=kind)

    def move_file(self, application_id: str, slot: str, stage_callback: StageCallback | None = None,
                  kind: str = "draft") -> dict:
        """Move the file in `slot` to the other slot; a file already there moves back (swap)."""
        if slot not in SLOTS:
            raise DraftInvalid("Unknown document slot.")
        _app, draft, _guard = self._load(application_id, kind)
        source = draft["files"].get(slot)
        if not source:
            raise DraftInvalid("There is no file to move.")
        moves = [(source, OTHER[slot])]
        if draft["files"].get(OTHER[slot]):
            moves.append((draft["files"][OTHER[slot]], slot))
        cache = dict(draft.get("cache") or {})
        placements, new_cache = [], {}
        emit = _emitter(stage_callback)
        for entry, target in moves:
            pdf = self.repo._download_verified(self._own_document(application_id, entry["document_id"]))
            moved, added = self._process(application_id, target, pdf, read_document(pdf), cache, emit,
                                         int(draft.get("doc_base") or 0))
            placements.append((target, moved))
            new_cache.update(added)
        clear = (slot, source["document_id"]) if len(moves) == 1 else None
        return self._place(application_id, placements, new_cache, clear, kind=kind)

    def remove_file(self, application_id: str, slot: str) -> dict:
        if slot not in SLOTS:
            raise DraftInvalid("Unknown document slot.")

        def change(draft: dict) -> None:
            draft["files"][slot] = None
            for field in FIELDS:
                if DOC_OF[field] == slot:
                    draft["overrides"].pop(field, None)
        return self._mutate(application_id, change)

    def _own_document(self, application_id: str, document_id: str) -> dict:
        row = self.repo._document_by_id(document_id)
        if row.get("application_id") != application_id:
            raise PersistenceError("Referenced document is not part of this application.")
        return row

    # --- values
    def save_values(self, application_id: str, *, changes: dict | None = None, reset: list | None = None,
                    contact: dict | None = None, declaration: bool | None = None, kind: str = "draft") -> dict:
        changes = {k: str(v or "").strip()[:200] for k, v in (changes or {}).items()}
        unknown = set(changes) - set(FIELDS) or set(reset or []) - set(FIELDS)
        if unknown:
            raise DraftInvalid("Unknown field.")

        def change(draft: dict) -> None:
            extracted = extracted_view(draft)
            for field, value in changes.items():
                doc_value = str(extracted["gst" if DOC_OF[field] == "GST" else "bank"].get(DOC_KEY[field]) or "")
                if field in ("gstin", "ifsc"):
                    value = norm_id(value)
                if doc_value and value and v2._same(field, value, doc_value):
                    draft["overrides"].pop(field, None)  # same as the document
                else:
                    draft["overrides"][field] = value
            for field in reset or []:
                draft["overrides"].pop(field, None)
            if contact is not None:
                draft["contact"] = {key: str(contact.get(key) or "").strip()[:limit]
                                    for key, limit in (("name", 120), ("email", 200), ("phone", 24))}
            if declaration is not None:
                draft["declaration"] = bool(declaration)
                draft["declared_at"] = _now() if declaration else ""
        return self._mutate(application_id, change, kind)

    def submission(self, draft: dict) -> V2Submission:
        values = current_values(draft)
        contact = draft.get("contact") or {}
        gst = doc_fields(draft, "GST") or {}
        return V2Submission(
            legal_name=values["legal_name"], business_state=values["business_state"],
            gstin=values["gstin"], pan=derived_pan(values["gstin"]),
            bank_holder=values["bank_holder"], account_number=values["account_number"], ifsc=values["ifsc"],
            contact_name=str(contact.get("name") or ""), contact_email=str(contact.get("email") or ""),
            contact_phone=str(contact.get("phone") or ""), address=str(gst.get("address") or ""),
            declaration=bool(draft.get("declaration")), declared_at=str(draft.get("declared_at") or ""),
        )

    # --- submit
    def submit(self, application_id: str, stage_callback: StageCallback | None = None) -> WorkflowResult:
        app = self.repo._application(application_id)
        if app.get("latest_run_id"):  # lost response: return the saved result, never a second run
            saved = self.repo.saved_result(application_id)
            if saved is not None:
                return saved
        draft = self.draft(application_id)
        if not draft.get("declaration"):
            raise DraftInvalid("Confirm that these details are correct and belong to your business.")
        vendor = self.submission(draft)
        if not vendor.legal_name.strip() or not vendor.contact_email.strip():
            raise DraftInvalid("Add your legal business name and contact email before submitting.")
        return self._evaluate(application_id, draft, vendor, "submission", int(app.get("revision") or 0),
                              stage_callback)

    def submit_fix(self, application_id: str, stage_callback: StageCallback | None = None) -> tuple[WorkflowResult, int]:
        """Re-check after the vendor fixed the requested items. Reuses every reading
        already made (the latest run's and the fix uploads'). Returns (result, provider calls)."""
        app, fix, _guard = self._load(application_id, "fix")
        _app, run, review = self._fix_context(application_id)
        blockers = fix_view(application_id, fix, v2.fix_items(run, review))["blockers"]
        if blockers:
            raise DraftInvalid(blockers[0])
        vendor = self.submission(fix)
        return self._evaluate(application_id, fix, vendor, "resubmission", int(app.get("revision") or 0),
                              stage_callback, count=True)

    def _evaluate(self, application_id: str, draft: dict, vendor: V2Submission, trigger: str,
                  expected_revision: int, stage_callback: StageCallback | None, count: bool = False):
        uploads: dict[str, PDFInput | None] = {"GST": None, "BANK": None}
        manifest, cache = [], {}
        for slot in SLOTS:
            entry = draft["files"].get(slot)
            if not entry:
                continue
            row = self._own_document(application_id, entry["document_id"])
            if row["doc_type"] != slot or row["file_sha256"] != entry["sha256"]:
                raise PersistenceError("Saved document does not match your application. Upload it again.")
            pdf = self.repo._download_verified(row)
            uploads[slot] = pdf
            manifest.append(self.repo._manifest_entry(row))
            hit = (draft.get("cache") or {}).get(f"{slot}:{entry['sha256']}")
            if hit:
                cache[(slot, hit["text_sha"])] = hit["fields"]
        scans = {slot: read_document(upload) for slot, upload in uploads.items()}
        extractor = CachedExtractor(self.extractor_factory(), cache, scans)
        options = {**self.pipeline_options, "reader": read_document}
        engine = ProcessingPipeline(extractor, approved_lookup=self.repo.approved_lookup, **options)
        result = engine.evaluate(vendor, uploads["GST"], uploads["BANK"], application_id=application_id,
                                 trigger=trigger, stage_callback=stage_callback, persistence_planned=True)
        try:
            saved = self.repo.commit_run(result, vendor, expected_revision=expected_revision,
                                         document_manifest=manifest, stage_callback=stage_callback)
        except PersistenceError:
            saved = self.repo.saved_result(application_id)
            if saved is None or saved.run_id != result.run_id:
                raise
        return (saved, extractor.provider_calls) if count else saved


def _emitter(callback: StageCallback | None) -> Callable[[str, str, str], None]:
    labels = {"U1": "Store document", "U2": "Identify document type", "U3": "Read document details"}

    def emit(stage_id: str, event: str, note: str) -> None:
        if callback:
            callback(StageEvent(stage_id=stage_id, label=labels[stage_id], event=event, note=note))
    return emit
