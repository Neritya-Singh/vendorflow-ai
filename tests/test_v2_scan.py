"""B7 part 2 — scans and photos (OCR grounding).

OFFLINE but with REAL local Tesseract OCR on the real fixture pixels; the
in-memory Supabase double and the label/ground-truth test double stand in for
Supabase and Gemini. These are NOT live Supabase/Gemini tests. Skipped when the
tesseract binary is not installed.
"""
from __future__ import annotations

import io
import json
import time
import types
from pathlib import Path

import pytest
from PIL import Image

from backend import offline
from vendorflow import v2_scan
from vendorflow.gemini_extractor import GeminiExtractor
from vendorflow.pdf_reader import PDFInput, UploadError
from vendorflow.rules import bank_account_grounded, norm_id, norm_name

from tests.test_v2_api import admin, review, stream_events
from tests.test_v2_fix import fix_submit, fix_upload, open_fix
from tests.test_v2_intake import CONTACT, counted, client, creds, submit  # noqa: F401  (pytest fixtures)

pytestmark = pytest.mark.skipif(not v2_scan.tesseract_available(), reason="tesseract-ocr is not installed")
FIX = Path(__file__).resolve().parents[1] / "fixtures"


def load(case: str, name: str) -> bytes:
    return (FIX / case / name).read_bytes()


def truth(case: str) -> dict:
    return json.loads((FIX / case / "submission.json").read_text())


def send(client, c, slot, content, name, mime):
    response = client.post("/api/vendor/draft/files", data={**c, "slot": slot}, files={"file": (name, content, mime)})
    events = stream_events(response)
    assert events[-1]["type"] == "result", events[-1]
    return events


def photo_draft(client, case, bank_name="cheque_photo.jpg", mime="image/jpeg"):
    c = creds(client)
    send(client, c, "GST", load(case, "gst_certificate.pdf"), "gst_certificate.pdf", "application/pdf")
    started = time.perf_counter()
    events = send(client, c, "BANK", load(case, bank_name), bank_name, mime)
    elapsed = time.perf_counter() - started
    view = client.put("/api/vendor/draft/values", json={**c, "contact": CONTACT}).json()
    return c, view, events, elapsed


# ---------------------------------------------------------------- OCR accuracy on the fixtures

@pytest.mark.parametrize("case,name", [("photo_cheque", "cheque_photo.jpg"), ("photo_blurry", "cheque_photo_clear.jpg"),
                                       ("scanned_letter", "bank_scan.pdf")])
def test_ocr_reads_every_bank_value_on_the_clear_fixtures(case, name):
    read = v2_scan.read_document(PDFInput(name, load(case, name)))
    assert read.ocr and read.readable
    want = truth(case)
    # The same comparison R13 makes: names ignore case/punctuation, IFSC ignores spacing,
    # the account number must equal the whole value printed after its label.
    assert norm_name(want["bank_holder"]) in norm_name(read.text), read.text
    assert norm_id(want["ifsc"]) in norm_id(read.text), read.text
    assert bank_account_grounded(want["account_number"], read.text), read.text


def test_ocr_cannot_confirm_the_values_on_the_blurry_photo():
    read = v2_scan.read_document(PDFInput("cheque_photo.jpg", load("photo_blurry", "cheque_photo.jpg")))
    assert read.ocr and read.readable  # some text, so it is not rejected at upload ...
    want = truth("photo_blurry")
    assert not any(want[k] in read.text for k in ("account_number", "ifsc"))  # ... but nothing confirms


# ---------------------------------------------------------------- flows

