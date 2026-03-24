"""Subprocess worker for PaddleOCR extraction from scanned PDFs."""

from __future__ import annotations

import io
import logging
import os
import sys
from pathlib import Path

import fitz
import numpy as np
from PIL import Image, ImageOps

from config import get_settings

logger = logging.getLogger(__name__)


def _read_field(item, field_name: str):
    if isinstance(item, dict):
        return item.get(field_name)
    return getattr(item, field_name, None)


def _extract_lines_from_result(result) -> list[str]:
    lines: list[str] = []
    if not isinstance(result, list):
        return lines

    for item in result:
        texts = _read_field(item, "rec_texts") or []
        scores = _read_field(item, "rec_scores") or []

        if texts:
            for i, text in enumerate(texts):
                if not text or not str(text).strip():
                    continue
                score = scores[i] if i < len(scores) else None
                if score is None or float(score) >= 0.3:
                    lines.append(str(text).strip())
            continue

        # Some PaddleOCR builds return nested structures from `ocr(...)`.
        if isinstance(item, list):
            for entry in item:
                if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                    continue
                text_info = entry[1]
                if not isinstance(text_info, (list, tuple)) or not text_info:
                    continue
                text = text_info[0]
                score = text_info[1] if len(text_info) > 1 else None
                if text and str(text).strip() and (score is None or float(score) >= 0.3):
                    lines.append(str(text).strip())

    return lines


def _get_paddle_ocr():
    settings = get_settings()
    cache_dir = (
        Path(settings.paddle_pdx_cache_home).expanduser().resolve()
        if getattr(settings, "paddle_pdx_cache_home", None)
        else (Path(__file__).resolve().parents[1] / ".cache" / "paddlex")
    )
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(cache_dir))
    if getattr(settings, "paddle_pdx_disable_model_source_check", True):
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

    from paddleocr import PaddleOCR  # type: ignore

    lang = (getattr(settings, "paddleocr_lang", None) or "en").strip() or "en"
    use_angle_cls = bool(getattr(settings, "paddleocr_use_angle_cls", True))
    return PaddleOCR(
        lang=lang,
        text_detection_model_name=getattr(settings, "paddleocr_text_detection_model_name", None),
        text_recognition_model_name=getattr(settings, "paddleocr_text_recognition_model_name", None),
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=use_angle_cls,
        device="cpu",
        enable_hpi=False,
    )


def _extract(pdf_path: Path, out_path: Path) -> None:
    settings = get_settings()
    dpi = max(int(getattr(settings, "ocr_render_dpi", 150)), 72)
    max_pages = max(int(getattr(settings, "ocr_max_pages", 8)), 1)

    doc = fitz.open(str(pdf_path))
    ocr = _get_paddle_ocr()
    text_parts: list[str] = []

    try:
        for page_index, page in enumerate(doc):
            if page_index >= max_pages:
                break

            pix = page.get_pixmap(dpi=dpi)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            img = ImageOps.autocontrast(ImageOps.grayscale(img)).convert("RGB")
            np_img = np.asarray(img)[:, :, ::-1]
            result = ocr.predict(np_img) if hasattr(ocr, "predict") else ocr.ocr(np_img)
            lines = _extract_lines_from_result(result)

            text_parts.append("\n".join(lines))
    finally:
        doc.close()

    out_path.write_text("\n".join(text_parts).strip(), encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: python -m services.paddle_ocr_worker <input.pdf> <output.txt>", file=sys.stderr)
        return 2

    pdf_path = Path(sys.argv[1]).resolve()
    out_path = Path(sys.argv[2]).resolve()
    try:
        _extract(pdf_path, out_path)
        return 0
    except Exception:
        logger.exception("PaddleOCR worker failed for %s", pdf_path.name)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
