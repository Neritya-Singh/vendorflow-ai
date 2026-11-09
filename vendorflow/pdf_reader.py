"""Safe, bounded PDF intake; all input is synthetic for the prototype."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import pymupdf as fitz

MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 10  # extra safety limit for a two-document onboarding case


class UploadError(ValueError):
    """Document must be corrected before the application can be processed."""


@dataclass(frozen=True)
class PDFInput:
    filename: str
    content: bytes


@dataclass(frozen=True)
class ReadPDF:
    filename: str
    sha256: str
    pages: int
    text: str
    readable: bool
    issue: str | None = None


def read_pdf(upload: PDFInput | None) -> ReadPDF | None:
    if upload is None:
        return None
    if not upload.filename.casefold().endswith(".pdf"):
        raise UploadError("Only .pdf documents are accepted. Upload a PDF file.")
    if not upload.content.startswith(b"%PDF-"):
        raise UploadError("This file does not appear to be a PDF. Please upload a PDF.")
    if len(upload.content) > MAX_PDF_BYTES:
        raise UploadError("The PDF exceeds 5 MB. Please upload a smaller file.")
    if len(upload.content) == 0:
        raise UploadError("The uploaded PDF is empty.")

    digest = sha256(upload.content).hexdigest()
    try:
        with fitz.open(stream=upload.content, filetype="pdf") as document:
            pages = document.page_count
            if document.needs_pass:
                return ReadPDF(upload.filename, digest, pages, "", False, "Password-protected PDF")
            if pages == 0 or pages > MAX_PDF_PAGES:
                return ReadPDF(upload.filename, digest, pages, "", False, "Invalid or excessive page count")
            text = "\n".join(page.get_text("text") for page in document).strip()
            if len(text) < 25:
                return ReadPDF(upload.filename, digest, pages, text, False, "No readable text found")
            return ReadPDF(upload.filename, digest, pages, text, True)
    except (fitz.FileDataError, fitz.EmptyFileError, RuntimeError, ValueError):
        return ReadPDF(upload.filename, digest, 0, "", False, "Unreadable or damaged PDF")
