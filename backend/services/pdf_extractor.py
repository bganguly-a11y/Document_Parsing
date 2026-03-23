"""PDF text extraction service - uses PyMuPDF for text, PaddleOCR for image-based PDFs."""
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import fitz  # PyMuPDF
from PyPDF2 import PdfReader
from config import get_settings

# Minimum text length to consider PDF as "text-based" (vs image/scanned)
MIN_TEXT_THRESHOLD = 50


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
        except Exception as e:
            # Fallback to PyPDF2 if OCR fails
            text = _extract_text_pypdf2(pdf_bytes)
            # Keep the failure visible to help diagnose missing models/deps.
            method = f"pypdf2 (ocr failed: {type(e).__name__})"
    else:
        text = text_pymupdf
        method = "pymupdf"
    
    return text or "(No text could be extracted from this PDF)", method
