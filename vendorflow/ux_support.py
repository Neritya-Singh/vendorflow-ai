"""Side-effect-free guidance for VendorFlow's vendor and staff screens.

These functions only PRESENT saved outcomes. They never approve an application,
change deterministic checks, infer genuine bank/GST verification, or make an
identity-screening result public.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .rules import EMAIL_PATTERN


VENDOR_NAV = ("Welcome", "New application", "Track / correct application")


def valid_contact_email(value: str) -> bool:
    return bool(EMAIL_PATTERN.fullmatch((value or "").strip()))


def _when(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def age_label(value: Any, *, now: datetime | None = None) -> str:
    """Age since intake (not a promise of SLA or an inferred waiting time)."""
    created = _when(value)
    if created is None:
        return "Unknown"
    reference = _when(now) or datetime.now(timezone.utc)
    mins = max(0, int((reference - created).total_seconds() // 60))
    if mins < 60:
        return f"{mins}m"
    if mins < 24 * 60:
        return f"{mins // 60}h"
    return f"{mins // (24 * 60)}d"


def active_review_request(review: dict | None, run: dict | None) -> bool:
    """A previous correction request is no longer active after a newer run."""
    if not review or review.get("action") != "REQUEST_CORRECTION":
        return False
    review_time = _when(review.get("created_at"))
    run_time = _when((run or {}).get("created_at") or (run or {}).get("finished_at"))
    return review_time is None or run_time is None or review_time >= run_time


def _failed_rules(run: dict | None) -> list[dict]:
    return [c for c in ((run or {}).get("checks_json") or [])
            if c.get("state") != "PASS"]


def next_action_owner(application: dict, run: dict | None = None,
                      review: dict | None = None) -> str:
    """Operational task owner, NEVER a fourth decision status.

    Identity-screening clues stay internal; a vendor sees only the owner and
    an appropriately generic follow-up. The reviewer can inspect R12 in staff UI.
    """
    if application.get("current_status") in {"APPROVED", "REJECTED"}:
        return "Complete"
    if not run:
        return "Vendor"  # Resume an interrupted intake with saved credentials.
    if active_review_request(review, run):
        return "Vendor"
    failures = _failed_rules(run)
    actionable = {"R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09", "R10", "R11", "R13"}
    # Extraction outages can make R08–R13 UNKNOWN, but the vendor should not
    # be told to correct accurate business data simply because Gemini failed.
    extraction_outage = bool(run.get("extraction_error")) or any(
        c.get("rule_id") == "R14" and c.get("state") != "PASS" for c in failures)
    if extraction_outage:
        submitted_invalid = any(c.get("state") == "FAIL" and c.get("rule_id") in
                                {"R01", "R02", "R03", "R04", "R05", "R06", "R07"}
                                for c in failures)
        return "Vendor" if submitted_invalid else "Technical retry"
    if any(c.get("rule_id") in actionable for c in failures):
        return "Vendor"
    return "Reviewer"


def vendor_action_heading(application: dict, run: dict | None = None,
                          review: dict | None = None) -> str:
    """Show the vendor an actionable heading, not an internal ownership label."""
    if active_review_request(review, run):
        return "Next step: Make the requested correction"
    if not run:
        return "Next step: Resume your submission"
    from .ui_support import vendor_document_guidance
    document = vendor_document_guidance(run)
    if document:
        return "Next step: " + document[1]
    owner = next_action_owner(application, run, review)
    if owner == "Technical retry":
        return "Next step: Retry the document check"
    if owner == "Reviewer":
        return "Your application is under review"
    if owner == "Vendor":
        return "Next step: Review your details"
    return "Application complete"


def vendor_next_step(application: dict, run: dict | None = None,
                     review: dict | None = None) -> str:
    """Plain-English instruction with no privileged duplicate-GSTIN hints."""
    owner = next_action_owner(application, run, review)
    if owner == "Complete":
        return "No further changes are available for this final decision. Save your receipt."
    if not run:
        return "Resume the same application using your ID and private tracking code. Reupload the PDFs you want checked."
    if active_review_request(review, run):
        return "Your reviewer requested a correction. Update the relevant details or PDF and resubmit."
    if owner == "Technical retry":
        return "Document processing was interrupted. Retry the check with the same application ID or ask the reviewer for help."
    if owner == "Vendor":
        from .ui_support import vendor_document_guidance
        document = vendor_document_guidance(run)
        if document:
            return ('Use "Fix and resubmit" below to upload the correct PDF. '
                    'Your application ID will stay the same.')
        return "Review the issues above, correct the affected details or PDF, then resubmit."
    return "Your application is waiting for staff review. No change is required unless the reviewer requests one."


def primary_review_issue(run: dict | None, review: dict | None = None) -> str:
    """Concise STAFF-only exception reason based on the committed run."""
    if active_review_request(review, run):
        return "Correction requested"
    if not run:
        return "Submission incomplete"
    failures = _failed_rules(run)
    if not failures:
        return "Manual decision needed"
    # Show a business-actionable problem ahead of generic UNKNOWN prerequisites.
    actionable = [c for c in failures if c.get("state") == "FAIL" and c.get("rule_id") != "R12"]
    if actionable:
        return str(actionable[0].get("label") or actionable[0].get("code") or "Evidence needs review")
    if any(c.get("rule_id") == "R12" for c in failures):
        return "Identity screening"  # Staff-only; no prior case ID in queue.
    if run.get("extraction_error"):
        return "Extraction interrupted"
    return str(failures[0].get("label") or "Evidence needs review")


def admin_queue_rows(applications: list[dict], latest_runs: dict[str, dict] | None = None,
                     latest_reviews: dict[str, dict] | None = None,
                     *, now: datetime | None = None) -> list[dict]:
    """Exception-first queue; no extra DB accesses, no decisions taken."""
    from .ui_support import display_status

    latest_runs = latest_runs or {}
    latest_reviews = latest_reviews or {}
    rows = []
    for app in applications:
        app_id = str(app.get("id") or "")
        run = latest_runs.get(str(app.get("latest_run_id") or ""))
        review = latest_reviews.get(app_id)
        rows.append({
            "Application ID": app_id,
            "Business": str((app.get("payload_json") or {}).get("legal_name") or ""),
            "Status": display_status(str(app.get("current_status") or "")),
            "Action owner": next_action_owner(app, run, review),
            "Primary issue": primary_review_issue(run, review) if app.get("current_status") == "PENDING" else "—",
            "Age": age_label(app.get("created_at"), now=now),
        })
    return rows


def committed_pdf_types(run: dict | None) -> list[str]:
    """Only offer downloads for PDF types named in the committed run manifest."""
    manifest = (run or {}).get("document_manifest") or []
    found = []
    for entry in manifest:
        doc_type = entry.get("doc_type")
        if (doc_type in {"GST", "BANK"} and doc_type not in found
                and entry.get("id") and entry.get("storage_path") and entry.get("file_sha256")
                and isinstance(entry.get("version"), int)):
            found.append(doc_type)
    return found


VENDOR_OWNER_LABELS = {
    "Vendor": "you", "Reviewer": "the review team",
    "Technical retry": "you — retry the document check", "Complete": "no one — final decision",
}


def vendor_owner_label(owner: str) -> str:
    """Use plain-language ownership without adding a fourth application status."""
    return VENDOR_OWNER_LABELS.get(owner, "the review team")


def selected_review_case(rows: list[dict], selected_positions: list[int]) -> str | None:
    """Fail closed on stale/invalid dataframe row selection; never pick another case.

    The UI still requires manual ID confirmation before any review mutation.
    """
    if len(selected_positions) != 1:
        return None
    pos = selected_positions[0]
    if type(pos) is not int or pos < 0 or pos >= len(rows):
        return None
    case_id = rows[pos].get("Application ID")
    return case_id if isinstance(case_id, str) and case_id.startswith("VF-") else None


def admin_review_issue_groups(checks: list[dict]) -> tuple[list[dict], list[dict]]:
    """Order reviewer-only findings: actual failures, then unknown evidence.

    Never silently discard an unresolved check. The UI shows the three most
    important findings and allows expansion of the rest; all remain inspectable.
    This function does not modify or reinterpret backend check states.
    """
    failures: list[dict] = []
    unverified: list[dict] = []
    for check in checks:
        state = str(check.get("state") or "UNKNOWN")
        if state == "PASS":
            continue
        rule = str(check.get("rule_id") or "")
        label = str(check.get("label") or "Check needs review")
        if rule == "R12":
            label = "Possible duplicate of an approved vendor"
        elif rule == "R01" and state == "FAIL":
            label = "Missing submission details"
        elif rule == "R02" and state == "FAIL":
            label = "Document evidence needed"
        note = str(check.get("admin_detail") or check.get("vendor_message")
                   or "This check requires a reviewer.").strip()
        # Rules intentionally emit imperative 'Complete: ...' and 'Upload: ...'.
        # Plain-English staff phrasing makes those actions unambiguous.
        if note.startswith("Complete: "):
            note = "Ask the vendor to provide: " + note[len("Complete: "):]
        elif note.startswith("Upload: "):
            note = "Ask the vendor to upload: " + note[len("Upload: "):]
        item = {"state": state, "rule_id": rule, "label": label, "note": note}
        (failures if state == "FAIL" else unverified).append(item)
    return failures, unverified
