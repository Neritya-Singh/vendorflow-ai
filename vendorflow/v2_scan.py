"""VendorFlow v2 B7: scans and photos. New beside the v1.1 PDF reader.

Accepted: text PDFs (read as before), image-only PDFs (pages rendered, then OCR)
and JPG/PNG photos (OCR). Local Tesseract OCR gives the GROUNDING text that R13
checks every extracted value against; the extraction itself comes from the
provider's image input (Gemini). If OCR cannot confirm a value, R13 fails and the
vendor is asked for a clearer copy: fail closed, never "trust the model".

Images go to the provider re-encoded from pixels only (no EXIF/GPS/comments).
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from hashlib import sha256

import pymupdf
from PIL import Image, ImageFilter, ImageMath, ImageOps, UnidentifiedImageError

from .pdf_reader import MAX_PDF_BYTES, MAX_PDF_TEXT_CHARS, PDFInput, ReadPDF, UploadError, read_pdf

MAX_BYTES = MAX_PDF_BYTES                 # 5 MB for every accepted type
MAX_IMAGE_PIXELS = 40_000_000             # decompression-bomb guard (a 12 MP phone photo is fine)
MAX_OCR_PAGES = 3                         # scanned PDFs: OCR at most the first 3 pages
OCR_TIMEOUT_SECONDS = 25
PROVIDER_MAX_SIDE = 2000                  # image sent to the provider
SCAN_DPI = 300
MIN_TEXT = 25                              # same threshold as the v1.1 PDF reader

EXTENSIONS = {".pdf": "pdf", ".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png"}
MIME_TYPES = {"pdf": "application/pdf", "jpeg": "image/jpeg", "png": "image/png"}


class OCRUnavailable(RuntimeError):
    """Tesseract missing or failed. Never carries document text."""


@dataclass(frozen=True)
class ReadDocument(ReadPDF):
    """ReadPDF plus how the text was obtained. `text` is the grounding text."""
    kind: str = "pdf"                                   # pdf | jpeg | png
    ocr: bool = False                                   # text came from Tesseract
    images: tuple[bytes, ...] = field(default=(), repr=False)  # original photo / rendered scan pages (PNG)
    ocr_ms: int = 0


def file_kind(filename: str, content: bytes) -> str:
    """'pdf' | 'jpeg' | 'png' when the extension AND the magic bytes agree, else UploadError."""
    ext = os.path.splitext(filename.casefold())[1]
    expected = EXTENSIONS.get(ext)
    if expected is None:
        raise UploadError("Upload a PDF, JPG or PNG file.")
    if not content:
        raise UploadError("The uploaded file is empty.")
    if len(content) > MAX_BYTES:
        raise UploadError("The file exceeds 5 MB. Please upload a smaller file.")
    actual = ("pdf" if content.startswith(b"%PDF-") else "jpeg" if content.startswith(b"\xff\xd8\xff")
              else "png" if content.startswith(b"\x89PNG\r\n\x1a\n") else None)
    if actual != expected:
        raise UploadError("This file isn't the type its name says. Upload a PDF, JPG or PNG file.")
    return actual


def content_type(filename: str) -> str:
    return MIME_TYPES[EXTENSIONS[os.path.splitext(filename.casefold())[1]]]


# ---------------------------------------------------------------- metadata

_JPEG_KEEP_APP = {0xE0, 0xE2, 0xEE}       # JFIF, ICC profile, Adobe (colour transform)
_PNG_KEEP = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM", b"sRGB",
             b"iCCP", b"sBIT", b"bKGD", b"pHYs"}


def _orientation(content: bytes) -> int:
    try:
        with Image.open(io.BytesIO(content)) as image:
            return int(image.getexif().get(0x0112, 1) or 1)
    except Exception:
        return 1


def _strip_jpeg(content: bytes) -> bytes:
    """Drop EXIF/XMP (APP1), IPTC (APP13), other APPn and comments; pixels untouched."""
    out, i = bytearray(content[:2]), 2
    while i + 4 <= len(content):
        if content[i] != 0xFF:
            raise UploadError("This image is damaged or can't be opened. Upload it again.")
        marker = content[i + 1]
        if marker == 0xFF:                      # fill byte
            i += 1
            continue
        if marker == 0xDA:                      # start of scan: the rest is image data
            out += content[i:]
            return bytes(out)
        length = int.from_bytes(content[i + 2:i + 4], "big")
        segment = content[i:i + 2 + length]
        if not ((0xE0 <= marker <= 0xEF and marker not in _JPEG_KEEP_APP) or marker == 0xFE):
            out += segment
        i += 2 + length
    raise UploadError("This image is damaged or can't be opened. Upload it again.")


def _strip_png(content: bytes) -> bytes:
    """Keep only image/colour chunks: drops eXIf, tEXt/zTXt/iTXt, tIME and unknown chunks."""
    out, i = bytearray(content[:8]), 8
    while i + 12 <= len(content):
        length = int.from_bytes(content[i:i + 4], "big")
        kind = content[i + 4:i + 8]
        if kind in _PNG_KEEP:
            out += content[i:i + 12 + length]
        i += 12 + length
        if kind == b"IEND":
            return bytes(out)
    raise UploadError("This image is damaged or can't be opened. Upload it again.")


def strip_metadata(kind: str, content: bytes) -> bytes:
    """The photo we STORE as evidence carries no EXIF/GPS, camera data or comments.
    Lossless (pixels unchanged) unless an EXIF rotation must be applied first; then the
    upright pixels are re-encoded at high quality. PDFs are returned as they are.
    Idempotent: a stripped file comes back byte-for-byte the same."""
    if kind not in ("jpeg", "png"):
        return content
    if _orientation(content) != 1:
        image = _open_image(content)            # upright; the strip below drops any metadata left
        buffer = io.BytesIO()
        if kind == "jpeg":
            image.convert("RGB").save(buffer, "JPEG", quality=95, subsampling=0)
        else:
            image.save(buffer, "PNG")
        content = buffer.getvalue()
    return _strip_jpeg(content) if kind == "jpeg" else _strip_png(content)


# ---------------------------------------------------------------- OCR

def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def _prepare(image: Image.Image) -> Image.Image:
    """Grey, upright, upscaled, with uneven lighting (shadows) flattened."""
    grey = ImageOps.exif_transpose(image).convert("L")
    longest = max(grey.size)
    if longest < 2400:
        scale = 2400 / longest
        grey = grey.resize((round(grey.width * scale), round(grey.height * scale)), Image.LANCZOS)
    # Flatten lighting: divide by a heavily blurred copy (the background estimate).
    background = grey.filter(ImageFilter.GaussianBlur(radius=max(grey.size) // 40))
    ratio = ImageMath.lambda_eval(lambda e: e["min"](e["g"] * 235 / e["max"](e["b"], 1), 255),
                                  g=grey.convert("F"), b=background.convert("F"))
    out = ratio.convert("L")
    return ImageOps.autocontrast(out, cutoff=1)


def ocr_image(image: Image.Image) -> str:
    """Tesseract (eng, automatic page segmentation). Raises OCRUnavailable."""
    if not tesseract_available():
        raise OCRUnavailable("OCR is not installed")
    buffer = io.BytesIO()
    _prepare(image).save(buffer, "PNG")
    try:
        done = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", "eng", "--psm", "3"],
            input=buffer.getvalue(), capture_output=True, timeout=OCR_TIMEOUT_SECONDS,
            env={**os.environ, "OMP_THREAD_LIMIT": "1"}, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        raise OCRUnavailable("OCR failed") from None
    if done.returncode != 0:
        raise OCRUnavailable("OCR failed")
    return done.stdout.decode("utf-8", "replace")


# ---------------------------------------------------------------- reading

_CACHE: OrderedDict[str, ReadDocument] = OrderedDict()
_CACHE_SIZE = 24
_LOCK = threading.Lock()
OCR_UNAVAILABLE = "Text recognition unavailable"


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def _open_image(content: bytes) -> Image.Image:
    try:
        image = Image.open(io.BytesIO(content))
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise UploadError("This image is too large. Upload a photo under 40 megapixels.")
        image.load()
        return ImageOps.exif_transpose(image)
    except UploadError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise UploadError("This image is damaged or can't be opened. Upload it again.") from None


def _scan_pages(content: bytes) -> list[Image.Image]:
    with pymupdf.open(stream=content, filetype="pdf") as document:
        return [Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                for pix in (page.get_pixmap(dpi=SCAN_DPI, colorspace=pymupdf.csRGB, alpha=False)
                            for page in list(document)[:MAX_OCR_PAGES])]


def read_document(upload: PDFInput | None) -> ReadDocument | None:
    """Pipeline/draft reader for PDFs, scanned PDFs and photos. Raises UploadError for a
    file that isn't what it says; returns readable=False when no usable text is found."""
    if upload is None:
        return None
    kind = file_kind(upload.filename, upload.content)
    digest = sha256(upload.content).hexdigest()
    with _LOCK:
        if digest in _CACHE:
            _CACHE.move_to_end(digest)
            hit = _CACHE[digest]
            return ReadDocument(**{**hit.__dict__, "filename": upload.filename})
    if kind == "pdf":
        base = read_pdf(upload)
        if base.readable or base.issue != "No readable text found":
            return ReadDocument(**base.__dict__, kind="pdf")  # text PDF (or a hard PDF problem): as before
        pages = _scan_pages(upload.content)
        page_count = base.pages
    else:
        pages = [_open_image(upload.content)]
        page_count = 1
    start = os.times().elapsed
    try:
        text = "\n".join(ocr_image(page) for page in pages).strip()
    except OCRUnavailable:
        return ReadDocument(upload.filename, digest, page_count, "", False, OCR_UNAVAILABLE, kind=kind, ocr=True)
    ocr_ms = round((os.times().elapsed - start) * 1000)
    images = tuple(_png(page) for page in pages) if kind == "pdf" else (upload.content,)
    if len(text) > MAX_PDF_TEXT_CHARS:
        result = ReadDocument(upload.filename, digest, page_count, "", False,
                              "Too much text; upload a shorter document", kind=kind, ocr=True)
    else:
        readable = len(text) >= MIN_TEXT
        result = ReadDocument(upload.filename, digest, page_count, text, readable,
                              None if readable else "No readable text found", kind=kind, ocr=True,
                              images=images, ocr_ms=ocr_ms)
    with _LOCK:
        _CACHE[digest] = result
        while len(_CACHE) > _CACHE_SIZE:
            _CACHE.popitem(last=False)
    return result


def provider_image(data: bytes) -> bytes:
    """JPEG rebuilt from pixels only: upright, at most 2000 px, no EXIF/GPS/comments."""
    image = _open_image(data).convert("RGB")
    image.thumbnail((PROVIDER_MAX_SIDE, PROVIDER_MAX_SIDE), Image.LANCZOS)
    image = Image.frombytes("RGB", image.size, image.tobytes())  # drops info: EXIF, comments, ICC
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=90)
    return buffer.getvalue()
