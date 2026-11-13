"""Generate SYNTHETIC photo and scan fixtures for B7 (photos, scans, OCR grounding).

Every image is clearly marked SAMPLE and uses invented companies, numbers and a
fictional bank. Layout and tilt are seeded; sensor noise differs on each run, so a
re-run gives visually equivalent (not byte-identical) files.

  photo_cheque    clear phone-style photo of a cancelled cheque  -> Approved
  photo_blurry    the same kind of photo, out of focus           -> waiting on vendor
                  (+ cheque_photo_clear.jpg, the retake            -> Approved)
  scanned_letter  image-only (scanned) PDF bank letter            -> Approved

Each photo carries its true values in a JPEG comment
("vendorflow-test-ground-truth:{...}"). ONLY the offline test double for Gemini
reads it (it stands in for a vision model that reads the photo correctly); the
OCR grounding is real Tesseract on the real pixels, and the Gemini path strips
all metadata before sending an image.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from create_fixtures import pdf as text_pdf

BASE = Path(__file__).resolve().parents[1] / "fixtures"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
GROUND_TRUTH = "vendorflow-test-ground-truth:"

CASES = {
    "photo_cheque": {
        "legal_name": "Lotus Demo Traders Private Limited", "gstin": "27LOTUS1234A1ZE",
        "business_state": "Maharashtra", "address": "Demo Market Road, Pune, Maharashtra",
        "account_number": "004455667788", "ifsc": "DEMO0654321", "branch": "Demo Branch, Pune",
    },
    "photo_blurry": {
        "legal_name": "Kestrel Sample Supplies Private Limited", "gstin": "29KESTR5678B1ZA",
        "business_state": "Karnataka", "address": "Sample Tech Park, Bengaluru, Karnataka",
        "account_number": "007788990011", "ifsc": "DEMO0778899", "branch": "Demo Branch, Bengaluru",
    },
    "scanned_letter": {
        "legal_name": "Heron Demo Logistics Private Limited", "gstin": "07HERON4321C1ZI",
        "business_state": "Delhi", "address": "Demo Cargo Lane, New Delhi, Delhi",
        "account_number": "003322114455", "ifsc": "DEMO0332211", "branch": "Demo Branch, New Delhi",
    },
}


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def cheque(case: dict, rng: random.Random) -> Image.Image:
    """Flat cheque artwork (before the 'camera')."""
    w, h = 1500, 680
    paper = Image.new("RGB", (w, h), (233, 240, 247))
    d = ImageDraw.Draw(paper)
    for y in range(0, h, 9):  # faint security pattern
        d.arc((-200, y - 40, w + 200, y + 40), 0, 180, fill=(219, 229, 240), width=1)
    d.rectangle((0, 0, w - 1, h - 1), outline=(150, 170, 195), width=4)
    d.text((40, 30), "SAMPLE DEMO BANK", font=font(BOLD, 46), fill=(22, 49, 81))
    d.text((42, 88), "Fictional bank - synthetic test cheque - not valid for payment", font=font(FONT, 21), fill=(70, 90, 115))
    d.rectangle((1180, 26, 1460, 100), outline=(190, 30, 30), width=5)
    d.text((1212, 33), "SAMPLE", font=font(BOLD, 50), fill=(190, 30, 30))
    # Crossing with CANCELLED between two lines (top-left area, away from the printed details).
    d.line((90, 245, 520, 135), fill=(190, 30, 30), width=5)
    d.line((120, 285, 550, 175), fill=(190, 30, 30), width=5)
    stamp = Image.new("RGBA", (420, 70), (0, 0, 0, 0))
    ImageDraw.Draw(stamp).text((10, 6), "CANCELLED", font=font(BOLD, 48), fill=(190, 30, 30, 255))
    stamp = stamp.rotate(14, expand=True, resample=Image.BICUBIC)
    paper.paste(stamp, (150, 120), stamp)
    d.text((620, 150), "Date: __ / __ / ____", font=font(FONT, 26), fill=(60, 70, 85))
    ink = (25, 30, 45)
    rows = [("Account holder:", case["legal_name"]), ("Account number:", case["account_number"]),
            ("IFSC:", case["ifsc"]), ("Branch:", case["branch"])]
    y = 330
    for label, value in rows:
        d.text((60, y), label, font=font(BOLD, 30), fill=ink)
        d.text((380, y), value, font=font(FONT, 32), fill=ink)
        y += 66
    d.text((60, 610), "C 000000 C 000000000 A 00", font=font(MONO, 26), fill=(80, 85, 95))
    return paper


def camera(paper: Image.Image, rng: random.Random, *, blur: float = 0.0) -> Image.Image:
    """Phone-photo look: table background, slight tilt and perspective, drop shadow,
    uneven light with a soft shadow across one corner, sensor noise, JPEG later."""
    W, H = 2000, 1300
    table = Image.linear_gradient("L").resize((W, H))
    table = Image.merge("RGB", [table.point(lambda v: 120 + v // 5), table.point(lambda v: 100 + v // 6),
                                table.point(lambda v: 80 + v // 7)])
    tilt = rng.uniform(-3.0, -2.0)
    rotated = paper.convert("RGBA").rotate(tilt, expand=True, resample=Image.BICUBIC)
    x, y = (W - rotated.width) // 2 + 20, (H - rotated.height) // 2 - 10
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rectangle((x + 18, y + 22, x + rotated.width + 10, y + rotated.height + 14), fill=(0, 0, 0, 120))
    table = Image.alpha_composite(table.convert("RGBA"), shadow.filter(ImageFilter.GaussianBlur(18)))
    table.alpha_composite(rotated, (x, y))
    photo = table.convert("RGB")
    # Mild perspective (phone not perfectly parallel to the table).
    photo = photo.transform((W, H), Image.PERSPECTIVE, (1.0, 0.012, -8, 0.004, 1.0, -6, 0.000006, 0.000004),
                            resample=Image.BICUBIC, fillcolor=(118, 99, 80))
    # Uneven light: darker towards the bottom-right, like a hand/phone shadow.
    light = Image.new("L", (W, H), 255)
    ImageDraw.Draw(light).ellipse((1100, 750, 2600, 1900), fill=150)
    light = light.filter(ImageFilter.GaussianBlur(160))
    photo = Image.composite(photo, Image.new("RGB", (W, H), (0, 0, 0)), light)
    noise = Image.effect_noise((W, H), 18).convert("RGB")
    photo = Image.blend(photo, noise, 0.06)
    photo = photo.filter(ImageFilter.GaussianBlur(0.7 + blur))
    return photo


def save_photo(photo: Image.Image, path: Path, case: dict) -> None:
    truth = {"holder_name": case["legal_name"], "account_number": case["account_number"], "ifsc": case["ifsc"]}
    exif = Image.Exif()
    exif[0x010F] = "SampleCam"   # Make
    exif[0x0110] = "Demo Phone"  # Model
    photo.save(path, "JPEG", quality=84, comment=(GROUND_TRUTH + json.dumps(truth)).encode(), exif=exif)


def scanned_pdf(path: Path, case: dict, rng: random.Random) -> None:
    """A bank letter printed, scanned in grey and saved as an image-only PDF (no text layer)."""
    page = Image.new("L", (1700, 2200), 246)
    d = ImageDraw.Draw(page)
    d.text((120, 120), "SAMPLE DEMO BANK", font=font(BOLD, 64), fill=20)
    d.text((120, 210), "BANK ACCOUNT CONFIRMATION - SAMPLE", font=font(BOLD, 40), fill=30)
    d.text((120, 270), "Synthetic scanned letter - training and demo only", font=font(FONT, 30), fill=60)
    rows = [("Account holder:", case["legal_name"]), ("Account number:", case["account_number"]),
            ("IFSC:", case["ifsc"]), ("Branch:", case["branch"]), ("Account type:", "Current")]
    y = 420
    for label, value in rows:
        d.text((120, y), label, font=font(BOLD, 38), fill=25)
        d.text((520, y), value, font=font(FONT, 40), fill=25)
        y += 90
    d.text((120, 2000), "Not issued by any bank. No real financial details.", font=font(FONT, 28), fill=80)
    page = page.rotate(rng.uniform(0.4, 0.9), expand=False, fillcolor=246, resample=Image.BICUBIC)
    page = Image.blend(page, Image.effect_noise(page.size, 22), 0.05).filter(ImageFilter.GaussianBlur(0.6))
    tmp = path.with_suffix(".png")
    page.save(tmp, "PNG")
    doc = pymupdf.open()
    sheet = doc.new_page(width=595, height=770)
    sheet.insert_image(sheet.rect, filename=str(tmp))
    doc.save(path, garbage=4, deflate=True)
    tmp.unlink()


def main() -> None:
    for name, case in CASES.items():
        rng = random.Random(name)
        folder = BASE / name
        folder.mkdir(parents=True, exist_ok=True)
        text_pdf(folder / "gst_certificate.pdf", "GST REGISTRATION - SAMPLE", [
            ("Legal business name", case["legal_name"]), ("GSTIN", case["gstin"]),
            ("Business state", case["business_state"]), ("Business address", case["address"]),
        ])
        if name == "scanned_letter":
            scanned_pdf(folder / "bank_scan.pdf", case, rng)
        else:
            save_photo(camera(cheque(case, rng), rng, blur=3.2 if name == "photo_blurry" else 0.0),
                       folder / "cheque_photo.jpg", case)
            if name == "photo_blurry":  # the vendor's retake, for the "upload a clearer copy" loop
                save_photo(camera(cheque(case, rng), rng), folder / "cheque_photo_clear.jpg", case)
        submission = {"legal_name": case["legal_name"], "business_state": case["business_state"],
                      "contact_name": "Demo Contact", "contact_email": "demo@example.com",
                      "gstin": case["gstin"], "pan": case["gstin"][2:12], "bank_holder": case["legal_name"],
                      "account_number": case["account_number"], "ifsc": case["ifsc"]}
        (folder / "submission.json").write_text(json.dumps(submission, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
