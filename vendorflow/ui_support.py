"""Side-effect-free presentation helpers for VendorFlow AI's Streamlit demo UI.

The UI never uses these to make approval decisions; the persisted Python rules do.
"""
from __future__ import annotations

from collections import Counter
import re
from typing import Any

LABELS = {"APPROVED": "Approved", "PENDING": "Pending Review", "REJECTED": "Rejected"}
ICONS = {"APPROVED": "✅", "PENDING": "⚠️", "REJECTED": "❌"}


def display_status(status: str) -> str:
    return f"{ICONS.get(status, 'ℹ️')} {LABELS.get(status, 'Processing')}"


def mask_sensitive(value: Any, visible: int = 4) -> str:
    """Mask bank/tax identifiers in UI. Empty source must not look verified."""
    string = str(value or "").strip()
    if not string:
        return "Not found"
    if len(string) <= visible:
        return "•" * len(string)
    return "•" * (len(string) - visible) + string[-visible:]


def selected_reasons(application: dict, runs: list[dict], reviews: list[dict], *, audience: str = "admin") -> list[str]:
    """Manually reviewed status is explained by the latest human action, not old AI checks."""
    if application.get("decision_source") == "MANUAL" and reviews:
        action = reviews[0].get("action", "")
        reason = reviews[0].get("reason", "")
        verb = {"APPROVE": "Approved after human review", "REJECT": "Rejected by reviewer",
                "REQUEST_CORRECTION": "Reviewer requested correction"}.get(action, "Reviewed")
        return [f"{verb}: {vendor_safe_review_reason(reason) if audience == 'vendor' else reason}"] if reason else [verb]
    if runs:
        return list(runs[0].get("reasons_json") or [])
    return ["No completed automated evaluation is available yet."]



def vendor_visible_checks(checks: list[dict]) -> list[dict]:
    """Public checks never reveal the existence of a matching registration."""
    return [check for check in checks if check.get("rule_id") != "R12"]


def vendor_safe_review_reason(reason: str) -> str:
    """Never render private case identifiers from free-text admin reasons."""
    if re.search(r"(?i)\b(duplicate|already\s+registered|prior\s+application|existing\s+vendor)\b|VF-[A-Z0-9-]{4,}", reason or ""):
        return "Please contact the review team for details of this decision."
    return reason

def completed_counts(applications: list[dict], runs: list[dict]) -> dict[str, float | int | None]:
    status_counts = Counter(row.get("current_status") for row in applications)
    times = [int(row["elapsed_ms"]) for row in runs if isinstance(row.get("elapsed_ms"), (int, float))]
    return {
        "total": len(applications),
        "approved": status_counts["APPROVED"],
        "pending": status_counts["PENDING"],
        "rejected": status_counts["REJECTED"],
        "run_count": len(times),
        "mean_seconds": round(sum(times) / len(times) / 1000, 2) if times else None,
    }


def comparison_rows(claimed: dict, extracted: dict) -> list[dict[str, str]]:
    gst = (extracted or {}).get("gst") or {}
    bank = (extracted or {}).get("bank") or {}
    return [
        {"Field": "GST legal name", "Submitted": claimed.get("legal_name") or "Not supplied",
         "From PDF": gst.get("legal_name") or "Not found"},
        {"Field": "GSTIN (masked)", "Submitted": mask_sensitive(claimed.get("gstin")),
         "From PDF": mask_sensitive(gst.get("gstin"))},
        {"Field": "GST state", "Submitted": claimed.get("business_state") or "Not supplied",
         "From PDF": gst.get("state") or "Not found"},
        {"Field": "Account holder", "Submitted": claimed.get("bank_holder") or "Not supplied",
         "From PDF": bank.get("holder_name") or "Not found"},
        {"Field": "Bank account (masked)", "Submitted": mask_sensitive(claimed.get("account_number")),
         "From PDF": mask_sensitive(bank.get("account_number"))},
        {"Field": "IFSC (masked)", "Submitted": mask_sensitive(claimed.get("ifsc")),
         "From PDF": mask_sensitive(bank.get("ifsc"))},
    ]


def comparison_assessments(claimed: dict, extracted: dict,
                           checks: list[dict]) -> list[dict[str, str]]:
    """UI-only documentary comparisons; no approval decisions are made here.

    Sensitive identifiers remain masked via comparison_rows(). The underlying
    values are compared before masking so identical last-four digits cannot
    conceal a discrepancy. A matching PDF is NOT official identity verification.
    """
    import re

    gst = (extracted or {}).get("gst") or {}
    bank = (extracted or {}).get("bank") or {}
    raw_pairs = [
        (claimed.get("legal_name"), gst.get("legal_name")),
        (claimed.get("gstin"), gst.get("gstin")),
        (claimed.get("business_state"), gst.get("state")),
        (claimed.get("bank_holder"), bank.get("holder_name")),
        (claimed.get("account_number"), bank.get("account_number")),
        (claimed.get("ifsc"), bank.get("ifsc")),
    ]
    ownership_check = next((c for c in checks if c.get("rule_id") == "R11"), {})

    def normalized(value: Any) -> str:
        return re.sub(r"[^\w]+", "", str(value or "").casefold())

    output = []
    for index, (row, (submitted, documentary)) in enumerate(
            zip(comparison_rows(claimed, extracted), raw_pairs)):
        if not str(submitted or "").strip() or not str(documentary or "").strip():
            assessment, kind = "Missing evidence", "missing"
        elif normalized(submitted) != normalized(documentary):
            assessment, kind = "Different", "flag"
        elif index == 3 and ownership_check.get("state") != "PASS":
            # The bank-letter name can match the claim yet differ from the
            # legal entity, as in our synthetic trade-name ambiguity fixture.
            assessment, kind = "Review ownership", "flag"
        else:
            assessment, kind = "Consistent", "ok"
        output.append({**row, "Assessment": assessment, "Kind": kind})
    return output


def stage_rows(events: list[dict]) -> list[dict]:
    icons = {"STARTED": "⏳", "COMPLETED": "✓", "FAILED": "✕", "SKIPPED": "–"}
    return [{"Stage": e.get("label") or e.get("stage_id", ""),
             "Result": f"{icons.get(e.get('event'), '?')} {e.get('event', 'UNKNOWN')}",
             "Details": e.get("note") or "",
             "Time": str(e.get("timestamp", ""))[:19]}
            for e in events if e.get("event") != "STARTED"]
