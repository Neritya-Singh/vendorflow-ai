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
VENDOR_INPUT_RULES = ("R01", "R03", "R04", "R05", "R06", "R07", "R17")
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
    "R04": ("GSTIN format", "Check your GSTIN. It should be 15 characters, like 27ABCDE1234F1Z0."),
    "R05": ("PAN does not match GSTIN", "Your PAN doesn't match the PAN inside your GSTIN. Check both numbers."),
    "R06": ("GSTIN state code", "Your GSTIN's state code doesn't match your business state. Check both."),
    "R07": ("IFSC format", "Check your IFSC. It should be 11 characters, like SBIN0001234."),
    "R17": ("GSTIN check digit", "Check your GSTIN. Its last character doesn't match the rest of the number, "
                                 "so one character is probably mistyped."),
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
    if (_failed(rules.get("R13")) and not document_problem and not extraction_outage(run)
            and not r13_covered_by_vendor_values(run)):
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
    if _failed(rules.get("R16")):
        flags.append(_flag("R16", MEDIUM, str(rules["R16"].get("label") or "Vendor changed values from the documents")))
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
        # Independent lookups: run them at the same time (each fails closed on its own).
        from .persistence import parallel
        return parallel(lambda: gstin_check(v, application_id, registry),
                        lambda: bank_reuse_check(v, application_id, registry))
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
    return {"screening": records_screening(registry), "name_key": norm_legal_name,
            "evidence_checks": evidence_checks}


# ---------------------------------------------------------------- B3 decisions
# V2_02 §7–8: a structured confirmation is required to approve an unresolved
# duplicate or bank-reuse case. Enforced by the API, not only the UI.
BANK_CHANGE_CONFIRMATION = "Bank change confirmed by call-back to the contact on the existing record"
CONFIRMATION_PREFIX = "Confirmation: "


def requires_confirmation(run: dict | None) -> bool:
    return any(c.get("rule_id") in {"R12", "R15"} and c.get("state") != "PASS" for c in _checks(run))


_FLAG_REQUESTS = {
    "R08": "Check that your legal name, GSTIN and state match your GST certificate exactly.",
    "R09": "Check that your account number matches your bank document.",
    "R10": "Check that your IFSC matches your bank document.",
    "R12": "Upload a recent letter from your bank confirming that this account belongs to your business.",
    "R15": "Upload a recent letter from your bank confirming that this account belongs to your business.",
    "R14": "Submit your application again so we can read your documents.",
    "R16": "Check the details you changed or typed in against your documents, or upload a clearer copy that shows them.",
}


def correction_draft(run: dict | None, legal_name: str = "") -> str:
    """Vendor message pre-drafted from the flagged items; the reviewer edits it.
    Never names another case or the reason a records check flagged."""
    asks: list[str] = [i["text"] for i in vendor_items(run)]
    for flag in team_flags(run):
        if flag["rule_id"] == "R11":
            who = legal_name or "your business's legal name"
            text = f"Upload a bank letter or cancelled cheque that shows {who} as the account holder."
        else:
            text = _FLAG_REQUESTS.get(flag["rule_id"], "")
        if text and text not in asks:
            asks.append(text)
    return " ".join(asks)[:1000] or "Please check your details and documents, then submit again."


def split_confirmation(reason: str) -> tuple[str, str | None]:
    """Stored as '<reason>\\n\\nConfirmation: <text>' in review_actions.reason."""
    marker = "\n\n" + CONFIRMATION_PREFIX
    if marker in (reason or ""):
        head, tail = reason.split(marker, 1)
        return head, tail
    return reason, None


# ---------------------------------------------------------------- B4 dashboard
REASON_CATEGORIES = (
    "Missing or wrong document", "Unreadable or unclear document", "Missing or invalid details",
    "Name differs from bank holder", "Value differs from document", "Duplicate or bank reuse", "Document reading unavailable",
)


def reason_categories(run: dict | None) -> set[str]:
    """Coarse, staff-only reason buckets for the dashboard's 'Top reasons'."""
    found: set[str] = set()
    for item in vendor_items(run):
        key = item["key"]
        if key == "swapped" or key.startswith("missing:"):
            found.add("Missing or wrong document")
        elif key.startswith("unclear:") or key == "R13" or key == "documents":
            found.add("Unreadable or unclear document")
        else:
            found.add("Missing or invalid details")
    for flag in team_flags(run):
        rule = flag["rule_id"]
        if rule == "R11":
            found.add("Name differs from bank holder")
        elif rule in {"R08", "R09", "R10", "R16"}:
            found.add("Value differs from document")
        elif rule in {"R12", "R15"}:
            found.add("Duplicate or bank reuse")
        elif rule == "R14":
            found.add("Document reading unavailable")
    return found


