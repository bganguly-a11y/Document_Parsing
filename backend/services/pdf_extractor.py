"""PDF text extraction service - uses PyMuPDF for text, pytesseract for image-based PDFs."""
import io
import fitz  # PyMuPDF
import pytesseract
from PIL import Image
from PyPDF2 import PdfReader
from config import get_settings

# Set Tesseract path if configured
settings = get_settings()
if settings.tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

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
    """Extract text using pytesseract for image/scanned PDFs."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text_parts = []
    for page in doc:
        pix = page.get_pixmap(dpi=150)
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        page_text = pytesseract.image_to_string(img, lang="eng")
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
            method = "pytesseract"
        except Exception:
            # Fallback to PyPDF2 if OCR fails
            text = _extract_text_pypdf2(pdf_bytes)
            method = "pypdf2"
    else:
        text = text_pymupdf
        method = "pymupdf"
    
    return text or "(No text could be extracted from this PDF)", method
