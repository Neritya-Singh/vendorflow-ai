"""VendorFlow AI: genuine Supabase admin-action acceptance test.

Run from VendorFlow_AI project root, after check_resubmission_live.py was installed:
  python scripts/check_admin_actions_live.py start
  python scripts/check_admin_actions_live.py finish

`start` creates three NEW, SYNTHETIC PENDING test applications. It uses actual
Gemini extraction for the document-backed examples and actual Supabase storage.
`finish` executes three different admin actions and checks persisted results.
The one-time tracking tokens are saved only in a chmod-600 local state file.
No real tax, bank, or identity verification takes place.

CAUTION: The finish step writes real, persistent manual audit actions. Do not
rerun it after a partial error before examining the Supabase rows.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
from vendorflow import GeminiExtractor, PDFInput, VendorSubmission
from vendorflow.persistence import SupabaseRepository, PersistentVendorService

# The earlier verified synthetic-PDF generator lives beside this file.
from check_resubmission_live import make_bank, make_gst, make_vendor

STATE_DIR = Path.home() / ".local" / "share" / "vendorflow_ai_demo"
STATE_FILE = STATE_DIR / "live_admin_state.json"


def new_state() -> dict:
    STATE_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(STATE_DIR, 0o700)
    descriptor = os.open(STATE_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    record = {"cases": {}}
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(record, handle)
    return record


def save_state(record: dict) -> None:
    # State file was created with mode 0600; preserve it across updates.
    with STATE_FILE.open("w", encoding="utf-8") as handle:
        json.dump(record, handle)
        handle.write("\n")
    os.chmod(STATE_FILE, 0o600)


def get_status(repo: SupabaseRepository, application_id: str) -> str:
    return repo._application(application_id)["current_status"]


def check_initial(repo, receipt, *, expected_rule: str) -> None:
    checks = {check.rule_id: check.state.value for check in receipt.result.checks}
    if not (receipt.result.status.value == "PENDING"
            and receipt.result.persisted
            and not receipt.result.extraction_error
            and checks.get(expected_rule) == "FAIL"
            and get_status(repo, receipt.application_id) == "PENDING"
            and len(repo.runs_for_application(receipt.application_id)) == 1):
        raise RuntimeError(
            "New application did not meet its expected PENDING criteria. "
            "Inspect Supabase before attempting another run."
        )


def start(repo: SupabaseRepository, service: PersistentVendorService) -> None:
    if STATE_FILE.exists():
        raise SystemExit(
            f"Admin test state already exists: {STATE_FILE}. "
            "Do not run start twice; report this message."
        )
    state = new_state()
    print("Creating three synthetic PENDING applications for admin review ...", flush=True)

    # A: Real, consistent PDFs but missing a form contact name. The admin can
    # exercise the override action after *hypothetical* supplementary review.
    approval_vendor = make_vendor().model_copy(update={"contact_name": ""})
    approval = service.submit(
        approval_vendor,
        make_gst(approval_vendor),
        make_bank(approval_vendor.account_number, missing_holder=False),
    )
    state["cases"]["approve"] = {
        "application_id": approval.application_id,
        "tracking_code": approval.tracking_code,
    }
    save_state(state)
    check_initial(repo, approval, expected_rule="R01")
    print("APPROVAL CASE: PENDING | R01 FAIL | SAVED RUNS: 1 | PASS", flush=True)

    # B: Existing-approved-GSTIN duplicate. Stage 3.3's actual earlier approved
    # happy-path application is intentionally used for this duplicate check.
    folder = ROOT / "fixtures" / "ec3_duplicate_changed_bank"
    duplicate_vendor = VendorSubmission.model_validate_json(
        (folder / "submission.json").read_text(encoding="utf-8")
    )
    duplicate = service.submit(
        duplicate_vendor,
        PDFInput("gst_certificate.pdf", (folder / "gst_certificate.pdf").read_bytes()),
        PDFInput("bank_confirmation.pdf", (folder / "bank_confirmation.pdf").read_bytes()),
    )
    state["cases"]["reject"] = {
        "application_id": duplicate.application_id,
        "tracking_code": duplicate.tracking_code,
    }
    save_state(state)
    check_initial(repo, duplicate, expected_rule="R12")
    print("REJECTION CASE: PENDING | R12 FAIL | SAVED RUNS: 1 | PASS", flush=True)

    # C: Genuine incomplete intake. Request correction should leave it PENDING.
    correction_vendor = make_vendor()
    correction = service.submit(correction_vendor, make_gst(correction_vendor), None)
    state["cases"]["request_correction"] = {
        "application_id": correction.application_id,
        "tracking_code": correction.tracking_code,
    }
    save_state(state)
    check_initial(repo, correction, expected_rule="R02")
    print("CORRECTION CASE: PENDING | R02 FAIL | SAVED RUNS: 1 | PASS", flush=True)

    print("STATE SAVED PRIVATELY: YES", flush=True)
    print("EXPECTED: PASS", flush=True)
    print("Do not share tracking credentials or rerun 'start'.", flush=True)


def finish(repo: SupabaseRepository, service: PersistentVendorService) -> None:
    if not STATE_FILE.exists():
        raise SystemExit("No admin-test state found. Run 'start' first.")
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    cases = state.get("cases", {})
    if set(cases) != {"approve", "reject", "request_correction"}:
        raise SystemExit("Admin-test setup is incomplete; do not execute manual actions.")

    # Confirm all three test cases are untouched before *any* writes.
    original_runs = {}
    for name, credentials in cases.items():
        app_id, token = credentials["application_id"], credentials["tracking_code"]
        app, runs = service.track(app_id, token)
        if (app["current_status"] != "PENDING" or len(runs) != 1
                or repo.review_history(app_id)):
            raise SystemExit(f"Case '{name}' was already modified; no new writes performed.")
        original_runs[name] = runs[0]["id"]

    actions = [
        ("request_correction", "REQUEST_CORRECTION",
         "Please upload a bank confirmation letter showing the account holder and account number.", "PENDING"),
        ("approve", "APPROVE",
         "SYNTHETIC WORKFLOW TEST ONLY: demo reviewer approved after an assumed offline contact confirmation; no official verification performed.", "APPROVED"),
        ("reject", "REJECT",
         "SYNTHETIC WORKFLOW TEST: duplicate GSTIN of an already-approved vendor; second registration rejected after demo review.", "REJECTED"),
    ]
    overall_ok = True
    for name, action, rationale, expected in actions:
        app_id, token = cases[name]["application_id"], cases[name]["tracking_code"]
        record = repo.admin_review(app_id, action, rationale)
        app, runs = service.track(app_id, token)
        audits = repo.review_history(app_id)
        passed = (
            app["current_status"] == expected
            and app["decision_source"] == "MANUAL"
            and len(runs) == 1 and runs[0]["id"] == original_runs[name]
            and len(audits) == 1 and audits[0]["action"] == action
            and audits[0]["reason"] == rationale
            and record["application_id"] == app_id
        )
        overall_ok = overall_ok and passed
        print(f"{action}: {app['current_status']} | SOURCE: {app['decision_source']} "
              f"| AUDIT EVENTS: {len(audits)} | SAVED RUNS: {len(runs)} "
              f"| {'PASS' if passed else 'FAIL'}", flush=True)
        if not passed:
            raise RuntimeError("Admin outcome/audit verification failed; do not retry finish.")

    queue_ids = {row["id"] for row in repo.admin_queue("PENDING")}
    queue_ok = (cases["request_correction"]["application_id"] in queue_ids
                and cases["approve"]["application_id"] not in queue_ids
                and cases["reject"]["application_id"] not in queue_ids)
    print("PENDING QUEUE FILTER: " + ("PASS" if queue_ok else "FAIL"), flush=True)
    print("EXPECTED: " + ("PASS" if overall_ok and queue_ok else "NOT MET"), flush=True)
    print("All outcomes are synthetic prototype decisions, not official legal/bank verification.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Live admin action + audit trail verification")
    parser.add_argument("step", choices=["start", "finish"])
    args = parser.parse_args()
    load_dotenv(ROOT / ".env", override=True)
    repo = SupabaseRepository.from_env()
    service = PersistentVendorService(repo, GeminiExtractor())
    if args.step == "start":
        start(repo, service)
    else:
        finish(repo, service)


if __name__ == "__main__":
    main()
