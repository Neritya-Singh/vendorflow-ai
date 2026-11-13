"""VendorFlow v2 ownership and wording policy (V2_02 §6, V2_01 §6–7).

Read-only presentation logic over SAVED runs. It never changes a check result,
an application status or a decision. The three external statuses stay
APPROVED / PENDING / REJECTED; this module only says WHO acts next on a
pending case and how that is worded for the vendor and the reviewer.

Ownership rule (V2_02 §6):
  1. Any vendor-fixable problem (missing, unreadable, wrong or swapped document;
     format; missing details; details we could not confirm from the document)
     -> waiting on the vendor. Only the vendor's items are shown.
  2. Otherwise any reviewer-owned flag (name differs from bank holder, a value
     that differs from the document, duplicate GSTIN, bank reuse, extraction
     outage, records check unavailable) -> with our team.
  3. A reviewer's active correction request always puts the case with the vendor.

The v1.1 helpers in ux_support/ui_support are left unchanged for the Streamlit app.
"""
from __future__ import annotations

import re

from .ux_support import active_review_request

DRAFT, VENDOR, TEAM, COMPLETE = "DRAFT", "VENDOR", "TEAM", "COMPLETE"
HIGH, MEDIUM, LOW = "HIGH", "MEDIUM", "LOW"
RISK_ORDER = {HIGH: 0, MEDIUM: 1, LOW: 2, None: 3}

# Rules whose FAIL the vendor can fix by typing or uploading.
VENDOR_INPUT_RULES = ("R01", "R03", "R04", "R05", "R06", "R07")
SWAPPED_MARKER = "opposite slots"

VENDOR_STATUS_LABELS = {
    DRAFT: "Continue your application",
    VENDOR: "Action needed from you",
    TEAM: "With our team",
}
STAFF_OWNER_LABELS = {DRAFT: "Draft", VENDOR: "Waiting on vendor", TEAM: "Needs review", COMPLETE: "Complete"}

TEAM_MESSAGE = ("Thanks, your application is with our team for a final check. "
                "No action is needed from you. We'll message you here.")
ADDITIONAL_CHECK = "Our team is completing an additional check. No action is needed from you."
OUTAGE_MESSAGE = ("We couldn't read your documents just now because of a temporary problem on our side. "
                  "This isn't a problem with your documents.")

_DOC_NAMES = {"GST certificate": "GST certificate", "Bank proof": "bank document"}


def _checks(run: dict | None) -> list[dict]:
    return list((run or {}).get("checks_json") or [])


def _by_rule(run: dict | None) -> dict[str, dict]:
    return {str(c.get("rule_id")): c for c in _checks(run)}


def _failed(check: dict | None) -> bool:
    return bool(check) and check.get("state") == "FAIL"


def _not_pass(check: dict | None) -> bool:
    return bool(check) and check.get("state") != "PASS"


def documents_swapped(run: dict | None) -> bool:
    r02 = _by_rule(run).get("R02")
    return _failed(r02) and SWAPPED_MARKER in str(r02.get("vendor_message") or "")


def extraction_outage(run: dict | None) -> bool:
    """Gemini/provider failure (not a swapped-file skip)."""
    if not run:
        return False
    r14 = _by_rule(run).get("R14")
    return bool(run.get("extraction_error")) or (_not_pass(r14) and not documents_swapped(run))


def _names(listing: str) -> list[str]:
    return [part.strip() for part in listing.rstrip(".").split(",") if part.strip()]


def _document_items(message: str) -> list[dict]:
    if SWAPPED_MARKER in message:
        return [{"key": "swapped", "short": "Files look swapped",
                 "text": "Your files look swapped. Put the GST certificate in the GST slot and the "
                         "bank document in the bank slot."}]
    items = []
    if message.startswith("Upload:"):
        for name in _names(message[len("Upload:"):]):
            label = _DOC_NAMES.get(name, name)
            items.append({"key": f"missing:{name}", "short": f"Missing {label}",
                          "text": f"Upload your {label}."})
    elif message.startswith("Replace unreadable document(s):"):
        for name in _names(message[len("Replace unreadable document(s):"):]):
            label = _DOC_NAMES.get(name, name)
            items.append({"key": f"unclear:{name}", "short": f"Unclear {label}",
                          "text": f"We couldn't read your {label}. Upload a clearer copy."})
    return items or [{"key": "documents", "short": "Document problem",
                      "text": "Check your uploaded documents and upload them again."}]


