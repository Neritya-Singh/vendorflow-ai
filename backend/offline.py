"""OFFLINE TEST MODE ONLY — in-memory stand-ins for Supabase and Gemini.

Enabled solely by VENDORFLOW_OFFLINE_MODE=1 for local development and automated
tests when no staging credentials are present. The real PDF reader, deterministic
rules, pipeline, persistence adapter (SupabaseRepository) and presenters still run;
only the database/storage client and the AI provider are replaced.

The in-memory client mirrors the integrity behaviour of the SQL triggers in
supabase/schema.sql (revision compare-and-swap, terminal immutability, approved
GSTIN uniqueness, manifest provenance). It is NOT evidence that the real Postgres
triggers, RLS or Storage privacy work — those are verified only against staging.
Nothing here is ever used when Supabase credentials are configured.
"""
from __future__ import annotations

import threading
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from vendorflow.models import BankExtraction, ExtractedDocuments, GSTExtraction
from vendorflow.rules import norm_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(row: dict, col: str):
    """PostgREST-style column path: "payload_json->draft->>rev"."""
    parts = col.replace("->>", "->").split("->")
    value = row.get(parts[0])
    for part in parts[1:]:
        value = value.get(part) if isinstance(value, dict) else None
    return str(value) if "->>" in col and value is not None else value


class _Query:
    def __init__(self, db: "InMemorySupabase", name: str):
        self.db, self.name = db, name
        self.predicates = []
        self.to_insert = None
        self.to_update = None
        self.order_col = None
        self.desc = False
        self.num = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, col, value):
        self.predicates.append(lambda r: _path(r, col) == value)
        return self

    def is_(self, col, value):
        if value != "null":
            raise NotImplementedError("offline double supports is_(col, 'null') only")
        self.predicates.append(lambda r: r.get(col) is None)
        return self

    def update(self, values):
        self.to_update = deepcopy(values)
        return self

    def neq(self, col, value):
        self.predicates.append(lambda r: r.get(col) != value)
        return self

    def order(self, col, desc=False):
        self.order_col, self.desc = col, desc
        return self

    def limit(self, count):
        self.num = count
        return self

    def insert(self, row):
        self.to_insert = deepcopy(row)
        return self

    def execute(self):
        with self.db.lock:
            return self._execute()

    def _execute(self):
        rows = self.db.rows[self.name]
        if self.to_update is not None:
            if self.name != "applications" or set(self.to_update) - {"payload_json", "updated_at"}:
                # Mirrors the server: only a draft's working payload is ever updated directly.
                raise RuntimeError("unsupported update")
            changed = []
            for row in rows:
                if all(p(row) for p in self.predicates):
                    row.update(deepcopy(self.to_update))
                    row["gstin_normalized"] = norm_id((row["payload_json"] or {}).get("gstin"))
                    changed.append(deepcopy(row))
            return SimpleNamespace(data=changed)
        if self.to_insert is None:
            matches = [deepcopy(r) for r in rows if all(p(r) for p in self.predicates)]
            if self.order_col:
                matches.sort(key=lambda r: (r.get(self.order_col) is None, r.get(self.order_col) or ""),
                             reverse=self.desc)
            if self.num is not None:
                matches = matches[: self.num]
            return SimpleNamespace(data=matches)

        row = self.to_insert
        row.setdefault("created_at", _now())
        if self.name == "applications":
            if any(r["id"] == row["id"] for r in rows):
                raise RuntimeError("duplicate key")
            row["gstin_normalized"] = norm_id(row["payload_json"].get("gstin"))
            row.setdefault("latest_run_id", None)
            row.setdefault("revision", 0)
            row["updated_at"] = row["created_at"]
        elif self.name == "documents":
            row.setdefault("id", str(uuid4()))
            if any(r["application_id"] == row["application_id"] and r["doc_type"] == row["doc_type"]
                   and r["version"] == row["version"] for r in rows):
                raise RuntimeError("duplicate document version")
        elif self.name == "runs":
            self._commit_run(row)
        elif self.name == "review_actions":
            self._commit_review(row)
        rows.append(row)
        return SimpleNamespace(data=[deepcopy(row)])

    def _app(self, application_id):
        for app in self.db.rows["applications"]:
            if app["id"] == application_id:
                return app
        raise RuntimeError("application not found")

    def _approved_conflict(self, app) -> bool:
        return any(other["id"] != app["id"] and other["current_status"] == "APPROVED"
                   and other["gstin_normalized"] == app["gstin_normalized"]
                   for other in self.db.rows["applications"])

    def _commit_run(self, row):
        app = self._app(row["application_id"])
        if app["current_status"] != "PENDING":
            raise RuntimeError("terminal application")
        if row["status"] == "REJECTED":
            raise RuntimeError("no automated rejection")
        if row["expected_revision"] != app["revision"]:
            raise RuntimeError("stale_revision")
        if row["trigger"] == "submission" and app["latest_run_id"] is not None:
            raise RuntimeError("initial submission already exists")
        if row["trigger"] == "resubmission" and app["latest_run_id"] is None:
            raise RuntimeError("resubmission without initial run")
        manifest = row.get("document_manifest") or []
        if len({d["doc_type"] for d in manifest}) != len(manifest):
            raise RuntimeError("duplicate manifest type")
        for entry in manifest:
            matches = [d for d in self.db.rows["documents"]
                       if d["id"] == entry["id"] and d["application_id"] == row["application_id"]
                       and all(d.get(k) == entry.get(k) for k in
                               ("doc_type", "version", "file_sha256", "storage_path"))]
            if len(matches) != 1:
                raise RuntimeError("manifest mismatch")
        if row["status"] == "APPROVED" and {d["doc_type"] for d in manifest} != {"GST", "BANK"}:
            raise RuntimeError("approval requires both PDFs")
        app["payload_json"] = deepcopy(row["payload_json"])
        app["gstin_normalized"] = norm_id(row["payload_json"].get("gstin"))
        if row["status"] == "APPROVED" and self._approved_conflict(app):
            raise RuntimeError("approved GSTIN uniqueness conflict")
        app.update(current_status=row["status"], decision_source="AUTOMATED",
                   latest_run_id=row["id"], revision=app["revision"] + 1, updated_at=_now())

    def _commit_review(self, row):
        app = self._app(row["application_id"])
        if app["current_status"] != "PENDING":
            raise RuntimeError("terminal application")
        if row["expected_revision"] != app["revision"] or row["reviewed_run_id"] != app["latest_run_id"]:
            raise RuntimeError("stale_revision")
        row.setdefault("id", str(uuid4()))
        status = {"APPROVE": "APPROVED", "REJECT": "REJECTED", "REQUEST_CORRECTION": "PENDING"}[row["action"]]
        if status == "APPROVED" and self._approved_conflict(app):
            raise RuntimeError("approved GSTIN uniqueness conflict")
        app.update(current_status=status, decision_source="MANUAL",
                   revision=app["revision"] + 1, updated_at=_now())


