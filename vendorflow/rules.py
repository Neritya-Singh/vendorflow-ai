"""Deterministic document-level policy; never represent it as formal KYC/KYB."""
from __future__ import annotations

import re
from collections.abc import Callable
from .models import VendorSubmission, ExtractedDocuments, CheckResult, CheckState
from .pdf_reader import ReadPDF

# State and UT GST codes for this limited India-only onboarding prototype.
GST_STATE_CODES = {
    "JAMMU AND KASHMIR": "01", "HIMACHAL PRADESH": "02", "PUNJAB": "03",
    "CHANDIGARH": "04", "UTTARAKHAND": "05", "HARYANA": "06", "DELHI": "07",
    "RAJASTHAN": "08", "UTTAR PRADESH": "09", "BIHAR": "10", "SIKKIM": "11",
    "ARUNACHAL PRADESH": "12", "NAGALAND": "13", "MANIPUR": "14",
    "MIZORAM": "15", "TRIPURA": "16", "MEGHALAYA": "17", "ASSAM": "18",
    "WEST BENGAL": "19", "JHARKHAND": "20", "ODISHA": "21",
    "CHHATTISGARH": "22", "MADHYA PRADESH": "23", "GUJARAT": "24",
    "DADRA AND NAGAR HAVELI AND DAMAN AND DIU": "26", "MAHARASHTRA": "27",
    "ANDHRA PRADESH": "37", "KARNATAKA": "29", "GOA": "30",
    "LAKSHADWEEP": "31", "KERALA": "32", "TAMIL NADU": "33",
    "PUDUCHERRY": "34", "ANDAMAN AND NICOBAR ISLANDS": "35",
    "TELANGANA": "36", "LADAKH": "38",
}
PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
GSTIN_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
IFSC_PATTERN = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def norm_id(value: str | None) -> str:
    return re.sub(r"\s+", "", value or "").upper()


def norm_name(value: str | None) -> str:
    """Nonmaterial case/spacing/punctuation only; no fuzzy/legal suffix equivalence."""
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", (value or "").upper())).strip()