def run_outcome_label(run: dict | None) -> str:
    """What a single saved run decided, in reviewer wording."""
    if (run or {}).get("status") == "APPROVED":
        return "Approved"
    return "Waiting on vendor" if vendor_items(run) else "Sent to team"


# ---------------------------------------------------------------- B5 upload-first evidence
# V2_01 §5–6: values are pre-filled from the documents. A value the vendor changed,
# or typed because it was not found on a document that WAS read, is kept, flagged
# and decided by the team (both values shown). GSTIN check digit (owner decision 5).

_GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_check_digit_ok(gstin: str) -> bool | None:
    """Standard GSTIN mod-36 checksum. None when the GSTIN is not structurally valid."""
    from .rules import GSTIN_PATTERN, norm_id
    value = norm_id(gstin)
    if not GSTIN_PATTERN.fullmatch(value):
        return None
    total = 0
    for index, char in enumerate(value[:14]):
        product = _GSTIN_CHARS.index(char) * (2 if index % 2 else 1)
        total += product // 36 + product % 36
    return _GSTIN_CHARS[(36 - total % 36) % 36] == value[14]


def _digits(value) -> str:
    return re.sub(r"[\s-]+", "", str(value or ""))


# (field, vendor label, staff label, document, extracted key, R13 label)
PROVENANCE_FIELDS = (
    ("legal_name", "Legal name", "Legal name", "GST", "legal_name", "GST legal name"),
    ("gstin", "GSTIN", "GSTIN", "GST", "gstin", "GSTIN"),
    ("business_state", "State", "State", "GST", "state", "GST state"),
    ("bank_holder", "Account holder", "Account holder", "BANK", "holder_name", "Bank account holder"),
    ("account_number", "Account number", "Account number", "BANK", "account_number", "Bank account number"),
    ("ifsc", "IFSC", "IFSC", "BANK", "ifsc", "Bank IFSC"),
)
_DOC_KEYS = {"GST": ("legal_name", "gstin", "state"), "BANK": ("holder_name", "account_number", "ifsc")}


def _same(field: str, a, b) -> bool:
    from .rules import norm_id, norm_legal_name, norm_state
    if field in ("gstin", "ifsc"):
        return norm_id(a) == norm_id(b)
    if field == "account_number":
        return _digits(a) == _digits(b)
    if field == "business_state":
        return norm_state(a) == norm_state(b)
    return norm_legal_name(a) == norm_legal_name(b)  # "Pvt Ltd" == "Private Limited" (B2)


def document_was_read(extracted: dict | None, doc: str) -> bool:
    """A document counts as read when at least one of its fields was extracted."""
    part = (extracted or {}).get("gst" if doc == "GST" else "bank") or {}
    return any(str(part.get(key) or "").strip() for key in _DOC_KEYS[doc])


def field_provenance(values: dict, extracted: dict | None) -> list[dict]:
    """Per field: document | edited | vendor (not on a read document) | missing | unread."""
    rows = []
    for field, label, staff, doc, key, _r13 in PROVENANCE_FIELDS:
        part = (extracted or {}).get("gst" if doc == "GST" else "bank") or {}
        doc_value = str(part.get(key) or "").strip()
        value = str((values or {}).get(field) or "").strip()
        if not document_was_read(extracted, doc):
            status = "unread"
        elif doc_value and value:
            status = "document" if _same(field, value, doc_value) else "edited"
        elif doc_value:
            status = "missing"
        else:
            status = "vendor" if value else "missing"
        rows.append({"field": field, "label": label, "staff_label": staff, "document": doc,
                     "value": value, "document_value": doc_value or None, "status": status})
    return rows


def _mask(field: str, value) -> str:
    text = str(value or "")
    if field == "account_number":
        digits = _digits(text)
        return "••••" + digits[-4:] if digits else ""
    return text


