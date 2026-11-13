"""Read-only view models built from SAVED records via the v1.1 presentation helpers.

Nothing here approves, rejects or re-scores an application. Vendor views never
expose the R12 identity-screening result, other case IDs, raw rule codes or
reviewer-only evidence.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from vendorflow.models import WorkflowResult
from vendorflow import v2_policy as v2
from vendorflow.ui_support import (
    comparison_assessments, completed_counts, display_status, selected_reasons, vendor_safe_review_reason,
)
from vendorflow.ux_support import (
    active_review_request, admin_review_issue_groups, age_label, committed_pdf_types,
)

STAGES = [
    ("S1", "Intake"), ("S2", "PDF reading"), ("S3", "Gemini extraction"),
    ("S4", "Normalization"), ("S5", "Deterministic rules"), ("S6", "Identity screening"),
    ("S7", "Decision routing"), ("S8", "Explanation"), ("S9", "Persistence"),
]

REVIEW_ACTION_LABELS = {"APPROVE": "Approved by reviewer", "REJECT": "Rejected by reviewer",
                        "REQUEST_CORRECTION": "Reviewer requested a correction"}


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def result_as_run(result: WorkflowResult, manifest: list[dict] | None = None) -> dict:
    """The same shape as a saved `runs` row, built from an in-flight result."""
    return {
        "id": result.run_id, "trigger": result.trigger, "status": result.status.value,
        "checks_json": [c.model_dump(mode="json") for c in result.checks],
        "reasons_json": list(result.reasons), "all_reasons_json": list(result.all_reasons),
        "extraction_error": result.extraction_error,
        "stages_json": [e.model_dump(mode="json") for e in result.stage_events],
        "extracted_json": result.extracted.model_dump(mode="json"),
        "started_at": _iso(result.started_at), "finished_at": _iso(result.finished_at),
        "created_at": _iso(result.finished_at), "elapsed_ms": result.elapsed_ms,
        "document_manifest": manifest or [],
    }


def stage_summary(events: list[dict]) -> list[dict]:
    """Collapse saved STARTED/COMPLETED/... events into one row per real stage."""
    rows = []
    for stage_id, label in STAGES:
        mine = [e for e in events if e.get("stage_id") == stage_id]
        started = next((e for e in mine if e.get("event") == "STARTED"), None)
        final = next((e for e in reversed(mine) if e.get("event") != "STARTED"), None)
        state = final.get("event") if final else ("STARTED" if started else "NOT_RUN")
        duration = None
        if started and final:
            try:
                a = datetime.fromisoformat(str(started["timestamp"]).replace("Z", "+00:00"))
                b = datetime.fromisoformat(str(final["timestamp"]).replace("Z", "+00:00"))
                duration = max(0, round((b - a).total_seconds() * 1000))
            except (KeyError, ValueError):
                duration = None
        rows.append({"stage_id": stage_id, "label": label, "state": state,
                     "note": (final or started or {}).get("note", ""),
                     "started_at": (started or {}).get("timestamp"),
                     "finished_at": (final or {}).get("timestamp"), "duration_ms": duration})
    return rows


VENDOR_REVIEW_LABELS = {"APPROVE": "Approved by our team", "REJECT": "Not approved by our team",
                        "REQUEST_CORRECTION": "Our team asked for a change"}


# Vendor wording for the same nine real stages (V2_02 §5): no internal captions.
VENDOR_STAGES = {
    "S1": "Received", "S2": "Opened your documents", "S3": "Read the details", "S4": "Prepared the details",
    "S5": "Checked formats and compared documents", "S6": "Checked our records", "S7": "Decided",
    "S8": "Prepared your result", "S9": "Saved",
}


def vendor_stage_rows(events: list[dict]) -> list[dict]:
    """Stage rows for vendor screens: real states and timings, but no internal notes."""
    return [{**row, "label": VENDOR_STAGES[row["stage_id"]], "note": ""} for row in stage_summary(events)]


def vendor_view(record: dict, runs: list[dict], reviews: list[dict], *, buyer: str = "Zamp AI") -> dict:
    """Vendor-safe status: who acts next and exactly what is needed (V2_02 §6–9).

    Never includes rule IDs, check states, identity-screening results, other case
    IDs or internal stage notes.
    """
    status = str(record.get("current_status") or "PENDING")
    latest_run = runs[0] if runs else None
    latest_review = reviews[0] if reviews else None
    owner = v2.case_owner(record, latest_run, latest_review)
    correction = active_review_request(latest_review, latest_run)
    review_reason = vendor_safe_review_reason(str((latest_review or {}).get("reason") or ""))
    todo: list[dict] = []
    retry_available = False

    if status == "APPROVED":
        status_label, heading = "Approved", "You're approved"
        messages = [f"Your business is approved as a supplier to {buyer}."]
        next_step = "Nothing else is needed from you. Keep your application ID for reference."
    elif status == "REJECTED":
        status_label, heading = "Not approved", "Not approved"
        messages = [f"We couldn't approve your application: {review_reason}" if review_reason
                    else "We couldn't approve your application."]
        next_step = f"This decision is final. If you have questions, contact {buyer}'s finance team."
    elif owner == v2.DRAFT:
        status_label, heading = v2.VENDOR_STATUS_LABELS[owner], "Continue your application"
        messages = ["Your application was started but not checked yet."]
        next_step = "Upload your documents again and submit them for checking. Your application ID stays the same."
    elif owner == v2.VENDOR:
        status_label = heading = v2.VENDOR_STATUS_LABELS[owner]
        if correction:
            todo.append({"key": "correction", "text": f"Our team needs one change: {review_reason}"})
        todo.extend({"key": i["key"], "text": i["text"]} for i in v2.vendor_items(latest_run))
        count = len(todo)
        messages = [f"We need {'one thing' if count == 1 else f'{count} things'} before we can continue."]
        next_step = "Fix the items listed, then submit for checking again. Your application ID stays the same."
    else:
        status_label = v2.VENDOR_STATUS_LABELS[v2.TEAM]
        heading = "With our team — no action needed"
        messages = [v2.vendor_team_message(latest_run)]
        next_step = "We'll message you here when there's an update."
        if v2.extraction_outage(latest_run):
            retry_available = True
            next_step = ("Our team will look at it. You can also try the check again now — "
                         "nothing needs to change and your application ID stays the same.")

    reviewer_note = None
    # A final reviewer decision always shows; a correction request only while active.
    if latest_review and (
        (latest_review.get("action") != "REQUEST_CORRECTION" and record.get("decision_source") == "MANUAL")
        or correction
    ):
        reviewer_note = {
            "action": latest_review.get("action"),
            "title": VENDOR_REVIEW_LABELS.get(str(latest_review.get("action")), "Message from our team"),
            "message": review_reason,
            "at": _iso(latest_review.get("created_at")),
        }

    timeline = []
    for run in runs:
        timeline.append({
            "kind": "run", "at": _iso(run.get("created_at") or run.get("finished_at")),
            "title": "Checked your application" if run.get("trigger") == "submission" else "Checked your changes",
            "status": run.get("status"), "status_label": display_status(str(run.get("status") or "")),
            "elapsed_ms": run.get("elapsed_ms"),
            "documents": [{"doc_type": d.get("doc_type"), "version": d.get("version")}
                          for d in run.get("document_manifest") or []],
        })
    for review in reviews:
        timeline.append({
            "kind": "review", "at": _iso(review.get("created_at")),
            "title": VENDOR_REVIEW_LABELS.get(str(review.get("action")), "Message from our team"),
            "status": {"APPROVE": "APPROVED", "REJECT": "REJECTED"}.get(str(review.get("action")), "PENDING"),
            "message": vendor_safe_review_reason(str(review.get("reason") or "")),
        })
    timeline.sort(key=lambda item: item.get("at") or "", reverse=True)

    return {
        "application_id": record.get("id"),
        "status": status, "status_label": status_label,
        "decision_source": record.get("decision_source") or "AUTOMATED",
        "owner": owner, "processing_unavailable": retry_available, "retry_available": retry_available,
        "heading": heading, "next_step": next_step, "reasons": messages, "todo": todo,
        "reviewer_note": reviewer_note,
        "stages": vendor_stage_rows((latest_run or {}).get("stages_json") or []),
        "elapsed_ms": (latest_run or {}).get("elapsed_ms"),
        "timeline": timeline,
        "documents": [{"doc_type": d.get("doc_type"), "version": d.get("version")}
                      for d in (latest_run or {}).get("document_manifest") or []],
        # Only the vendor's own to-do opens the edit form; "with our team" never does.
        "editable": status == "PENDING" and owner == v2.VENDOR,
        "needs_resume": status == "PENDING" and owner == v2.DRAFT,
        "revision": int(record.get("revision") or 0),
        "latest_run_id": record.get("latest_run_id"),
        "submitted": record.get("payload_json") or {},
        "created_at": _iso(record.get("created_at")),
    }


def receipt_view(application_id: str, result: WorkflowResult, vendor: dict, manifest: list[dict],
                 *, buyer: str = "Zamp AI") -> dict:
    record = {"id": application_id, "current_status": result.status.value,
              "decision_source": "AUTOMATED", "payload_json": vendor,
              "latest_run_id": result.run_id, "revision": None}
    view = vendor_view(record, [result_as_run(result, manifest)], [], buyer=buyer)
    view["persisted"] = result.persisted
    view.pop("revision")
    return view


# ---------------------------------------------------------------- admin views

def _review_dict(row: dict) -> dict:
    return {"action": row.get("action"), "label": REVIEW_ACTION_LABELS.get(str(row.get("action")), row.get("action")),
            "reason": row.get("reason"), "actor": row.get("actor"),
            "reviewed_run_id": row.get("reviewed_run_id"), "created_at": _iso(row.get("created_at"))}


TAB_ORDER = {"NEEDS_REVIEW": 0, "WAITING_ON_VENDOR": 1, "APPROVED": 2, "REJECTED": 3}


def _latest_reviews(review_rows: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for row in sorted(review_rows, key=lambda r: str(r.get("created_at") or ""), reverse=True):
        latest.setdefault(row.get("application_id"), row)
    return latest


def admin_overview(apps: list[dict], run_rows: list[dict], review_rows: list[dict]) -> dict:
    """Reviewer queue with ownership tabs. Drafts (zero runs) are excluded from the
    queue and from every metric."""
    latest_runs = {r["id"]: r for r in run_rows if r.get("id")}
    latest_reviews = _latest_reviews(review_rows)
    queue = []
    submitted = []
    for app in apps:
        run = latest_runs.get(str(app.get("latest_run_id") or ""))
        summary = v2.staff_summary(app, run, latest_reviews.get(app.get("id")))
        tab = v2.queue_tab(app, summary["owner"])
        if tab is None:
            continue
        submitted.append(app)
        waiting_since = app.get("updated_at") or app.get("created_at")
        queue.append({
            "application_id": app.get("id"),
            "business": str((app.get("payload_json") or {}).get("legal_name") or ""),
            "gstin": str(app.get("gstin_normalized") or (app.get("payload_json") or {}).get("gstin") or ""),
            "status": app.get("current_status"), "status_label": display_status(str(app.get("current_status") or "")),
            "decision_source": app.get("decision_source"),
            "owner": summary["owner"], "owner_label": v2.STAFF_OWNER_LABELS[summary["owner"]],
            "tab": tab, "reason": summary["reason"], "risk": summary["risk"],
            "age": age_label(waiting_since),
            "created_at": _iso(app.get("created_at")), "updated_at": _iso(app.get("updated_at")),
            "waiting_since": _iso(waiting_since),
            "elapsed_ms": (run or {}).get("elapsed_ms"),
        })
    # Risk first, then the longest wait.
    queue.sort(key=lambda r: (TAB_ORDER[r["tab"]], v2.RISK_ORDER[r["risk"]], r["waiting_since"] or ""))
    submitted_ids = {a.get("id") for a in submitted}
    counts = completed_counts(submitted, [r for r in run_rows if r.get("application_id") in submitted_ids])
    tabs = {tab: sum(r["tab"] == tab for r in queue) for tab in TAB_ORDER}
    oldest = next((r for r in sorted(queue, key=lambda r: r["waiting_since"] or "") if r["tab"] == "NEEDS_REVIEW"), None)
    metrics = {**counts, "needs_review": tabs["NEEDS_REVIEW"], "waiting_on_vendor": tabs["WAITING_ON_VENDOR"],
               "oldest_needs_review": oldest["age"] if oldest else None}
    return {"metrics": metrics, "queue": queue}


def _run_detail(run: dict) -> dict:
    return {
        "id": run.get("id"), "trigger": run.get("trigger"), "status": run.get("status"),
        "status_label": display_status(str(run.get("status") or "")),
        "created_at": _iso(run.get("created_at")), "started_at": _iso(run.get("started_at")),
        "finished_at": _iso(run.get("finished_at")), "elapsed_ms": run.get("elapsed_ms"),
        "extraction_error": bool(run.get("extraction_error")),
        "reasons": run.get("reasons_json") or [],
        "stages": stage_summary(run.get("stages_json") or []),
        "events": run.get("stages_json") or [],
        "documents": [{"doc_type": d.get("doc_type"), "version": d.get("version"),
                       "sha256_prefix": str(d.get("file_sha256") or "")[:16]}
                      for d in run.get("document_manifest") or []],
        "pdf_types": committed_pdf_types(run),
    }


def _case_summary(app: dict, run: dict | None, review: dict | None) -> dict:
    summary = v2.staff_summary(app, run, review)
    return {
        "owner": summary["owner"], "owner_label": v2.STAFF_OWNER_LABELS[summary["owner"]],
        "primary_issue": summary["reason"], "risk": summary["risk"],
        "flags": v2.team_flags(run) if summary["owner"] == v2.TEAM else [],
        "vendor_items": [{"short": i["short"], "text": i["text"]} for i in v2.vendor_items(run)],
    }


def admin_case(app: dict, runs: list[dict], reviews: list[dict]) -> dict:
    latest_run = runs[0] if runs else None
    latest_review = reviews[0] if reviews else None
    checks = (latest_run or {}).get("checks_json") or []
    failed, unverified = admin_review_issue_groups(checks)
    payload = app.get("payload_json") or {}
    return {
        "application_id": app.get("id"), "business": payload.get("legal_name") or "",
        "status": app.get("current_status"), "status_label": display_status(str(app.get("current_status") or "")),
        "decision_source": app.get("decision_source"), "revision": int(app.get("revision") or 0),
        "latest_run_id": app.get("latest_run_id"),
        "created_at": _iso(app.get("created_at")), "updated_at": _iso(app.get("updated_at")),
        "contact": {"name": payload.get("contact_name") or "", "email": payload.get("contact_email") or "",
                    "state": payload.get("business_state") or ""},
        "reasons": selected_reasons(app, runs, reviews, audience="admin"),
        **_case_summary(app, latest_run, latest_review),
        "issues": {"failed": failed, "unverified": unverified},
        "comparison": comparison_assessments(payload, (latest_run or {}).get("extracted_json") or {}, checks)
        if latest_run else [],
        "checks": [{"rule_id": c.get("rule_id"), "label": c.get("label"), "state": c.get("state"),
                    "evidence": c.get("admin_detail") or c.get("vendor_message") or ""} for c in checks],
        "runs": [_run_detail(r) for r in runs],
        "reviews": [_review_dict(r) for r in reviews],
        "can_review": app.get("current_status") == "PENDING" and bool(latest_run),
        "active_correction_request": active_review_request(latest_review, latest_run),
    }


def unmasked_comparison(payload: dict, extracted: dict) -> list[dict]:
    gst, bank = (extracted or {}).get("gst") or {}, (extracted or {}).get("bank") or {}
    pairs = [("GST legal name", "legal_name", gst.get("legal_name")),
             ("GSTIN", "gstin", gst.get("gstin")), ("GST state", "business_state", gst.get("state")),
             ("Account holder", "bank_holder", bank.get("holder_name")),
             ("Bank account", "account_number", bank.get("account_number")),
             ("IFSC", "ifsc", bank.get("ifsc"))]
    return [{"Field": label, "Submitted": payload.get(key) or "Not supplied", "From PDF": found or "Not found"}
            for label, key, found in pairs]


SAFE_FILENAME = re.compile(r"[^A-Za-z0-9_.-]")