def test_clear_cheque_photo_is_read_once_grounded_by_ocr_and_approved(counted):
    client, provider = counted
    c, view, events, elapsed = photo_draft(client, "photo_cheque")
    bank = view["files"]["BANK"]
    assert bank["status"] == "read" and bank["message"] == "Read: account holder, account number, IFSC"
    assert [e["stage_id"] for e in events if e["type"] == "stage" and e["event"] == "COMPLETED"] == ["U1", "U2", "U3"]
    assert elapsed < 10, elapsed
    holder = next(f for f in view["fields"] if f["key"] == "bank_holder")
    assert holder["value"] == truth("photo_cheque")["bank_holder"] and holder["status"] == "document"
    assert view["details_ready"], view["blockers"]
    calls = len(provider.calls)
    result = submit(client, c)
    assert result["status"] == "APPROVED", result
    assert len(provider.calls) == calls  # submit reused the photo's reading
    # Reviewer can view the original photo (1 page) and download it as an image.
    csrf = admin(client)
    assert csrf
    case = client.get(f"/api/admin/applications/{c['application_id']}").json()
    run = case["latest_run_id"]
    base = f"/api/admin/applications/{c['application_id']}/runs/{run}/documents/BANK"
    assert client.get(base + "/pages").json()["pages"] == 1
    page = client.get(base + "/pages/1")
    assert page.status_code == 200 and page.headers["content-type"] == "image/png"
    original = client.get(base)
    # The stored evidence is the original photo minus its metadata (EXIF/GPS stripped, pixels unchanged).
    assert original.headers["content-type"] == "image/jpeg"
    assert original.content == v2_scan.strip_metadata("jpeg", load("photo_cheque", "cheque_photo.jpg"))
    assert not Image.open(io.BytesIO(original.content)).getexif()


def test_blurry_photo_waits_on_vendor_for_a_clearer_copy_then_retake_is_approved(counted):
    client, provider = counted
    c, view, _events, _elapsed = photo_draft(client, "photo_blurry")
    assert view["files"]["BANK"]["status"] == "read"  # the (stand-in) vision read it ...
    result = submit(client, c)
    assert result["status"] == "PENDING" and result["owner"] == "VENDOR", result  # ... OCR could not confirm it
    todo = " ".join(t["text"] for t in result["todo"])
    assert "Upload a clearer copy" in todo and "bank document" in todo
    assert "R13" not in todo + " ".join(m["text"] for m in result["messages"])  # item keys are internal; shown text has no rule IDs

    fix = open_fix(client, c).json()
    assert [i["id"] for i in fix["items"]] == ["doc:BANK"]
    fixed = fix_upload(client, c, "BANK", load("photo_blurry", "cheque_photo_clear.jpg"), "retake.jpg")
    assert fixed["ready"], fixed["blockers"]
    calls = len(provider.calls)
    assert fix_submit(client, c)["status"] == "APPROVED"
    assert len(provider.calls) == calls


def test_scanned_pdf_bank_letter_is_ocrd_and_approved(client):
    c, view, _events, _elapsed = photo_draft(client, "scanned_letter", "bank_scan.pdf", "application/pdf")
    assert view["files"]["BANK"]["status"] == "read" and view["details_ready"], view
    assert submit(client, c)["status"] == "APPROVED"


def test_value_the_ocr_cannot_find_is_never_trusted(client):
    """Fail closed: the (stand-in) vision model 'reads' a digit that is not printed."""
    image = Image.open(io.BytesIO(load("photo_cheque", "cheque_photo.jpg")))
    wrong = {**json.loads(image.info["comment"].decode().split(":", 1)[1]), "account_number": "004455667789"}
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=92, comment=("vendorflow-test-ground-truth:" + json.dumps(wrong)).encode())
    offline.register_ground_truth(buffer.getvalue())  # the upload is stripped; the double finds it by pixels
    c = creds(client)
    send(client, c, "GST", load("photo_cheque", "gst_certificate.pdf"), "gst_certificate.pdf", "application/pdf")
    send(client, c, "BANK", buffer.getvalue(), "cheque.jpg", "image/jpeg")
    client.put("/api/vendor/draft/values", json={**c, "contact": CONTACT})
    result = submit(client, c)
    assert result["status"] == "PENDING" and result["owner"] == "VENDOR"
    assert any("clearer copy" in t["text"] for t in result["todo"])


