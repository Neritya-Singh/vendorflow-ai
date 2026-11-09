"""Generate unequivocally SYNTHETIC demo PDFs for all five agreed cases."""
from __future__ import annotations
import json
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4

BASE = Path(__file__).resolve().parents[1] / "fixtures"
GSTIN = "09ABCDE1234F1Z5"
PAN = "ABCDE1234F"


def pdf(path: Path, title: str, fields: list[tuple[str, str]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    c.setFillColor(HexColor("#163151"))
    c.rect(0, height-118, width, 118, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(42, height-55, title)
    c.setFont("Helvetica", 10)
    c.drawString(42, height-81, "SYNTHETIC DOCUMENT - TRAINING & DEMO ONLY")
    c.setFillColor(HexColor("#26364A"))
    c.setFont("Helvetica", 11)
    y = height-165
    for name, val in fields:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(42, y, name + ":")
        c.setFont("Helvetica", 11)
        c.drawString(206, y, val)
        y -= 39
    c.setFont("Helvetica-Oblique", 9)
    c.setFillColor(HexColor("#A33B29"))
    c.drawString(42, 80, "Not issued by any government agency or bank. No real financial details.")
    c.save()


def gst(path: Path):
    pdf(path, "GST REGISTRATION - SAMPLE", [
        ("Legal business name", "Acme Widgets Private Limited"),
        ("GSTIN", GSTIN),
        ("Business state", "Uttar Pradesh"),
        ("Business address", "Demo Industrial Area, Lucknow, Uttar Pradesh"),
        ("Trade name", "Acme Workshop"),
    ])


def bank(path: Path, *, holder: str = "Acme Widgets Private Limited", account: str = "001234567890", missing_holder: bool = False):
    fields = [
        ("Bank", "Fictional Demo Bank"),
        ("Letter type", "Account confirmation - sample"),
    ]
    if not missing_holder:
        fields.append(("Account holder", holder))
    fields.extend([
        ("Account number", account),
        ("IFSC", "DEMO0123456"),
    ])
    pdf(path, "BANK CONFIRMATION - SAMPLE", fields)


def main():
    scenarios = {
        "happy": {"pan": PAN, "bank_holder": "Acme Widgets Private Limited", "account_number": "001234567890"},
        "ec1_pan_gstin": {"pan": "PQRST1234U", "bank_holder": "Acme Widgets Private Limited", "account_number": "001234567890"},
        "ec2_bank_owner": {"pan": PAN, "bank_holder": "Ravi Example", "account_number": "001234567890"},
        "ec3_duplicate_changed_bank": {"pan": PAN, "bank_holder": "Acme Widgets Private Limited", "account_number": "009999887766"},
        "ec4_missing_bank_holder": {"pan": PAN, "bank_holder": "Acme Widgets Private Limited", "account_number": "001234567890"},
    }
    for name, overrides in scenarios.items():
        location = BASE / name
        gst(location / "gst_certificate.pdf")
        bank(location / "bank_confirmation.pdf", holder=overrides["bank_holder"], account=overrides["account_number"],
             missing_holder=name == "ec4_missing_bank_holder")
        payload = {
            "legal_name": "Acme Widgets Private Limited",
            "business_state": "Uttar Pradesh",
            "contact_name": "Demo Contact",
            "contact_email": "demo@example.com",
            "gstin": GSTIN,
            "pan": overrides["pan"],
            "bank_holder": overrides["bank_holder"],
            "account_number": overrides["account_number"],
            "ifsc": "DEMO0123456",
        }
        (location / "submission.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (BASE / "README.md").write_text(
        "# Synthetic demo fixtures\n\nAll PDFs and identifiers here are invented for demo use. "
        "They are not government/bank documents and do not establish real identity.\n\n"
        "Test scenarios: happy; ec1_pan_gstin; ec2_bank_owner; "
        "ec3_duplicate_changed_bank (must have a prior APPROVED GSTIN); "
        "ec4_missing_bank_holder.\n", encoding="utf-8")
    print("Created 5 synthetic submission scenarios in", BASE)


if __name__ == "__main__":
    main()