_INPUT_TEXT = {
    "R03": ("PAN format", "Check your PAN. It should be 10 characters, like ABCDE1234F."),
    "R04": ("GSTIN format", "Check your GSTIN. It should be 15 characters, like 27ABCDE1234F1Z5."),
    "R05": ("PAN does not match GSTIN", "Your PAN doesn't match the PAN inside your GSTIN. Check both numbers."),
    "R06": ("GSTIN state code", "Your GSTIN's state code doesn't match your business state. Check both."),
    "R07": ("IFSC format", "Check your IFSC. It should be 11 characters, like SBIN0001234."),
}


def _r01_items(check: dict) -> list[dict]:
    message = str(check.get("vendor_message") or "")
    items = []
    found = re.search(r"Complete: ([^.]*)\.", message)
    if found:
        items.append({"key": "R01", "short": "Missing details",
                      "text": "Add the missing details: " + found.group(1) + "."})
    if "valid contact email" in message:
        items.append({"key": "R01:email", "short": "Contact email", "text": "Enter a valid contact email address."})
    return items or [{"key": "R01", "short": "Missing details", "text": "Add the missing details."}]


def _r13_item(check: dict) -> dict:
    message = str(check.get("vendor_message") or "")
    docs = []
    if "GST" in message:
        docs.append("GST certificate")
    if "Bank" in message:
        docs.append("bank document")
    which = " and ".join(docs) or "documents"
    return {"key": "R13", "short": f"Couldn't confirm details from {which}",
            "text": f"We couldn't confirm all the details from your {which}. Upload a clearer copy."}


def vendor_items(run: dict | None) -> list[dict]:
    """Vendor-fixable problems in a saved run, worded for the vendor (no rule IDs)."""
    if not run:
        return []
    rules = _by_rule(run)
    items: list[dict] = []
    if _failed(rules.get("R01")):
        items.extend(_r01_items(rules["R01"]))
    document_problem = _failed(rules.get("R02"))
    if document_problem:
        items.extend(_document_items(str(rules["R02"].get("vendor_message") or "")))
    for rule in VENDOR_INPUT_RULES[1:]:
        if _failed(rules.get(rule)):
            short, text = _INPUT_TEXT[rule]
            items.append({"key": rule, "short": short, "text": text})
    # Unconfirmed evidence is the vendor's to fix (clearer copy) unless it is only a
    # side effect of a missing/unreadable/swapped document or a provider outage.
    if _failed(rules.get("R13")) and not document_problem and not extraction_outage(run):
        items.append(_r13_item(rules["R13"]))
    return items


def _flag(rule: str, risk: str, reason: str) -> dict:
    return {"rule_id": rule, "risk": risk, "reason": reason}


def team_flags(run: dict | None) -> list[dict]:
    """Reviewer-owned flags, highest risk first. Staff wording only."""
    if not run:
        return []
    rules = _by_rule(run)
    flags: list[dict] = []
    r12 = rules.get("R12")
    if _failed(r12):
        label = str(r12.get("label") or "")
        flags.append(_flag("R12", HIGH, label if label and label != "Approved GSTIN duplicate"
                           else "Same GSTIN as an approved vendor"))
    elif _not_pass(r12) and not _failed(rules.get("R04")):
        flags.append(_flag("R12", MEDIUM, "Records check could not run"))
    r15 = rules.get("R15")
    if _failed(r15):
        flags.append(_flag("R15", HIGH, str(r15.get("label") or "Bank account used under a different GSTIN")))
    elif _not_pass(r15) and not _failed(rules.get("R07")) and not _failed(rules.get("R01")):
        flags.append(_flag("R15", MEDIUM, "Bank reuse check could not run"))
    if _failed(rules.get("R11")):
        flags.append(_flag("R11", MEDIUM, "Bank account holder differs from legal name"))
    if _failed(rules.get("R08")):
        flags.append(_flag("R08", MEDIUM, "Business details differ from the GST certificate"))
    if _failed(rules.get("R09")):
        flags.append(_flag("R09", MEDIUM, "Account number differs from the bank document"))
    if _failed(rules.get("R10")):
        flags.append(_flag("R10", MEDIUM, "IFSC differs from the bank document"))
    if extraction_outage(run):
        flags.append(_flag("R14", LOW, "Document reading unavailable, re-run needed"))
    flags.sort(key=lambda f: RISK_ORDER[f["risk"]])
    return flags


