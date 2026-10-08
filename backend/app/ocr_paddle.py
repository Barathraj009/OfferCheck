"""Unified OCR integration: PaddleOCR + Tesseract fallback.

Uses PaddleOCR for text extraction when available, otherwise falls back to
the existing Tesseract OCR. The extracted text is shown to the user for
editing before analysis, and the edited text becomes the actual analysis input.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

log = logging.getLogger("scamcheck.ocr")

# --- Tesseract (existing, proven zero-cost) ---
from .ocr import extract_text as tesseract_extract, OcrResult, OcrUnavailable, OcrLanguageError

# --- PaddleOCR integration ---
PADDLEOCR_AVAILABLE = False
_paddle_ocr = None

try:
    from paddleocr import PaddleOCR as _PaddleOCR
    PADDLEOCR_AVAILABLE = True
    log.info("PaddleOCR is available for text extraction")
except Exception as e:
    log.info(f"PaddleOCR not available: {type(e).__name__} - using Tesseract only")


def _init_paddle_ocr():
    """Initialize PaddleOCR instance (lazy, thread-safe-ish)."""
    global _paddle_ocr
    if _paddle_ocr is None and PADDLEOCR_AVAILABLE:
        try:
            _paddle_ocr = _PaddleOCR(use_textline_orientation=True, lang="en")
            log.info("PaddleOCR initialized successfully")
        except Exception as e:
            log.warning(f"PaddleOCR init failed: {e}")
            _paddle_ocr = None
    return _paddle_ocr


def extract_text_paddle(img) -> Optional[str]:
    """Extract text from an PIL Image using PaddleOCR.

    Returns the extracted text string, or None if extraction fails.
    """
    ocr = _init_paddle_ocr()
    if ocr is None:
        return None
    try:
        # PaddleOCR expects a numpy array or path; convert PIL image to numpy
        import numpy as np
        img_array = np.array(img.convert("RGB"))
        result = ocr.ocr(img_array, cls=True)
        # result is a list of [text, confidence] per line
        texts = []
        for line in result:
            if line and len(line) > 0:
                line_text = line[1] if isinstance(line, tuple) else str(line)
                if line_text:
                    texts.append(line_text)
        return " ".join(texts).strip() if texts else None
    except Exception as e:
        log.warning(f"PaddleOCR extraction failed: {e}")
        return None


def extract_text_composite(img) -> str:
    """Extract text using PaddleOCR first, then Tesseract as fallback.

    The composite approach ensures we always get *some* text extraction.
    PaddleOCR is preferred for quality; Tesseract is the zero-cost fallback.
    """
    # Try PaddleOCR first
    paddle_text = extract_text_paddle(img)
    if paddle_text and paddle_text.strip():
        log.info("PaddleOCR extraction succeeded (%d chars)", len(paddle_text))
        return paddle_text.strip()

    # Fall back to Tesseract
    try:
        t_result = tesseract_extract(img, lang="eng", max_chars=6000)
        log.info("Tesseract fallback extraction succeeded (%d chars)", len(t_result.text))
        return t_result.text
    except Exception as e:
        log.error(f"Both OCR engines failed: {e}")
        return ""


def ocr_with_user_edit(img, max_chars: int = 6000) -> str:
    """Full OCR workflow: extract text -> show to user -> edit -> return final text.

    This is the main entry point for the Check an Offer page. The flow is:
    1. Extract text from image using PaddleOCR (or Tesseract fallback)
    2. Present the extracted text to the user in an editable field
    3. User can edit/correct the text
    4. The edited text becomes the actual analysis input

    Returns the final text that will be used for analysis.
    """
    # Step 1: Extract text
    extracted = extract_text_composite(img)

    # Step 2: Present to user for editing
    # In a real UI, this would open an edit modal/dialog
    # For now, we return the extracted text; the UI layer handles editing
    # The edited text should be fed back into this function via the UI

    # For now, return extracted text (UI will handle the edit loop)
    # If the extracted text is too long, truncate
    if extracted and len(extracted) > max_chars:
        extracted = extracted[:max_chars]

    return extracted or ""


# Convenience: wrap a PIL image through the full workflow
def process_image_for_analysis(img) -> str:
    """Process an image through OCR and return the text for analysis.

    This is called by the backend API endpoint /api/ocr.
    The frontend should show the extracted text to the user for editing,
    then send the edited text as the 'text' field in the analysis request.
    """
    text = ocr_with_user_edit(img)
    # If no text extracted, return empty string (caller handles 422 validation)
    return text if text else ""