class _Bucket:
    def __init__(self, storage):
        self.storage = storage

    def upload(self, path, file, file_options):
        if file_options.get("upsert") != "false" or path in self.storage.files:
            raise RuntimeError("object exists")
        self.storage.files[path] = bytes(file)
        return SimpleNamespace(path=path)

    def download(self, path):
        return self.storage.files[path]

    def remove(self, paths):
        for path in paths:
            self.storage.files.pop(path, None)


class _Storage:
    def __init__(self):
        self.files: dict[str, bytes] = {}

    def from_(self, bucket):
        if bucket != "vendor-documents":
            raise RuntimeError("unknown bucket")
        return _Bucket(self)


class InMemorySupabase:
    """Process-local, non-durable. Restarting the server clears every record."""

    def __init__(self):
        self.rows = {name: [] for name in ("applications", "documents", "runs", "review_actions")}
        self.storage = _Storage()
        self.lock = threading.RLock()

    def table(self, name):
        return _Query(self, name)


def _labelled(text: str, *labels: str) -> str | None:
    """Value printed after one of the exact labels ("Label: value" or on the next line)."""
    lines = [line.strip() for line in text.splitlines()]
    for label in labels:
        key = label.casefold() + ":"
        for index, line in enumerate(lines):
            folded = line.casefold()
            if folded == key and index + 1 < len(lines):
                return lines[index + 1]
            if folded.startswith(key) and line[len(key):].strip():
                return line[len(key):].strip()
    return None


class OfflineLabelExtractor:
    """TEST DOUBLE for Gemini: reads labelled lines from the synthetic fixture PDFs.

    It is deliberately literal (no inference), so it exercises the same grounding
    and comparison rules. It is never used when GEMINI_API_KEY is configured.
    """

    last_diagnostic = None

    def extract(self, gst_text: str, bank_text: str) -> ExtractedDocuments:
        return ExtractedDocuments(
            gst=GSTExtraction(
                legal_name=_labelled(gst_text, "Legal business name", "Legal name") if gst_text else None,
                gstin=_labelled(gst_text, "GSTIN") if gst_text else None,
                state=_labelled(gst_text, "Business state", "State") if gst_text else None,
                address=_labelled(gst_text, "Business address") if gst_text else None,
            ),
            bank=BankExtraction(
                holder_name=_labelled(bank_text, "Account holder", "Account holder name") if bank_text else None,
                account_number=_labelled(bank_text, "Account number", "Account no") if bank_text else None,
                ifsc=_labelled(bank_text, "IFSC", "IFSC code") if bank_text else None,
            ),
        )