def norm_state(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").upper().strip())



def normalize_submission(v: VendorSubmission) -> VendorSubmission:
    """Prepare comparison-ready values without changing bank account leading zeroes."""
    return VendorSubmission(
        legal_name=" ".join(v.legal_name.split()),
        business_state=norm_state(v.business_state),
        contact_name=" ".join(v.contact_name.split()),
        contact_email=v.contact_email.strip(),
        pan=norm_id(v.pan),
        gstin=norm_id(v.gstin),
        bank_holder=" ".join(v.bank_holder.split()),
        account_number=re.sub(r"\s+", "", v.account_number),
        ifsc=norm_id(v.ifsc),
    )

def add(checks: list[CheckResult], rule: str, ok: bool | None, code: str,
        label: str, message: str, detail: str = "", action: str = "Review / correct submission") -> None:
    checks.append(CheckResult(
        rule_id=rule, state=CheckState.PASS if ok is True else (CheckState.FAIL if ok is False else CheckState.UNKNOWN),
        code=code, label=label,
        vendor_message=message, admin_detail=detail, next_action=action,
    ))


def checks_without_duplicate(v: VendorSubmission, x: ExtractedDocuments,
                             gst_pdf: ReadPDF | None, bank_pdf: ReadPDF | None,
                             extraction_error: bool) -> list[CheckResult]:
    checks: list[CheckResult] = []
    missing = [label for label, value in (
        ("Legal business name", v.legal_name), ("Business state", v.business_state),
        ("Contact name", v.contact_name), ("Contact email", v.contact_email),
        ("PAN", v.pan), ("GSTIN", v.gstin), ("Bank holder", v.bank_holder),
        ("Bank account number", v.account_number), ("IFSC", v.ifsc),
    ) if not value.strip()]
    email_ok = bool(EMAIL_PATTERN.fullmatch(v.contact_email.strip())) if v.contact_email.strip() else False
    add(checks, "R01", not missing and email_ok, "REQUIRED_FIELDS",
        "Required fields", ("Complete: " + ", ".join(missing) + ".") if missing else
        ("Enter a valid contact email address." if not email_ok else "All required fields are present."),
        action="Complete missing fields")

    missing_docs = [label for label, pdf in (("GST certificate", gst_pdf), ("Bank proof", bank_pdf)) if pdf is None]
    unreadable_docs = [label for label, pdf in (("GST certificate", gst_pdf), ("Bank proof", bank_pdf)) if pdf is not None and not pdf.readable]
    document_good = not missing_docs and not unreadable_docs
    doc_msg = ("Upload: " + ", ".join(missing_docs) + ".") if missing_docs else (
        "Replace unreadable document(s): " + ", ".join(unreadable_docs) + "." if unreadable_docs
        else "Both required PDFs contain readable text.")
    add(checks, "R02", document_good, "DOCUMENT_READABILITY", "Required PDFs", doc_msg,
        action="Upload / replace the named PDF")

    pan, gstin, ifsc = norm_id(v.pan), norm_id(v.gstin), norm_id(v.ifsc)
    pan_ok = bool(PAN_PATTERN.fullmatch(pan))
    gstin_ok = bool(GSTIN_PATTERN.fullmatch(gstin))
    ifsc_ok = bool(IFSC_PATTERN.fullmatch(ifsc))
    add(checks, "R03", pan_ok, "PAN_FORMAT", "PAN structure", "Check the 10-character PAN format." if not pan_ok else "PAN format valid.", action="Correct PAN")
    add(checks, "R04", gstin_ok, "GSTIN_FORMAT", "GSTIN structure", "Check the 15-character GSTIN format." if not gstin_ok else "GSTIN format valid.", action="Correct GSTIN")
    add(checks, "R05", pan == gstin[2:12] if (pan_ok and gstin_ok) else None,
        "PAN_GSTIN_MISMATCH", "PAN in GSTIN",
        "Your PAN does not match the PAN embedded in your GSTIN. Check both numbers.", action="Correct PAN / GSTIN")
    expected_code = GST_STATE_CODES.get(norm_state(v.business_state))
    add(checks, "R06", (gstin[:2] == expected_code) if (expected_code and gstin_ok) else None,
        "GST_STATE_MISMATCH", "GSTIN state", "Your GSTIN state code does not match the selected business state.",
        action="Check GSTIN and business state")
    add(checks, "R07", ifsc_ok, "IFSC_FORMAT", "IFSC structure", "Enter an 11-character IFSC in the standard format." if not ifsc_ok else "IFSC format valid.", action="Correct IFSC")

    # Documentary comparisons fail closed when a field is missing or the document is unreadable.
    gst_available = bool(gst_pdf and gst_pdf.readable and not extraction_error)
    bank_available = bool(bank_pdf and bank_pdf.readable and not extraction_error)
    xgst = norm_id(x.gst.gstin)
    xlegal = norm_name(x.gst.legal_name)
    xstate = norm_state(x.gst.state)
    gmatch = bool(gst_available and xgst and xlegal and xstate and v.legal_name.strip() and v.business_state.strip()
                  and xgst == gstin and xlegal == norm_name(v.legal_name)
                  and xstate == norm_state(v.business_state))
    add(checks, "R08", gmatch if gst_available else None, "GST_DOCUMENT_MISMATCH", "GST certificate",
        "GST certificate legal name, GSTIN or state is missing or differs from your submission.",
        action="Correct business details / replace GST PDF")

    xaccount = re.sub(r"\s+", "", x.bank.account_number or "")
    account = re.sub(r"\s+", "", v.account_number)
    add(checks, "R09", bool(bank_available and account and xaccount and account == xaccount) if bank_available else None,
        "BANK_ACCOUNT_MISMATCH", "Bank account", "Your bank account number differs from, or is missing in, the uploaded bank proof.",
        action="Correct bank account / replace bank PDF")
    add(checks, "R10", bool(bank_available and x.bank.ifsc and norm_id(x.bank.ifsc) == ifsc) if bank_available else None,
        "BANK_IFSC_MISMATCH", "Bank IFSC", "The IFSC differs from, or is missing in, the uploaded bank proof.",
        action="Correct IFSC / replace bank PDF")
    bank_name_matches_form = bool(x.bank.holder_name and v.bank_holder and norm_name(x.bank.holder_name) == norm_name(v.bank_holder))
    bank_name_matches_legal = bool(x.bank.holder_name and v.legal_name and norm_name(x.bank.holder_name) == norm_name(v.legal_name))
    add(checks, "R11", (bank_name_matches_form and bank_name_matches_legal) if bank_available else None,
        "BANK_NAME_REVIEW", "Bank account ownership",
        "The bank account holder name needs review against the business legal name and bank proof.",
        action="Review / supply bank holder evidence")

    required_extracted = {
        "GST legal name": x.gst.legal_name if gst_available else None,
        "GSTIN": x.gst.gstin if gst_available else None,
        "GST state": x.gst.state if gst_available else None,
        "Bank account holder": x.bank.holder_name if bank_available else None,
        "Bank account number": x.bank.account_number if bank_available else None,
        "Bank IFSC": x.bank.ifsc if bank_available else None,
    }
    not_found = [key for key, value in required_extracted.items() if not (value or "").strip()]
    # Extracted evidence must ALSO be grounded in the actual parsed document text.
    # A plausible Gemini hallucination is not evidence and cannot earn approval.
    gst_text = gst_pdf.text if gst_available and gst_pdf else ""
    bank_text = bank_pdf.text if bank_available and bank_pdf else ""
    grounding = (
        ("GST legal name", x.gst.legal_name, gst_text, norm_name),
        ("GSTIN", x.gst.gstin, gst_text, norm_id),
        ("GST state", x.gst.state, gst_text, norm_name),
        ("Bank account holder", x.bank.holder_name, bank_text, norm_name),
        ("Bank account number", x.bank.account_number, bank_text, lambda t: re.sub(r"\s+", "", t or "")),
        ("Bank IFSC", x.bank.ifsc, bank_text, norm_id),
    )
    ungrounded = [label for label, value, document_text, formatter in grounding
                  if value and formatter(value) not in formatter(document_text)]
    # Keep the same R13 code for missing or unsupported evidence; do not claim verified.
    issues = [*not_found, *("not supported by PDF: " + name for name in ungrounded)]
    add(checks, "R13", not issues, "EXTRACTION_INCOMPLETE", "Evidence completeness",
        "Missing or unconfirmed document evidence: " + ", ".join(issues) + "." if issues else "All critical extracted fields occur in the source documents.",
        action="Upload clearer/more complete documents")
    add(checks, "R14", not extraction_error, "EXTRACTION_UNAVAILABLE", "AI extraction",
        "AI extraction was unavailable. Try again or request manual review." if extraction_error else "Extraction completed without error.",
        action="Retry / request review")
    return checks


def duplicate_check(v: VendorSubmission, approved_lookup: Callable[[str, str], list[str]] | None,
                    application_id: str) -> CheckResult:
    checks: list[CheckResult] = []
    gstin = norm_id(v.gstin)
    if not GSTIN_PATTERN.fullmatch(gstin):
        ok, detail, msg = None, "GSTIN not structurally valid", "Check GSTIN before checking duplicates."
    elif approved_lookup is None:
        ok, detail, msg = None, "No persistent duplicate registry connected", "Duplicate verification is unavailable; manual review is required."
    else:
        try:
            # The storage adapter must exclude this application when resubmitting.
            existing = [a for a in approved_lookup(gstin, application_id) if a != application_id]
            ok, detail, msg = (not existing), ("Possible matching approved application: " + ", ".join(existing)) if existing else "No other approved GSTIN found", "This GSTIN may already be registered. Our team will review it."
        except Exception:
            ok, detail, msg = None, "Approved registry lookup failed", "Duplicate verification is temporarily unavailable. Please request review."
    add(checks, "R12", ok, "DUPLICATE_GSTIN", "Approved GSTIN duplicate", msg, detail,
        "Review possible duplicate")
    return checks[0]


def make_decision(checks: list[CheckResult]) -> tuple[str, list[str], list[str], str]:
    """Only ALL PASS permits approval; fixes are never auto-rejected."""
    failures = [check for check in checks if check.state != CheckState.PASS]
    if not failures:
        return "APPROVED", ["All prototype document-consistency checks passed."], ["All prototype document-consistency checks passed."], "Save your tracking details."
    priority = ["DOCUMENT_READABILITY", "PAN_GSTIN_MISMATCH", "DUPLICATE_GSTIN", "BANK_NAME_REVIEW",
                "BANK_ACCOUNT_MISMATCH", "BANK_IFSC_MISMATCH", "GST_DOCUMENT_MISMATCH", "EXTRACTION_INCOMPLETE", "EXTRACTION_UNAVAILABLE"]
    failures.sort(key=lambda c: (priority.index(c.code) if c.code in priority else len(priority)))
    all_messages = list(dict.fromkeys(check.vendor_message for check in failures))
    return "PENDING", all_messages[:3], all_messages, failures[0].next_action
