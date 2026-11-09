"""VendorFlow AI Stage 3.3: two-checkpoint, LIVE Supabase resubmission test.

Usage (run from project root):
  python scripts/check_resubmission_live.py start
  python scripts/check_resubmission_live.py finish

This creates ONE new synthetic vendor, retains only a private local tracking token,
and checks a missing-bank-holder -> corrected-bank-proof transition. It never prints
secrets and never edits the prior approved or duplicate test applications.
"""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import secrets
import string
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from vendorflow import GeminiExtractor, PDFInput, VendorSubmission
from vendorflow.persistence import SupabaseRepository, PersistentVendorService

STATE_DIR = Path.home() / ".local" / "share" / "vendorflow_ai_demo"
STATE_FILE = STATE_DIR / "live_resubmit_state.json"
NAME = "Example Supplies Private Limited"
STATE = "Uttar Pradesh"
IFSC = "DEMO0123456"


def synthetic_pdf(title: str, rows: list[tuple[str, str]]) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    height = A4[1]
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawString(40, height - 60, title)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(40, height - 85, "SYNTHETIC SAMPLE: NOT AN OFFICIAL GOVERNMENT OR BANK DOCUMENT")
    pdf.setFont("Helvetica", 11)
    for idx, (label, value) in enumerate(rows):
        pdf.drawString(40, height - 130 - idx * 37, f"{label}: {value}")
    pdf.save()
    return buffer.getvalue()


def make_bank(account: str, *, missing_holder: bool) -> PDFInput:
    fields = [("Bank", "Fictional Sample Bank")]
    if not missing_holder:
        fields.append(("Account holder", NAME))
    fields += [("Account number", account), ("IFSC", IFSC)]
    return PDFInput("bank_confirmation.pdf", synthetic_pdf("BANK CONFIRMATION - DEMO", fields))


def make_vendor() -> VendorSubmission:
    alphabet = string.ascii_uppercase
    pan = ("".join(secrets.choice(alphabet) for _ in range(5))
           + "".join(secrets.choice(string.digits) for _ in range(4))
           + secrets.choice(alphabet))
    return VendorSubmission(
        legal_name=NAME, business_state=STATE,
        contact_name="Demo Applicant", contact_email="synthetic@example.com",
        pan=pan, gstin=f"09{pan}1Z5", bank_holder=NAME,
        account_number="00" + "".join(secrets.choice(string.digits) for _ in range(10)),
        ifsc=IFSC,
    )


def make_gst(vendor: VendorSubmission) -> PDFInput:
    return PDFInput("gst_certificate.pdf", synthetic_pdf("GST CERTIFICATE - DEMO", [
        ("Legal business name", vendor.legal_name),
        ("GSTIN", vendor.gstin),
        ("Business state", vendor.business_state),
        ("Business address", "Demo Lane, Uttar Pradesh"),
    ]))


def save_private_state(record: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(STATE_DIR, 0o700)
    descriptor = os.open(STATE_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as out:
        json.dump(record, out)
        out.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Live correction/resubmission smoke test")
    parser.add_argument("step", choices=["start", "finish"])
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=True)

    if args.step == "start" and STATE_FILE.exists():
        raise SystemExit(f"A test is already recorded at {STATE_FILE}. Do not create another; report this message.")
    if args.step == "finish" and not STATE_FILE.exists():
        raise SystemExit("No saved pending test found. Run the 'start' checkpoint first.")

    repo = SupabaseRepository.from_env()
    service = PersistentVendorService(repo, GeminiExtractor())

    if args.step == "start":
        vendor = make_vendor()
        receipt = service.submit(vendor, make_gst(vendor),
                                 make_bank(vendor.account_number, missing_holder=True))
        # Save private tracking credentials immediately after a successful persistent submission.
        save_private_state({"application_id": receipt.application_id,
                            "tracking_code": receipt.tracking_code,
                            "vendor": vendor.model_dump()})
        app, history = service.track(receipt.application_id, receipt.tracking_code)
        checks = {item.rule_id: item.state.value for item in receipt.result.checks}
        print("APPLICATION ID:", receipt.application_id)
        print("INITIAL STATUS:", receipt.result.status.value)
        print("DATABASE STATUS:", app["current_status"])
        print("PERSISTED:", receipt.result.persisted)
        print("RUN COUNT:", len(history))
        print("EXTRACTION ERROR:", receipt.result.extraction_error)
        print("R11:", checks.get("R11"), " R13:", checks.get("R13"))
        print("SAVED PRIVATE TRACKING CREDENTIALS LOCALLY: YES")
        print("EXPECTED:", "PASS" if (
            receipt.result.status.value == "PENDING" and receipt.result.persisted
            and app["current_status"] == "PENDING" and len(history) == 1
            and not receipt.result.extraction_error and checks.get("R11") == "FAIL"
            and checks.get("R13") == "FAIL") else "NOT MET")
    else:
        record = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        app_id = record["application_id"]
        token = record["tracking_code"]
        vendor = VendorSubmission.model_validate(record["vendor"])
        old_app, old_history = service.track(app_id, token)
        if old_app["current_status"] != "PENDING" or len(old_history) != 1:
            raise SystemExit("Test application is not a single-run PENDING case. No write performed.")
        result = service.resubmit(app_id, token, vendor,
                                  bank_upload=make_bank(vendor.account_number, missing_holder=False))
        app, history = service.track(app_id, token)
        bank_rows = (repo.client.table("documents").select("version")
                     .eq("application_id", app_id).eq("doc_type", "BANK")
                     .order("version", desc=False).execute().data)
        versions = [int(row["version"]) for row in bank_rows]
        runs = repo.runs_for_application(app_id)
        print("APPLICATION ID:", app_id)
        print("NEW STATUS:", result.status.value)
        print("DATABASE STATUS:", app["current_status"])
        print("PERSISTED:", result.persisted)
        print("SAVED RUN COUNT:", len(history))
        print("RUN TRIGGERS:", sorted(row["trigger"] for row in runs))
        print("BANK PDF VERSIONS:", versions)
        print("EXTRACTION ERROR:", result.extraction_error)
        print("EXPECTED:", "PASS" if (
            result.status.value == "APPROVED" and app["current_status"] == "APPROVED"
            and result.persisted and not result.extraction_error and len(history) == 2
            and sorted(row["trigger"] for row in runs) == ["resubmission", "submission"]
            and versions == [1, 2]) else "NOT MET")


if __name__ == "__main__":
    main()
