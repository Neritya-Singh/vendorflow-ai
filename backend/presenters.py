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
from vendorflow.ui_support import (
    comparison_assessments, completed_counts, display_status, selected_reasons,
    vendor_document_guidance, vendor_safe_review_reason, vendor_visible_checks,
)
from vendorflow.ux_support import (
    active_review_request, admin_queue_rows, admin_review_issue_groups, committed_pdf_types,
    next_action_owner, primary_review_issue, vendor_action_heading, vendor_next_step,
)

STAGES = [
    ("S1", "Intake"), ("S2", "PDF reading"), ("S3", "Gemini extraction"),
    ("S4", "Normalization"), ("S5", "Deterministic rules"), ("S6", "Identity screening"),
    ("S7", "Decision routing"), ("S8", "Explanation"), ("S9", "Persistence"),
]

PROCESSING_UNAVAILABLE = ("Document processing was temporarily unavailable, so your PDFs have not been "
                          "checked yet. This is not a problem with your documents. Retry the check — "
                          "your application ID stays the same.")
EVIDENCE_UNCONFIRMED = ("We couldn't confirm all the details from the uploaded PDFs. Check that your "
                        "documents are complete and readable, then replace any unclear file.")
REVIEW_ACTION_LABELS = {"APPROVE": "Approved by reviewer", "REJECT": "Rejected by reviewer",
                        "REQUEST_CORRECTION": "Reviewer requested a correction"}
INPUT_RULES = {"R01", "R03", "R04", "R05", "R06", "R07"}


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


def _vendor_checks(run: dict, owner: str) -> list[dict]:
    document = vendor_document_guidance(run)
    outage = owner == "Technical retry"
    rows = []
    for check in vendor_visible_checks(run.get("checks_json") or []):
        state, rule = check.get("state", "UNKNOWN"), check.get("rule_id")
        if document and ((rule in {"R08", "R09", "R10", "R11"} and state == "UNKNOWN")
                         or (rule in {"R13", "R14"} and state != "PASS")):
            continue  # Secondary effects of a missing/unreadable PDF are not repeated.
        if outage and rule in {"R08", "R09", "R10", "R11", "R13"} and state != "PASS":
            detail, state = "Not checked yet — document processing was unavailable.", "UNKNOWN"
        elif state == "PASS":
            detail = "Passed"
        elif document and rule == "R02":
            detail = document[0]
        elif rule == "R13":
            detail = EVIDENCE_UNCONFIRMED
        elif rule == "R14" and outage:
            detail = PROCESSING_UNAVAILABLE
        else:
            detail = check.get("vendor_message") or "Requires review"
        rows.append({"label": check.get("label") or "Check", "state": state, "detail": detail})
    return rows