def test_reviewer_can_still_request_a_new_bank_photo(client):
    c, _view, _e, _t = photo_draft(client, "photo_cheque")
    submit(client, c)  # approved: final, so use a team case instead
    c2, _view, _e, _t = photo_draft(client, "photo_cheque")  # same GSTIN as an approved vendor -> team
    result = submit(client, c2)
    assert result["owner"] == "TEAM"
    csrf = admin(client)
    assert review(client, csrf, c2["application_id"], "REQUEST_CORRECTION", "Send a bank letter",
                  items=["doc:BANK"]).status_code == 200
    fixed = fix_upload(client, c2, "BANK", load("photo_cheque", "cheque_photo.jpg"), "again.jpg")
    assert fixed["files"]["BANK"]["status"] == "read"


# ---------------------------------------------------------------- intake safety

def test_upload_type_checks(client):
    c = creds(client)
    png = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(png, "PNG")
    bad = [("cheque.jpg", png.getvalue(), "image/jpeg"),        # name says JPG, bytes are PNG
           ("cheque.gif", b"GIF89a....", "image/gif"),
           ("cheque.png", png.getvalue(), "text/plain")]
    for name, content, mime in bad:
        response = client.post("/api/vendor/draft/files", data={**c, "slot": "BANK"}, files={"file": (name, content, mime)})
        assert response.status_code == 400, (name, response.text)
    view = send(client, c, "BANK", png.getvalue(), "cheque.png", "image/png")[-1]["data"]
    assert view["files"]["BANK"]["status"] == "unreadable"  # blank image: no text, blocked at upload
    # The v1.1-compatible typed endpoint stays PDF-only.
    old = client.post("/api/vendor/applications", data={**creds(client), "legal_name": "X", "contact_email": "a@b.co"},
                      files={"bank_pdf": ("b.jpg", load("photo_cheque", "cheque_photo.jpg"), "image/jpeg")})
    assert old.status_code == 400


def test_decompression_bomb_is_rejected():
    big = io.BytesIO()
    Image.new("1", (8000, 8000), 1).save(big, "PNG")  # 64 MP, tiny file
    with pytest.raises(UploadError):
        v2_scan.read_document(PDFInput("huge.png", big.getvalue()))


def test_ocr_outage_is_our_problem_not_the_vendors(client, monkeypatch):
    monkeypatch.setattr(v2_scan, "tesseract_available", lambda: False)
    image = Image.open(io.BytesIO(load("photo_cheque", "cheque_photo.jpg")))
    fresh = io.BytesIO()
    image.save(fresh, "JPEG", quality=80)  # new bytes: not in the reading cache
    c = creds(client)
    view = send(client, c, "BANK", fresh.getvalue(), "cheque.jpg", "image/jpeg")[-1]["data"]
    assert view["files"]["BANK"]["status"] == "unavailable"
    assert "isn't a problem with your file" in view["files"]["BANK"]["message"]


def test_provider_gets_pixels_only_and_never_the_ocr_text():
    sent = {}

    class Models:
        def generate_content(self, **kwargs):
            sent.update(kwargs)
            return types.SimpleNamespace(text=json.dumps({
                "gst": {"legal_name": None, "gstin": None, "state": None, "address": None},
                "bank": {"holder_name": "Lotus Demo Traders Private Limited", "account_number": "004455667788", "ifsc": "DEMO0654321"}}))

    photo = load("photo_cheque", "cheque_photo.jpg")
    out = GeminiExtractor(client=types.SimpleNamespace(models=Models()), model="gemini-test").extract_images(
        [], [photo], "", "OCR TEXT THAT MUST NOT BE SENT")
    assert out.bank.account_number == "004455667788" and out.gst.gstin is None
    parts = [p for p in sent["contents"] if not isinstance(p, str)]
    assert len(parts) == 1 and parts[0].inline_data.mime_type == "image/jpeg"
    assert "OCR TEXT" not in json.dumps([p for p in sent["contents"] if isinstance(p, str)])
    image = Image.open(io.BytesIO(parts[0].inline_data.data))
    assert "comment" not in image.info and not image.getexif() and max(image.size) <= 2000