def case_owner(application: dict, run: dict | None = None, review: dict | None = None) -> str:
    """DRAFT / VENDOR / TEAM / COMPLETE. Never a fourth decision status."""
    if application.get("current_status") in {"APPROVED", "REJECTED"}:
        return COMPLETE
    if not run:
        return DRAFT
    if active_review_request(review, run):
        return VENDOR
    if vendor_items(run):
        return VENDOR
    return TEAM


def staff_summary(application: dict, run: dict | None, review: dict | None) -> dict:
    """One-line 'why it's here' and risk tag for the reviewer queue and case header."""
    owner = case_owner(application, run, review)
    status = application.get("current_status")
    if owner == VENDOR:
        if active_review_request(review, run):
            return {"owner": owner, "reason": "Correction requested from vendor", "risk": None}
        items = vendor_items(run)
        return {"owner": owner, "reason": "Waiting for vendor: " + items[0]["short"].lower() if items else
                "Waiting for vendor", "risk": None}
    if owner == TEAM:
        flags = team_flags(run)
        if flags:
            return {"owner": owner, "reason": flags[0]["reason"], "risk": flags[0]["risk"]}
        return {"owner": owner, "reason": "Manual decision needed", "risk": LOW}
    if owner == DRAFT:
        return {"owner": owner, "reason": "Not submitted yet", "risk": None}
    return {"owner": owner, "reason": "Approved by reviewer" if status == "APPROVED" and
            application.get("decision_source") == "MANUAL" else
            "Approved straight through" if status == "APPROVED" else "Rejected by reviewer", "risk": None}


def queue_tab(application: dict, owner: str) -> str | None:
    """Reviewer queue tab. Drafts (zero runs) never appear in the queue."""
    status = application.get("current_status")
    if owner == DRAFT:
        return None
    if status == "APPROVED":
        return "APPROVED"
    if status == "REJECTED":
        return "REJECTED"
    return "WAITING_ON_VENDOR" if owner == VENDOR else "NEEDS_REVIEW"


def vendor_team_message(run: dict | None) -> str:
    if extraction_outage(run):
        return OUTAGE_MESSAGE
    if any(f["rule_id"] in {"R12", "R15"} for f in team_flags(run)):
        return ADDITIONAL_CHECK
    return TEAM_MESSAGE


# ---------------------------------------------------------------- B2 records screening
# V2_01 §6: duplicate GSTIN across approved, pending and rejected applications, and
# the same bank account (number + IFSC) under a different GSTIN. Both route to the
# team; the vendor only ever sees ADDITIONAL_CHECK. Staff wording lives in `label`
# (short reason) and `admin_detail` (one or two sentences naming the linked cases).

STATUS_WORDS = {"APPROVED": "approved", "REJECTED": "rejected", "PENDING": "open"}
_STATUS_PRIORITY = {"APPROVED": 0, "REJECTED": 1, "PENDING": 2}
CASE_ID = re.compile(r"\bVF-[0-9A-F]{12}\b")


def _check(rule: str, state: str, code: str, label: str, detail: str, action: str):
    from .models import CheckResult, CheckState
    return CheckResult(rule_id=rule, state=CheckState(state), code=code, label=label,
                       vendor_message=ADDITIONAL_CHECK if state != "PASS" else "Records check completed.",
                       admin_detail=detail, next_action=action)


def _listing(records: list[dict]) -> str:
    return ", ".join(f"{r['id']} ({STATUS_WORDS.get(r['status'], 'open')})" for r in records)


