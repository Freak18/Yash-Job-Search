import io
import logging
import re

from pypdf import PdfReader

from config import OPENROUTER_MODEL
from scorer import get_client

logger = logging.getLogger(__name__)

MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_PAGES = 15
MAX_INPUT_CHARS = 30000


class ResumeParseError(Exception):
    pass


def extract_pdf_text(data: bytes) -> str:
    if not data.startswith(b"%PDF"):
        raise ResumeParseError("File is not a valid PDF.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ResumeParseError("PDF is password protected.")
        pages = [(page.extract_text() or "") for page in reader.pages[:MAX_PAGES]]
    except ResumeParseError:
        raise
    except Exception as exc:
        raise ResumeParseError(f"Could not read PDF: {exc}") from exc

    text = "\n".join(pages)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise ResumeParseError("No text found in PDF (scanned/image-only PDFs are not supported).")
    return text


def _build_compact_prompt(raw_text: str) -> str:
    return f"""
Rewrite the raw resume text below as a compact plain-text resume used to match against job descriptions.

Rules:
- Keep every factual detail that matters for matching: total years of experience, job titles, employers, dates, technologies/skills, domains, key achievements with numbers, education, certifications.
- Remove noise: page numbers, headers/footers, contact details (phone, email, address, links), decorative symbols, duplicated lines, filler words.
- Do NOT invent, infer or add anything that is not in the text.
- Plain text only, no markdown, no commentary. Use short section headings (SUMMARY, SKILLS, EXPERIENCE, EDUCATION, CERTIFICATIONS) and compact bullet lines starting with "- ".
- Target length: roughly 300-600 words.

RAW RESUME TEXT:
{raw_text[:MAX_INPUT_CHARS]}
""".strip()


def compact_resume(raw_text: str) -> str:
    response = get_client().chat.completions.create(
        model=OPENROUTER_MODEL,
        messages=[{"role": "user", "content": _build_compact_prompt(raw_text)}],
        temperature=0.1,
        max_tokens=3000,
    )
    content = (response.choices[0].message.content or "").strip()
    content = re.sub(r"^```(?:text|markdown)?\s*|\s*```$", "", content).strip()
    if not content:
        raise ResumeParseError("AI returned an empty response.")
    return content


def parse_resume_pdf(data: bytes) -> dict:
    """Extract text from a PDF and compact it with the LLM; falls back to raw text if the AI call fails."""
    if len(data) > MAX_PDF_BYTES:
        raise ResumeParseError("PDF is larger than 5 MB.")

    raw_text = extract_pdf_text(data)
    try:
        return {"content": compact_resume(raw_text), "compacted": True, "warning": ""}
    except Exception as exc:
        logger.warning("Resume compaction failed: %s", exc)
        return {
            "content": raw_text,
            "compacted": False,
            "warning": f"AI compaction failed ({exc}); showing raw extracted text.",
        }
