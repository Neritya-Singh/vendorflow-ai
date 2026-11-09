"""Local LIVE-Gemini integration CLI (no fake answers; nothing persisted yet)."""
import argparse
import json
from pathlib import Path
from dotenv import load_dotenv
from vendorflow import VendorSubmission, PDFInput, ProcessingPipeline, GeminiExtractor


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Run a real Gemini PDF extraction and local policy check")
    parser.add_argument("--scenario", default="happy", help="Name of a synthetic scenario in fixtures/")
    parser.add_argument("--demo-empty-registry", action="store_true", help="Assume no approved vendors ONLY for local standalone smoke test")
    args = parser.parse_args()
    location = Path(__file__).parent / "fixtures" / args.scenario
    vendor = VendorSubmission.model_validate_json((location / "submission.json").read_text())
    gst = PDFInput("gst_certificate.pdf", (location / "gst_certificate.pdf").read_bytes())
    bank = PDFInput("bank_confirmation.pdf", (location / "bank_confirmation.pdf").read_bytes())
    lookup = (lambda gstin, application_id: []) if args.demo_empty_registry else None
    engine = ProcessingPipeline(GeminiExtractor(), approved_lookup=lookup)
    result = engine.evaluate(vendor, gst, bank, stage_callback=lambda event:
                             print(f"[{event.stage_id}] {event.event}: {event.label} {event.note}"))
    public = {
        "application_id": result.application_id, "run_id": result.run_id,
        "status": result.status, "reasons": result.reasons,
        "next_action": result.next_action, "elapsed_ms": result.elapsed_ms,
        "persisted": result.persisted, "extraction_error": result.extraction_error,
        "checks": [{"rule_id": x.rule_id, "result": x.state, "code": x.code} for x in result.checks],
    }
    print("\nRESULT (local, NOT yet saved to Supabase)")
    print(json.dumps(public, indent=2))


if __name__ == "__main__":
    main()
