"""PDF text extraction service - uses PyMuPDF for text, PaddleOCR for image-based PDFs."""
import base64
import io
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import fitz  # PyMuPDF
from PyPDF2 import PdfReader
from config import get_settings

try:
    from groq import Groq
except ImportError:  # pragma: no cover - handled at runtime
    Groq = None  # type: ignore[assignment]

# Minimum text length to consider PDF as "text-based" (vs image/scanned)
MIN_TEXT_THRESHOLD = 50
logger = logging.getLogger(__name__)


def _get_groq_client():
    settings = get_settings()
    if Groq is None:
        raise RuntimeError("groq package not installed.")

    api_key = settings.groq_api_key or os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set.")
    return Groq(api_key=api_key)


def _get_text_percentage(doc: fitz.Document) -> float:
    """Calculate ratio of text area to total page area. Low ratio = image-based PDF."""
    total_page_area = 0.0
    total_text_area = 0.0
    for page in doc:
        total_page_area += abs(page.rect)
        for block in page.get_text("dict").get("blocks", []):
            if "lines" in block:
                for line in block["lines"]:
                    for span in line.get("spans", []):
                        bbox = span.get("bbox", [0, 0, 0, 0])
                        total_text_area += (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
    return total_text_area / total_page_area if total_page_area > 0 else 0.0


def _extract_text_pymupdf(pdf_bytes: bytes) -> str:
    """Extract text using PyMuPDF (fast for text-based PDFs)."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text_parts = []
    for page in doc:
        text_parts.append(page.get_text())
    doc.close()
    return "\n".join(text_parts).strip()


def _extract_text_ocr(pdf_bytes: bytes) -> str:
    """Extract text using PaddleOCR for image/scanned PDFs."""
    settings = get_settings()

    with tempfile.TemporaryDirectory(prefix="ocr_") as temp_dir:
        temp_path = Path(temp_dir)
        pdf_path = temp_path / "input.pdf"
        out_path = temp_path / "output.txt"
        pdf_path.write_bytes(pdf_bytes)

        env = os.environ.copy()
        cache_dir = (
            Path(settings.paddle_pdx_cache_home).expanduser().resolve()
            if getattr(settings, "paddle_pdx_cache_home", None)
            else (Path(__file__).resolve().parents[1] / ".cache" / "paddlex")
        )
        cache_dir.mkdir(parents=True, exist_ok=True)
        env.setdefault("PADDLE_PDX_CACHE_HOME", str(cache_dir))
        if getattr(settings, "paddle_pdx_disable_model_source_check", True):
            env.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

        command = [
            sys.executable,
            "-m",
            "services.paddle_ocr_worker",
            str(pdf_path),
            str(out_path),
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=str(Path(__file__).resolve().parents[1]),
                env=env,
                capture_output=True,
                text=True,
                timeout=max(int(getattr(settings, "ocr_timeout_seconds", 90)), 15),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("PaddleOCR timed out on this PDF in the deployed environment.") from exc

        if completed.returncode != 0:
            stderr = (completed.stderr or completed.stdout or "").strip()
            detail = stderr.splitlines()[-1] if stderr else f"exit code {completed.returncode}"
            raise RuntimeError(f"PaddleOCR failed: {detail}")

        return out_path.read_text(encoding="utf-8").strip()


def _extract_text_pypdf2(pdf_bytes: bytes) -> str:
    """Fallback: extract text using PyPDF2."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    text_parts = []
    for page in reader.pages:
        text_parts.append(page.extract_text() or "")
    return "\n".join(text_parts).strip()


def _extract_text_groq_vision(pdf_bytes: bytes) -> str:
    """Fallback OCR using a Groq vision model on rendered PDF page images."""
    settings = get_settings()
    client = _get_groq_client()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text_parts: list[str] = []
    dpi = max(int(getattr(settings, "groq_ocr_render_dpi", 120)), 72)
    max_pages = max(int(getattr(settings, "groq_ocr_max_pages", 4)), 1)

    try:
        for page_index, page in enumerate(doc):
            if page_index >= max_pages:
                break

            pix = page.get_pixmap(dpi=dpi)
            image_bytes = pix.tobytes("jpeg")
            image_b64 = base64.b64encode(image_bytes).decode("ascii")
            response = client.chat.completions.create(
                model=settings.groq_vision_model,
                temperature=0,
                max_tokens=1200,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are performing OCR on a PDF page image. "
                            "Extract only the visible text from the page. "
                            "Preserve useful line breaks. "
                            "Do not summarize, explain, or invent missing text."
                        ),
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"Extract the text from page {page_index + 1}."},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                            },
                        ],
                    },
                ],
            )
            if not response.choices:
                continue
            page_text = (response.choices[0].message.content or "").strip()
            if page_text:
                text_parts.append(page_text)
    finally:
        doc.close()

    return "\n\n".join(text_parts).strip()


def extract_text(pdf_bytes: bytes, filename: str) -> tuple[str, str]:
    """
    Extract text from PDF. Uses OCR for image-based PDFs, PyMuPDF/PyPDF2 for text-based.
    Returns (extracted_text, extraction_method).
    """
    # Try PyMuPDF text extraction first
    text_pymupdf = _extract_text_pymupdf(pdf_bytes)
    
    # If very little text extracted, likely image-based -> use OCR
    if len(text_pymupdf.strip()) < MIN_TEXT_THRESHOLD:
        try:
            text = _extract_text_ocr(pdf_bytes)
            method = "paddleocr"
        except Exception as ocr_error:
            logger.exception("PaddleOCR extraction failed for %s", filename)
            try:
                text = _extract_text_groq_vision(pdf_bytes)
                method = "groq-vision-ocr"
            except Exception as groq_error:
                logger.exception("Groq vision OCR fallback failed for %s", filename)
                text = _extract_text_pypdf2(pdf_bytes)
                method = (
                    f"pypdf2 (ocr failed: {type(ocr_error).__name__}; "
                    f"groq fallback failed: {type(groq_error).__name__})"
                )
    else:
        text = text_pymupdf
        method = "pymupdf"
    
    return text or "(No text could be extracted from this PDF)", method
