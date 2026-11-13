"""B10 fix: the STORED original photo carries no EXIF/GPS (not just the Gemini copy). Offline."""
from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from PIL import Image, PngImagePlugin

from vendorflow import v2_intake
from vendorflow.pdf_reader import PDFInput, UploadError
from vendorflow.v2_scan import strip_metadata

GPS_IFD = 0x8825


def _photo(orientation: int = 1, size=(60, 40)) -> bytes:
    image = Image.new("RGB", size, (240, 240, 240))
    image.paste((200, 0, 0), (0, 0, 16, 10))   # a red block top-left, to check rotation
    exif = Image.Exif()
    exif[0x010F] = "SynthCam"                  # Make
    exif[0x0112] = orientation                 # Orientation
    exif[GPS_IFD] = {1: "N", 2: (12.0, 58.0, 0.0), 3: "E", 4: (77.0, 35.0, 0.0)}
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", exif=exif, quality=95, comment=b"synthetic comment")
    return buffer.getvalue()


def _clean(content: bytes) -> Image.Image:
    image = Image.open(io.BytesIO(content))
    image.load()
    assert not image.getexif(), "EXIF left in stored file"
    assert "comment" not in image.info and "exif" not in image.info and "xmp" not in image.info
    return image


def test_jpeg_gps_and_camera_data_removed_without_touching_pixels():
    original = _photo()
    assert Image.open(io.BytesIO(original)).getexif().get_ifd(GPS_IFD)  # the fixture really has GPS
    stripped = strip_metadata("jpeg", original)
    assert b"Exif" not in stripped and b"SynthCam" not in stripped and b"synthetic comment" not in stripped
    image = _clean(stripped)
    # Lossless: the compressed image data after SOS is byte-identical.
    assert stripped[stripped.index(b"\xff\xda"):] == original[original.index(b"\xff\xda"):]
    assert image.tobytes() == Image.open(io.BytesIO(original)).tobytes()


def test_rotated_photo_is_stored_upright_without_metadata():
    stripped = strip_metadata("jpeg", _photo(orientation=6))  # 90° clockwise
    image = _clean(stripped)
    assert image.size == (40, 60)
    r, g, b = image.getpixel((36, 4))           # red block now top-right
    assert r > 150 and g < 90 and b < 90


def test_png_text_and_exif_chunks_removed():
    info = PngImagePlugin.PngInfo()
    info.add_text("Comment", "synthetic secret")
    info.add_itxt("GPS", "12.9N 77.5E")
    exif = Image.Exif()
    exif[0x010F] = "SynthCam"
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20), "white").save(buffer, "PNG", pnginfo=info, exif=exif)
    stripped = strip_metadata("png", buffer.getvalue())
    for marker in (b"tEXt", b"iTXt", b"eXIf", b"synthetic secret", b"SynthCam"):
        assert marker not in stripped
    image = _clean(stripped)
    assert not {k for k in image.info if k not in ("dpi",)}


@pytest.mark.parametrize("orientation", [1, 6])
def test_idempotent(orientation):
    once = strip_metadata("jpeg", _photo(orientation))
    assert strip_metadata("jpeg", once) == once


def test_pdf_untouched_and_damaged_jpeg_rejected():
    assert strip_metadata("pdf", b"%PDF-1.4 x") == b"%PDF-1.4 x"
    with pytest.raises(UploadError):
        strip_metadata("jpeg", b"\xff\xd8\xff\xe0\x00")


def test_store_document_saves_the_stripped_photo_and_its_hash():
    saved, rows = {}, []

    class Bucket:
        def upload(self, path, file, file_options):
            saved[path] = file

    class Table:
        def insert(self, row):
            rows.append(row)
            return SimpleNamespace(execute=lambda: SimpleNamespace(data=[{**row, "id": "d1"}]))

    repo = SimpleNamespace(BUCKET="vendor-documents", _latest_document_row=lambda a, s: None,
                           client=SimpleNamespace(storage=SimpleNamespace(from_=lambda b: Bucket()),
                                                  table=lambda name: Table()))
    original = _photo()
    row = v2_intake.store_document(repo, "APP-1", "BANK", PDFInput("cheque.jpg", original))
    (stored,) = saved.values()
    assert stored != original and b"Exif" not in stored
    _clean(stored)
    import hashlib
    assert row["file_sha256"] == hashlib.sha256(stored).hexdigest()
