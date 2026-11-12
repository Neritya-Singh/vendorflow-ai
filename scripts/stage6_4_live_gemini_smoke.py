"""STAGING-ONLY, read-only Gemini extraction test on bundled synthetic PDF files.

No Supabase writes or Storage calls. Avoid using actual financial documents.
Loads local .env; never prints secrets, extracted names/IDs or raw API errors.
The SDK uses a single bounded (<=3) attempt policy in GeminiExtractor.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)

EXPECTED_STAGING = "https://hkxalnpnchzheorrogci.supabase.co"
if os.getenv("SUPABASE_URL", "").strip().rstrip("/") != EXPECTED_STAGING:
    raise SystemExit("STOP: expected isolated staging SUPABASE_URL in .env (no test performed)")
if not os.getenv("GEMINI_API_KEY", "").strip():
    raise SystemExit("STOP: GEMINI_API_KEY missing (no test performed)")

sys.path.insert(0, str(ROOT))
from vendorflow.gemini_extractor import GeminiExtractor, ExtractionFailure
from vendorflow.pdf_reader import PDFInput, read_pdf
from vendorflow.rules import norm_id, norm_name, norm_state, bank_account_grounded


def fixture_text(name: str) -> str:
    path = ROOT / "fixtures" / "happy" / name
    value = read_pdf(PDFInput(name, path.read_bytes()))
    if value is None or not value.readable:
        raise RuntimeError("Bundled synthetic fixture cannot be read")
    return value.text


def main() -> int:
    gst_text = fixture_text("gst_certificate.pdf")
    bank_text = fixture_text("bank_confirmation.pdf")
    extractor = GeminiExtractor()
    try:
        result = extractor.extract(gst_text, bank_text)
    except ExtractionFailure as exc:
        print("LIVE GEMINI EXTRACTION: FAIL", extractor.last_diagnostic.summary())
        print("ACTION: inspect local Gemini model/quota and recheck; no application was saved")
        return 1
    # Never print the extracted names, GSTIN, bank details or raw provider content.
    matches = (
        bool(result.gst.legal_name) and norm_name(result.gst.legal_name) in norm_name(gst_text),
        bool(result.gst.gstin) and norm_id(result.gst.gstin) in norm_id(gst_text),
        bool(result.gst.state) and norm_state(result.gst.state) in norm_state(gst_text),
        bool(result.bank.holder_name) and norm_name(result.bank.holder_name) in norm_name(bank_text),
        bank_account_grounded(result.bank.account_number, bank_text),
        bool(result.bank.ifsc) and norm_id(result.bank.ifsc) in norm_id(bank_text),
    )
    if not all(matches):
        print("LIVE GEMINI EXTRACTION: FAIL (one or more critical fields missing / unsupported)")
        print(extractor.last_diagnostic.summary())
        print("ACTION: document must remain Pending Review; no application was saved")
        return 1
    print("LIVE GEMINI EXTRACTION: PASS (6/6 fields grounded in synthetic PDFs)")
    print(extractor.last_diagnostic.summary())
    print("CLEAN: no Supabase database or Storage operations performed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        # No provider payload, credentials, or raw documents in console errors.
        raise SystemExit("LIVE GEMINI EXTRACTION: FAIL (local setup or fixture issue)") from None
