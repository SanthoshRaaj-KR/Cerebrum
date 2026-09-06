"""Résumé PDF -> plain text, for the setup screen's résumé box to prefill itself.

That's the whole job now. The interview works from whatever text ends up in
that box (see context.CandidateContext) - there is no structured-profile
step any more, so this module is just the PDF extraction.
"""

from __future__ import annotations

import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError

# Resumes rarely run past a few hundred KB; this is a generous ceiling meant
# to reject something wrong (a video, a zip) rather than a real resume.
MAX_PDF_BYTES = 10 * 1024 * 1024


class ResumeParseError(Exception):
    """The PDF could not be read, or nothing usable came out of it."""


def extract_text(pdf_bytes: bytes) -> str:
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ResumeParseError(
            f"file too large ({len(pdf_bytes) // 1024} KB) - is this actually a resume?"
        )

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except PdfReadError as exc:
        raise ResumeParseError(f"not a readable PDF: {exc}") from exc

    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(pages).strip()
    if not text:
        raise ResumeParseError(
            "no extractable text found - this may be a scanned/image-only PDF"
        )
    return text