def gstin_check(v, application_id: str, registry) -> "CheckResult":
    from .rules import GSTIN_PATTERN, norm_id
    gstin = norm_id(v.gstin)
    action = "Compare with the linked application before deciding"
    if not GSTIN_PATTERN.fullmatch(gstin):
        return _check("R12", "UNKNOWN", "DUPLICATE_GSTIN", "Records check waits for a valid GSTIN",
                      "GSTIN not structurally valid; records not searched.", action)
    if registry is None:
        return _check("R12", "UNKNOWN", "DUPLICATE_GSTIN", "Records check could not run",
                      "No records registry connected.", action)
    try:
        matches = registry.records_by_gstin(gstin, application_id)
    except Exception:
        return _check("R12", "UNKNOWN", "DUPLICATE_GSTIN", "Records check could not run",
                      "Records lookup failed; screen manually.", action)
    if not matches:
        return _check("R12", "PASS", "DUPLICATE_GSTIN", "No other application with this GSTIN",
                      "No approved, pending or rejected application uses this GSTIN.", action)
    matches = sorted(matches, key=lambda r: _STATUS_PRIORITY.get(r["status"], 3))
    top = matches[0]
    account = re.sub(r"\s+", "", v.account_number or "")
    same_bank = top["account_number"] == account and top["ifsc"] == norm_id(v.ifsc)
    word = STATUS_WORDS.get(top["status"], "open")
    if top["status"] == "APPROVED" and not same_bank:
        label = "Same GSTIN as an approved vendor, different bank account"
        detail = (f"This GSTIN already belongs to approved application {top['id']}, but this application "
                  "gives a different bank account. This is a common pattern in payment-diversion fraud.")
    elif top["status"] == "APPROVED":
        label = "Same GSTIN as an approved vendor"
        detail = f"This GSTIN already belongs to approved application {top['id']}, with the same bank account."
    else:
        label = f"Same GSTIN as a{'n' if word == 'open' else ''} {word} application"
        detail = (f"This GSTIN is also on {word} application {top['id']}"
                  f"{', with the same bank account' if same_bank else ', with a different bank account'}.")
    if len(matches) > 1:
        detail += f" All matches: {_listing(matches)}."
    return _check("R12", "FAIL", "DUPLICATE_GSTIN", label, detail, action)


def bank_reuse_check(v, application_id: str, registry) -> "CheckResult":
    from .rules import IFSC_PATTERN, norm_id
    account, ifsc = re.sub(r"\s+", "", v.account_number or ""), norm_id(v.ifsc)
    action = "Confirm who owns the bank account before deciding"
    if not account or not IFSC_PATTERN.fullmatch(ifsc):
        return _check("R15", "UNKNOWN", "BANK_REUSE", "Bank reuse check waits for valid bank details",
                      "Account number or IFSC missing/invalid; records not searched.", action)
    if registry is None:
        return _check("R15", "UNKNOWN", "BANK_REUSE", "Bank reuse check could not run",
                      "No records registry connected.", action)
    try:
        matches = registry.records_by_bank(account, ifsc, application_id)
    except Exception:
        return _check("R15", "UNKNOWN", "BANK_REUSE", "Bank reuse check could not run",
                      "Records lookup failed; screen manually.", action)
    gstin = norm_id(v.gstin)
    others = sorted((r for r in matches if r["gstin"] != gstin), key=lambda r: _STATUS_PRIORITY.get(r["status"], 3))
    if not others:
        return _check("R15", "PASS", "BANK_REUSE", "Bank account not used under another GSTIN",
                      "No other GSTIN uses this account number and IFSC.", action)
    top = others[0]
    detail = (f"The same bank account (number and IFSC) is on {STATUS_WORDS.get(top['status'], 'open')} application "
              f"{top['id']} under a different GSTIN ({top['gstin'] or 'not given'}).")
    if len(others) > 1:
        detail += f" All matches: {_listing(others)}."
    return _check("R15", "FAIL", "BANK_REUSE", "Bank account used under a different GSTIN", detail, action)


def records_screening(registry):
    """Pipeline hook (ProcessingPipeline(screening=...)): returns R12 and R15."""
    def screen(v, application_id: str):
        return [gstin_check(v, application_id, registry), bank_reuse_check(v, application_id, registry)]
    return screen


def linked_case_ids(run: dict | None) -> list[str]:
    """Case IDs named by the saved R12/R15 evidence (staff only)."""
    found: list[str] = []
    for check in _checks(run):
        if check.get("rule_id") in {"R12", "R15"} and check.get("state") == "FAIL":
            for case_id in CASE_ID.findall(str(check.get("admin_detail") or "")):
                if case_id not in found:
                    found.append(case_id)
    return found


def pipeline_options(registry) -> dict:
    """v2 policy hooks for ProcessingPipeline / PersistentVendorService."""
    from .rules import norm_legal_name
    return {"screening": records_screening(registry), "name_key": norm_legal_name}
