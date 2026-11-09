"""Live Supabase + Gemini smoke test. Run ONLY after the Supabase SQL setup.

Creates a real SYNTHETIC application record and versioned private PDF objects.
This is NOT a mock; it will write to the connected Supabase project.
"""
import argparse
from pathlib import Path
from dotenv import load_dotenv
from vendorflow import GeminiExtractor, PDFInput, VendorSubmission
from vendorflow.persistence import SupabaseRepository, PersistentVendorService, PersistenceError


def main():
    root = Path(__file__).resolve().parent
    load_dotenv(root / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=["happy", "ec1_pan_gstin", "ec2_bank_owner",
                                               "ec3_duplicate_changed_bank", "ec4_missing_bank_holder"],
                        default="happy")
    args = parser.parse_args()
    folder = root / "fixtures" / args.scenario
    vendor = VendorSubmission.model_validate_json((folder / "submission.json").read_text())
    gst = PDFInput("gst_certificate.pdf", (folder / "gst_certificate.pdf").read_bytes())
    bank = PDFInput("bank_confirmation.pdf", (folder / "bank_confirmation.pdf").read_bytes())
    repo = SupabaseRepository.from_env()
    service = PersistentVendorService(repo, GeminiExtractor())
    receipt = service.submit(vendor, gst, bank,
                             stage_callback=lambda e: print(f"[{e.stage_id}] {e.event}: {e.note}"))
    app, history = service.track(receipt.application_id, receipt.tracking_code)
    print("\nSTATUS:", receipt.result.status.value)
    print("REASONS:", receipt.result.reasons)
    print("APP ID:", receipt.application_id)
    print("TRACKING CODE (PRIVATE, store securely):", receipt.tracking_code)
    print("DATABASE STATUS:", app["current_status"])
    print("PERSISTED:", receipt.result.persisted)
    print("SAVED RUN COUNT:", len(history))
    print("ELAPSED MS:", receipt.result.elapsed_ms)
    print("\nNever paste your tracking code or .env credentials into chat.")


if __name__ == "__main__":
    main()
