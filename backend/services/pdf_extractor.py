"""PDF text extraction service - uses PyMuPDF for text, PaddleOCR for image-based PDFs."""
import io
from functools import lru_cache
import os
from pathlib import Path
import fitz  # PyMuPDF
from PIL import Image, ImageOps
import numpy as np
from PyPDF2 import PdfReader
from config import get_settings

@lru_cache(maxsize=1)
def _get_paddle_ocr():
    """
    Lazily construct the PaddleOCR engine once.

    Note: model weights may be downloaded on first use.
    """
    settings = get_settings()
    # PaddleOCR (via PaddleX) writes cache/model files under ~/.paddlex by default.
    # In restricted environments that may be non-writable; use a project-local cache instead.
    cache_dir = (
        Path(settings.paddle_pdx_cache_home).expanduser().resolve()
        if getattr(settings, "paddle_pdx_cache_home", None)
        else (Path(__file__).resolve().parents[1] / ".cache" / "paddlex")
    )
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(cache_dir))
    if getattr(settings, "paddle_pdx_disable_model_source_check", True):
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

    # Import lazily so the API can still start up even if PaddleOCR isn't installed yet.
    from paddleocr import PaddleOCR  # type: ignore

    lang = (getattr(settings, "paddleocr_lang", None) or "en").strip() or "en"
    use_angle_cls = bool(getattr(settings, "paddleocr_use_angle_cls", True))
    # PaddleOCR v3 uses `use_textline_orientation` for angle correction.
    # Force CPU and disable HPI to avoid privileged sysctl calls in restricted environments.
    return PaddleOCR(
        lang=lang,
        use_textline_orientation=use_angle_cls,
        device="cpu",
        enable_hpi=False,
    )

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
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text_parts = []
    ocr = _get_paddle_ocr()
    for page in doc:
        # Balance accuracy vs speed for server-side OCR.
        pix = page.get_pixmap(dpi=200)
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        # Light pre-processing improves OCR on scanned PDFs.
        img = ImageOps.autocontrast(ImageOps.grayscale(img)).convert("RGB")

        # PaddleOCR expects a numpy image; use BGR channel order.
        np_img = np.asarray(img)[:, :, ::-1]
        result = ocr.predict(np_img)

        lines: list[str] = []
        # PaddleOCR v3 returns a list of dicts; recognized strings are in `rec_texts`.
        if isinstance(result, list):
            for item in result:
                if not isinstance(item, dict):
                    continue
                texts = item.get("rec_texts") or []
                scores = item.get("rec_scores") or []
                for i, text in enumerate(texts):
                    if not text or not str(text).strip():
                        continue
                    score = scores[i] if i < len(scores) else None
                    if score is None or score >= 0.3:
                        lines.append(str(text).strip())

        page_text = "\n".join(lines)
        text_parts.append(page_text)
    doc.close()
    return "\n".join(text_parts).strip()


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