def evidence_checks(v, extracted) -> list:
    """Pipeline hook (ProcessingPipeline(evidence_checks=...)): R16 and R17."""
    from .models import CheckResult, CheckState
    values = v.model_dump() if hasattr(v, "model_dump") else dict(v)
    data = extracted.model_dump() if hasattr(extracted, "model_dump") else dict(extracted or {})
    rows = field_provenance(values, data)
    edited = [r for r in rows if r["status"] == "edited"]
    typed = [r for r in rows if r["status"] == "vendor"]
    unread = any(r["status"] == "unread" for r in rows)
    parts = [f"{r['staff_label']}: changed by vendor (document {_mask(r['field'], r['document_value'])!r}; "
             f"vendor {_mask(r['field'], r['value'])!r})" for r in edited]
    parts += [f"{r['staff_label']}: entered by vendor, not on document ({_mask(r['field'], r['value'])!r})"
              for r in typed]
    if edited or typed:
        label = ("Vendor changed and entered values not on the documents" if edited and typed
                 else "Vendor changed a value from the documents" if edited
                 else "Vendor entered a value not on the documents")
        state, detail = CheckState.FAIL, "; ".join(parts) + "."
    elif unread:
        label, state = "Document values not compared", CheckState.UNKNOWN
        detail = "A document was not read, so entered values could not be compared with it."
    else:
        label, state, detail = "All values come from the documents", CheckState.PASS, ""
    r16 = CheckResult(rule_id="R16", state=state, code="VENDOR_VALUES", label=label,
                      vendor_message=("Our team will compare the details you changed or entered with your documents."
                                      if state == CheckState.FAIL else "Details taken from your documents."),
                      admin_detail=detail, next_action="Compare the vendor's values with the documents")
    digit = gstin_check_digit_ok(values.get("gstin") or "")
    r17 = CheckResult(rule_id="R17", state=CheckState.UNKNOWN if digit is None else
                      (CheckState.PASS if digit else CheckState.FAIL),
                      code="GSTIN_CHECK_DIGIT", label="GSTIN check digit",
                      vendor_message=("GSTIN check digit valid." if digit else
                                      "Check your GSTIN. Its last character doesn't match the rest of the number."
                                      if digit is False else "GSTIN check digit waits for a valid GSTIN."),
                      next_action="Correct GSTIN")
    # UNKNOWN only when R04 already fails; keep R17 out of the decision in that case.
    return [r16, r17] if digit is not None else [r16, r17.model_copy(update={"state": CheckState.PASS,
            "vendor_message": "GSTIN check digit not checked (GSTIN format already flagged)."})]


def r13_covered_by_vendor_values(run: dict | None) -> bool:
    """True when every R13 issue is a field the vendor typed because it was not found
    on a document we DID read. Those go to the team (flagged by R16), not back to the vendor."""
    r13 = _by_rule(run).get("R13")
    if not _failed(r13) or not _failed(_by_rule(run).get("R16")):
        return False
    message = str(r13.get("vendor_message") or "")
    found = re.search(r"evidence: (.*)\.$", message)
    if not found or "not supported by PDF" in message:
        return False
    issues = [part.strip() for part in found.group(1).split(",") if part.strip()]
    rows = {r[5]: r[0] for r in PROVENANCE_FIELDS}
    typed = {r["field"] for r in field_provenance((run or {}).get("payload_json") or {},
                                                   (run or {}).get("extracted_json") or {})
             if r["status"] == "vendor"}
    return bool(issues) and all(rows.get(issue) in typed for issue in issues)


# ---------------------------------------------------------------- B7 part 1: fix items
# A reviewer's correction request names WHAT the vendor must change, so the vendor's
# fix page shows only those items (an upload slot or a field), never the full form.
# The ids are stored after the message in review_actions.reason, like the bank-change
# confirmation, so no schema change is needed:  "<message>\n\nRequested: doc:BANK, field:ifsc"
REQUESTED_PREFIX = "Requested: "
FIX_FIELDS = tuple(f[0] for f in PROVENANCE_FIELDS) + ("contact",)
FIX_ITEM_IDS = ("doc:GST", "doc:BANK") + tuple(f"field:{f}" for f in FIX_FIELDS)
FIX_ITEM_LABELS = {
    "doc:GST": "New GST certificate", "doc:BANK": "New bank document",
    **{f"field:{f[0]}": f[1] for f in PROVENANCE_FIELDS}, "field:contact": "Contact details",
}
_FIX_DOC_TEXT = {"GST": "Upload a new GST certificate.",
                 "BANK": "Upload a new bank document: a cancelled cheque or a letter from your bank."}
