"""Unified OCR and Document Text Extraction: PaddleOCR + Tesseract + PDF.

Uses PaddleOCR / Tesseract for image extraction and pypdf for PDF document extraction.
Extracted text is returned to the user for editing before analysis, and the edited text
becomes the actual analysis input.
"""

from __future__ import annotations

import io
import logging
import os
import sys
import types
from typing import Optional

from PIL import Image

# Guard against decompression bomb vulnerabilities (e.g. huge images)
Image.MAX_IMAGE_PIXELS = 10_000_000

log = logging.getLogger("scamcheck.ocr")

from .ocr import (
    OcrLanguageError,
    OcrResult,
    OcrUnavailable,
    decode_image,
    extract_text as tesseract_extract,
)

PADDLEOCR_AVAILABLE = False
_paddle_ocr = None

# Safely check if PaddleOCR can be imported without torch DLL collision
try:
    if "sentence_transformers" not in sys.modules:
        sys.modules["sentence_transformers"] = types.ModuleType("sentence_transformers")
        sys.modules["sentence_transformers.backend"] = types.ModuleType("sentence_transformers.backend")
    if "modelscope" not in sys.modules:
        sys.modules["modelscope"] = types.ModuleType("modelscope")
    from paddleocr import PaddleOCR as _PaddleOCR
    PADDLEOCR_AVAILABLE = True
except Exception as e:
    log.info("PaddleOCR not available (%s) - using Tesseract & pypdf", type(e).__name__)
    PADDLEOCR_AVAILABLE = False


def _init_paddle_ocr():
    """Initialize PaddleOCR instance (lazy, safe)."""
    global _paddle_ocr
    if _paddle_ocr is None and PADDLEOCR_AVAILABLE:
        try:
            _paddle_ocr = _PaddleOCR(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                lang="en"
            )
            log.info("PaddleOCR initialized successfully")
        except Exception as e:
            log.warning("PaddleOCR init failed: %s", e)
            _paddle_ocr = None
    return _paddle_ocr


def extract_text_paddle(img: Image.Image) -> Optional[str]:
    """Extract text from a PIL Image using PaddleOCR."""
    ocr = _init_paddle_ocr()
    if ocr is None:
        return None
    try:
        import numpy as np
        img_array = np.array(img.convert("RGB"))
        res = list(ocr.predict(img_array))
        texts = []
        for r in res:
            if hasattr(r, "get"):
                rec_text = r.get("rec_text")
                if rec_text:
                    if isinstance(rec_text, list):
                        texts.extend([str(t) for t in rec_text if str(t).strip()])
                    else:
                        texts.append(str(rec_text).strip())
        return " ".join(texts).strip() if texts else None
    except Exception as e:
        log.warning("PaddleOCR inference failed: %s", e)
        return None


def extract_text_image(img: Image.Image, lang: str = "eng", max_chars: int = 6000) -> tuple[str, str, float]:
    """Extract text from an image. Returns (text, engine, confidence)."""
    # 1. Try PaddleOCR first
    paddle_text = extract_text_paddle(img)
    if paddle_text and len(paddle_text.strip()) > 5:
        return paddle_text.strip()[:max_chars], "paddleocr", 90.0

    # 2. Try Tesseract with adaptive preprocessing
    try:
        t_res = tesseract_extract(img, lang=lang, max_chars=max_chars)
        return t_res.text[:max_chars], f"tesseract ({t_res.variant})", t_res.confidence
    except (OcrUnavailable, OcrLanguageError):
        raise
    except Exception as e:
        log.warning("Tesseract failed: %s", e)
        if paddle_text:
            return paddle_text.strip()[:max_chars], "paddleocr", 80.0
        raise


def extract_pdf_text(data: bytes, lang: str = "eng", max_chars: int = 12000) -> str:
    """Extract text from a PDF file using pypdf, with image OCR fallback for scanned pages."""
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                log.warning("PDF is password protected and could not be decrypted.")
                return ""
        text_parts = []
        for page in reader.pages:
            t = page.extract_text() or ""
            if t.strip():
                text_parts.append(t.strip())
        extracted = "\n\n".join(text_parts).strip()
        if extracted:
            return extracted[:max_chars]

        # If digital text is empty (scanned PDF), try extracting embedded images
        ocr_parts = []
        for page in reader.pages:
            for img_obj in page.images:
                try:
                    img = Image.open(io.BytesIO(img_obj.data))
                    txt, _, _ = extract_text_image(img, lang=lang, max_chars=max_chars // 2)
                    if txt.strip():
                        ocr_parts.append(txt.strip())
                except Exception:
                    pass
        return "\n\n".join(ocr_parts).strip()[:max_chars]
    except Exception as e:
        log.warning("PDF extraction failed: %s", e)
        return ""


def extract_document_text(
    data: bytes,
    filename: str = "",
    content_type: str = "",
    lang: str = "eng",
    max_chars: int = 6000
) -> dict:
    """Universal document and image text extractor."""
    is_pdf = (
        content_type in ("application/pdf", "application/x-pdf")
        or filename.lower().endswith(".pdf")
        or data.startswith(b"%PDF-")
    )

    if is_pdf:
        text = extract_pdf_text(data, lang=lang, max_chars=max_chars)
        return {
            "text": text,
            "empty": not bool(text),
            "type": "pdf",
            "confidence": 95.0 if text else 0.0,
            "engine": "pypdf",
        }

    # Image processing
    img = decode_image(data)
    text, engine, conf = extract_text_image(img, lang=lang, max_chars=max_chars)
    return {
        "text": text,
        "empty": not bool(text),
        "type": "image",
        "confidence": conf,
        "engine": engine,
    }