def vendor_view(record: dict, runs: list[dict], reviews: list[dict]) -> dict:
    status = str(record.get("current_status") or "PENDING")
    latest_run = runs[0] if runs else None
    latest_review = reviews[0] if reviews else None
    owner = next_action_owner(record, latest_run, latest_review)
    reasons = selected_reasons(record, runs, reviews, audience="vendor")
    if owner == "Technical retry" and record.get("decision_source") != "MANUAL":
        independent = [c.get("vendor_message") for c in (latest_run or {}).get("checks_json") or []
                       if c.get("rule_id") in INPUT_RULES and c.get("state") == "FAIL"]
        reasons = [PROCESSING_UNAVAILABLE, *[m for m in independent if m]][:3]
    if status == "APPROVED":
        heading = "Application approved"
        detail = ("Your details match your documents under our onboarding checks. "
                  "No further action is required — keep your receipt for reference.")
    elif status == "REJECTED":
        heading = "Application not approved"
        detail = ("A reviewer has made a final decision. Read the reason above. "
                  "Contact the review team if you need help; this application can no longer be changed.")
    else:
        heading = vendor_action_heading(record, latest_run, latest_review)
        heading = heading.replace("Next step: ", "")
        detail = vendor_next_step(record, latest_run, latest_review)
        if owner == "Technical retry":
            heading = "Retry the document check"
            detail = ("Document processing is temporarily unavailable. Retry the check from your tracking page without "
                      "changing anything; your application ID and tracking code stay the same.")

    reviewer_note = None
    # A final reviewer decision always shows; a correction request only while it is
    # still active (a newer automated run supersedes it).
    if latest_review and (
        (latest_review.get("action") != "REQUEST_CORRECTION" and record.get("decision_source") == "MANUAL")
        or active_review_request(latest_review, latest_run)
    ):
        reviewer_note = {
            "action": latest_review.get("action"),
            "title": REVIEW_ACTION_LABELS.get(str(latest_review.get("action")), "Reviewer note"),
            "message": vendor_safe_review_reason(str(latest_review.get("reason") or "")),
            "at": _iso(latest_review.get("created_at")),
        }

    timeline = []
    for run in runs:
        timeline.append({
            "kind": "run", "at": _iso(run.get("created_at") or run.get("finished_at")),
            "title": "Initial check" if run.get("trigger") == "submission" else "Re-check after correction",
            "status": run.get("status"), "status_label": display_status(str(run.get("status") or "")),
            "elapsed_ms": run.get("elapsed_ms"),
            "documents": [{"doc_type": d.get("doc_type"), "version": d.get("version")}
                          for d in run.get("document_manifest") or []],
        })
    for review in reviews:
        timeline.append({
            "kind": "review", "at": _iso(review.get("created_at")),
            "title": REVIEW_ACTION_LABELS.get(str(review.get("action")), "Reviewer action"),
            "status": {"APPROVE": "APPROVED", "REJECT": "REJECTED"}.get(str(review.get("action")), "PENDING"),
            "message": vendor_safe_review_reason(str(review.get("reason") or "")),
        })
    timeline.sort(key=lambda item: item.get("at") or "", reverse=True)

    return {
        "application_id": record.get("id"),
        "status": status, "status_label": display_status(status),
        "decision_source": record.get("decision_source") or "AUTOMATED",
        "owner": owner, "processing_unavailable": owner == "Technical retry",
        "heading": heading, "next_step": detail, "reasons": reasons[:3],
        "reviewer_note": reviewer_note,
        "checks": _vendor_checks(latest_run, owner) if latest_run else [],
        "stages": stage_summary((latest_run or {}).get("stages_json") or []),
        "elapsed_ms": (latest_run or {}).get("elapsed_ms"),
        "timeline": timeline,
        "documents": [{"doc_type": d.get("doc_type"), "version": d.get("version")}
                      for d in (latest_run or {}).get("document_manifest") or []],
        "editable": status == "PENDING" and bool(latest_run),
        "needs_resume": status == "PENDING" and not latest_run,
        "revision": int(record.get("revision") or 0),
        "latest_run_id": record.get("latest_run_id"),
        "submitted": record.get("payload_json") or {},
        "created_at": _iso(record.get("created_at")),
    }


def receipt_view(application_id: str, result: WorkflowResult, vendor: dict, manifest: list[dict]) -> dict:
    record = {"id": application_id, "current_status": result.status.value,
              "decision_source": "AUTOMATED", "payload_json": vendor,
              "latest_run_id": result.run_id, "revision": None}
    view = vendor_view(record, [result_as_run(result, manifest)], [])
    view["persisted"] = result.persisted
    view.pop("revision")
    return view


# ---------------------------------------------------------------- admin views

def _review_dict(row: dict) -> dict:
    return {"action": row.get("action"), "label": REVIEW_ACTION_LABELS.get(str(row.get("action")), row.get("action")),
            "reason": row.get("reason"), "actor": row.get("actor"),
            "reviewed_run_id": row.get("reviewed_run_id"), "created_at": _iso(row.get("created_at"))}


def admin_overview(apps: list[dict], run_rows: list[dict], review_rows: list[dict]) -> dict:
    latest_runs = {r["id"]: r for r in run_rows if r.get("id")}
    latest_reviews: dict[str, dict] = {}
    for row in sorted(review_rows, key=lambda r: str(r.get("created_at") or ""), reverse=True):
        latest_reviews.setdefault(row.get("application_id"), row)
    ordered = sorted(apps, key=lambda a: (a.get("current_status") != "PENDING", str(a.get("created_at") or "")))
    rows = admin_queue_rows(ordered, latest_runs, latest_reviews)
    queue = []
    for app, row in zip(ordered, rows):
        run = latest_runs.get(str(app.get("latest_run_id") or ""))
        queue.append({
            "application_id": row["Application ID"], "business": row["Business"],
            "status": app.get("current_status"), "status_label": row["Status"],
            "decision_source": app.get("decision_source"),
            "owner": row["Action owner"], "primary_issue": row["Primary issue"], "age": row["Age"],
            "created_at": _iso(app.get("created_at")), "updated_at": _iso(app.get("updated_at")),
            "elapsed_ms": (run or {}).get("elapsed_ms"),
            "has_run": bool(run),
        })
    counts = completed_counts(apps, run_rows)
    return {"metrics": counts, "queue": queue}


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
        "owner": next_action_owner(app, latest_run, latest_review),
        "primary_issue": primary_review_issue(latest_run, latest_review),
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