_FIELD_FIX_TEXT = {"contact": "Check your contact details."}
_ITEM_TARGETS = {
    "swapped": ("doc:GST", "doc:BANK"), "documents": ("doc:GST", "doc:BANK"),
    "R03": ("field:gstin",), "R04": ("field:gstin",), "R05": ("field:gstin",), "R17": ("field:gstin",),
    "R06": ("field:gstin", "field:business_state"), "R07": ("field:ifsc",), "R01:email": ("field:contact",),
}
_FLAG_TARGETS = {"R11": ("doc:BANK",), "R12": ("doc:BANK",), "R15": ("doc:BANK",),
                 "R08": ("field:legal_name", "field:gstin", "field:business_state"),
                 "R09": ("field:account_number",), "R10": ("field:ifsc",)}


def join_requested(reason: str, items: list[str] | tuple[str, ...]) -> str:
    known = [i for i in FIX_ITEM_IDS if i in set(items or ())]
    return f"{reason}\n\n{REQUESTED_PREFIX}{', '.join(known)}" if known else reason


def split_requested(reason: str) -> tuple[str, list[str]]:
    """('<message>', ['doc:BANK', ...]). Unknown ids are dropped."""
    marker = "\n\n" + REQUESTED_PREFIX
    if marker not in (reason or ""):
        return reason or "", []
    head, tail = reason.split(marker, 1)
    tail = tail.split("\n\n", 1)[0]
    asked = {part.strip() for part in tail.split(",")}
    return head, [i for i in FIX_ITEM_IDS if i in asked]


def split_review(reason: str) -> tuple[str, str | None, list[str]]:
    """(message, bank-change confirmation or None, requested fix-item ids)."""
    head, confirmation = split_confirmation(reason or "")
    message, items = split_requested(head)
    return message, confirmation, items


def _r01_targets(run: dict) -> list[str]:
    payload = run.get("payload_json") or {}
    out = [f"field:{f}" for f in FIX_FIELDS[:-1] if not str(payload.get(f) or "").strip()]
    if not str(payload.get("contact_name") or "").strip() or not str(payload.get("contact_email") or "").strip():
        out.append("field:contact")
    return out


def _vendor_item_targets(run: dict, item: dict) -> list[str]:
    key = str(item.get("key") or "")
    if key.startswith(("missing:", "unclear:")):
        return ["doc:GST" if "GST" in key else "doc:BANK"]
    if key == "R13":
        text = str(item.get("text") or "")
        out = (["doc:GST"] if "GST" in text else []) + (["doc:BANK"] if "bank" in text else [])
        return out or ["doc:GST", "doc:BANK"]
    if key == "R01":
        return _r01_targets(run)
    return list(_ITEM_TARGETS.get(key, ()))


def suggested_fix_items(run: dict | None) -> list[str]:
    """Pre-selected items for a reviewer's correction request, from the flags."""
    if not run:
        return []
    wanted: list[str] = []
    for item in vendor_items(run):
        wanted.extend(_vendor_item_targets(run, item))
    for flag in team_flags(run):
        if flag["rule_id"] == "R16":
            rows = field_provenance(run.get("payload_json") or {}, run.get("extracted_json") or {})
            wanted.extend(f"field:{r['field']}" for r in rows if r["status"] in ("edited", "vendor"))
        wanted.extend(_FLAG_TARGETS.get(flag["rule_id"], ()))
    return [i for i in FIX_ITEM_IDS if i in set(wanted)]


def fix_items(run: dict | None, review: dict | None) -> list[dict]:
    """What the vendor must change on the fix page: the automated vendor items plus
    the items an ACTIVE reviewer correction request names. Each is either a document
    (an upload slot) or a field. A request saved without items (older API clients)
    falls back to the items suggested by the flags."""
    if not run:
        return []
    texts: dict[str, str] = {}
    for item in vendor_items(run):
        for target in _vendor_item_targets(run, item):
            texts.setdefault(target, item["text"])
    if active_review_request(review, run):
        _message, _confirmation, asked = split_review(str(review.get("reason") or ""))
        for target in asked or suggested_fix_items(run) or ["doc:GST", "doc:BANK"]:
            texts.setdefault(target, "")
    out = []
    for target in FIX_ITEM_IDS:
        if target not in texts:
            continue
        kind, name = target.split(":", 1)
        if kind == "doc":
            out.append({"id": target, "kind": "document", "slot": name,
                        "text": texts[target] or _FIX_DOC_TEXT[name]})
        else:
            label = FIX_ITEM_LABELS[target]
            out.append({"id": target, "kind": "field", "field": name,
                        "text": texts[target] or _FIELD_FIX_TEXT.get(name, f"Check your {label if name in ('gstin', 'ifsc') else label.lower()}.")})
    return out
