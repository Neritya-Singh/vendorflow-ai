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
import re
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime, timezone

from pydantic import Field

from . import v2_policy as v2
from .models import BankExtraction, ExtractedDocuments, GSTExtraction, StageEvent, VendorSubmission, WorkflowResult
from .pdf_reader import PDFInput, ReadPDF, read_pdf
from .persistence import (
    PersistenceError, SupabaseRepository, UnauthorizedTracking, _token_digest,
)
from .pipeline import ProcessingPipeline, StageCallback
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

    def __init__(self, inner, cache: dict[tuple[str, str], dict]):
        self.inner = inner
        self.cache = cache
        self.provider_calls = 0
        self.last_diagnostic = None

    def extract(self, gst_text: str, bank_text: str) -> ExtractedDocuments:
        gst = self.cache.get(("GST", text_sha(gst_text))) if gst_text.strip() else None
        bank = self.cache.get(("BANK", text_sha(bank_text))) if bank_text.strip() else None
        result = ExtractedDocuments.empty()
        if (gst_text.strip() and gst is None) or (bank_text.strip() and bank is None):
            fresh = self.inner.extract(gst_text if gst is None else "", bank_text if bank is None else "")
            self.provider_calls += 1
            self.last_diagnostic = getattr(self.inner, "last_diagnostic", None)
            result = fresh
        if gst is not None:
            result.gst = GSTExtraction(**gst)
        if bank is not None:
            result.bank = BankExtraction(**bank)
        return result


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
    "unreadable": "We couldn't read this file. Upload a PDF with selectable text. Scans and photos are supported soon.",
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
            "suggested_slot": suggested, "pages": file.get("pages"), "uploaded_at": file.get("uploaded_at")}


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
        "flagged": [r["key"] for r in fields if r["status"] in ("edited", "vendor")],
    }


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

    def _mutate(self, application_id: str, change: Callable[[dict], None]) -> dict:
        """Compare-and-swap on draft.rev so parallel uploads never lose each other's update."""
        for _attempt in range(6):
            draft = self.draft(application_id)
            rev = int(draft.get("rev") or 0)
            change(draft)
            draft["rev"] = rev + 1
            response = (self.client.table("applications")
                        .update({"payload_json": {"draft": draft}, "updated_at": _now()})
                        .eq("id", application_id).eq("payload_json->draft->>rev", str(rev))
                        .is_("latest_run_id", "null").execute())
            if response.data:
                return draft
        raise PersistenceError("Your application is being updated in another tab. Refresh and try again.")

    def _count_documents(self, application_id: str) -> int:
        return len(self.client.table("documents").select("id").eq("application_id", application_id).execute().data)

    # --- files
    def _extract_one(self, slot: str, text: str) -> dict:
        extractor = self.extractor_factory()
        out = extractor.extract(text, "") if slot == "GST" else extractor.extract("", text)
        return (out.gst if slot == "GST" else out.bank).model_dump()

    def _process(self, application_id: str, slot: str, pdf: PDFInput, read: ReadPDF, cache: dict,
                 emit: Callable[[str, str, str], None]) -> tuple[dict, dict]:
        """Store, identify and read ONE file for `slot`. Returns (file entry, new cache entries)."""
        if self._count_documents(application_id) >= MAX_DRAFT_DOCUMENTS:
            raise DraftLimit("Too many uploads for this application. Contact the finance team if you need help.")
        emit("U1", "STARTED", "")
        row = self.repo.upload_document(application_id, slot, pdf)
        emit("U1", "COMPLETED", "")
        emit("U2", "STARTED", "")
        kind = classify_document(read)
        emit("U2", "COMPLETED", "")
        entry = {"document_id": str(row["id"]), "version": int(row["version"]), "filename": pdf.filename,
                 "sha256": row["file_sha256"], "pages": read.pages, "kind": kind, "uploaded_at": _now()}
        new_cache: dict = {}
        if not read.readable:
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
                    fields = self._extract_one(slot, read.text)
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
               clear: tuple[str, str] | None = None) -> dict:
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
        return self._mutate(application_id, change)

    def add_file(self, application_id: str, slot: str, pdf: PDFInput,
                 stage_callback: StageCallback | None = None) -> dict:
        if slot not in SLOTS:
            raise DraftInvalid("Unknown document slot.")
        draft = self.draft(application_id)
        entry, cache = self._process(application_id, slot, pdf, read_pdf(pdf), draft.get("cache") or {},
                                     _emitter(stage_callback))
        return self._place(application_id, [(slot, entry)], cache)

    def move_file(self, application_id: str, slot: str, stage_callback: StageCallback | None = None) -> dict:
        """Move the file in `slot` to the other slot; a file already there moves back (swap)."""
        if slot not in SLOTS:
            raise DraftInvalid("Unknown document slot.")
        draft = self.draft(application_id)
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
            moved, added = self._process(application_id, target, pdf, read_pdf(pdf), cache, emit)
            placements.append((target, moved))
            new_cache.update(added)
        clear = (slot, source["document_id"]) if len(moves) == 1 else None
        return self._place(application_id, placements, new_cache, clear)

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
                    contact: dict | None = None, declaration: bool | None = None) -> dict:
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
        return self._mutate(application_id, change)

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
        extractor = CachedExtractor(self.extractor_factory(), cache)
        engine = ProcessingPipeline(extractor, approved_lookup=self.repo.approved_lookup, **self.pipeline_options)
        result = engine.evaluate(vendor, uploads["GST"], uploads["BANK"], application_id=application_id,
                                 stage_callback=stage_callback, persistence_planned=True)
        try:
            return self.repo.commit_run(result, vendor, expected_revision=int(app.get("revision") or 0),
                                        document_manifest=manifest, stage_callback=stage_callback)
        except PersistenceError:
            saved = self.repo.saved_result(application_id)
            if saved is not None and saved.run_id == result.run_id:
                return saved
            raise


def _emitter(callback: StageCallback | None) -> Callable[[str, str, str], None]:
    labels = {"U1": "Store document", "U2": "Identify document type", "U3": "Read document details"}

    def emit(stage_id: str, event: str, note: str) -> None:
        if callback:
            callback(StageEvent(stage_id=stage_id, label=labels[stage_id], event=event, note=note))
    return emit
