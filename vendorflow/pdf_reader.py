"""Safe, bounded PDF intake; all input is synthetic for the prototype."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import re
import pymupdf as fitz

MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGES = 10  # extra safety limit for a two-document onboarding case
MAX_PDF_TEXT_CHARS = 24_000  # per document; avoid excessive Gemini prompt/token cost


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
    if len(upload.content) == 0:
        raise UploadError("The uploaded PDF is empty.")
    # Test the byte cap before sniffing/parsing; no oversized input reaches fitz.
    if len(upload.content) > MAX_PDF_BYTES:
        raise UploadError("The PDF exceeds 5 MB. Please upload a smaller file.")
    if not upload.content.startswith(b"%PDF-"):
        raise UploadError("This file does not appear to be a PDF. Please upload a PDF.")

    digest = sha256(upload.content).hexdigest()
    try:
        with fitz.open(stream=upload.content, filetype="pdf") as document:
            pages = document.page_count
            if document.needs_pass:
                return ReadPDF(upload.filename, digest, pages, "", False, "Password-protected PDF")
            if pages == 0 or pages > MAX_PDF_PAGES:
                return ReadPDF(upload.filename, digest, pages, "", False, "Invalid or excessive page count")
            parts: list[str] = []
            chars = 0
            for page in document:
                page_text = page.get_text("text")
                chars += len(page_text)
                if chars > MAX_PDF_TEXT_CHARS:
                    return ReadPDF(upload.filename, digest, pages, "", False,
                                   "Too much extracted text; upload a shorter PDF")
                parts.append(page_text)
            text = "\n".join(parts).strip()
            if len(text) < 25:
                return ReadPDF(upload.filename, digest, pages, text, False, "No readable text found")
            return ReadPDF(upload.filename, digest, pages, text, True)
    except (fitz.FileDataError, fitz.EmptyFileError, RuntimeError, ValueError):
        return ReadPDF(upload.filename, digest, 0, "", False, "Unreadable or damaged PDF")


def likely_swapped_pdf_roles(gst_pdf: ReadPDF | None, bank_pdf: ReadPDF | None) -> bool:
    """Very conservative *hint*, not verification: both distinct headings AND
    labeled identifying fields must appear in the opposite upload slots.

    A single PDF that mentions GSTIN and a bank reference is not sufficient.
    Unreadable or scanned PDFs cannot be confidently diagnosed this way.
    """
    if not (gst_pdf and bank_pdf and gst_pdf.readable and bank_pdf.readable):
        return False
    gst = gst_pdf.text
    bank = bank_pdf.text
    looks_like_bank = (re.search(r"(?im)^\s*BANK CONFIRMATION\b", gst[:500])
                       and re.search(r"(?im)^\s*Account number\s*:", gst))
    looks_like_gst = (re.search(r"(?im)^\s*GST REGISTRATION\b", bank[:500])
                      and re.search(r"(?im)^\s*GSTIN\s*:", bank))
    return bool(looks_like_bank and looks_like_gst)
