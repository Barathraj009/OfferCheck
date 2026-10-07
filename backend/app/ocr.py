"""Local screenshot OCR (Tesseract) with adaptive preprocessing.

Zero-cost rules: uses only the free local Tesseract binary - no cloud OCR, no
downloads. When the binary is missing the caller degrades honestly (503).

Preprocessing strategy (measured on good/noisy/tiny/rotated screenshots):
  * plain grayscale is the most reliable single pipeline - aggressive
    autocontrast or binarization actively *hurts* noisy images;
  * tiny clean text benefits from autocontrast + LANCZOS upscale;
  * upside-down/rotated phone photos need OSD orientation correction.
So we run the cheap pipeline first and only spend extra Tesseract passes when
the recognition confidence is low, choosing the variant with the highest
Tesseract word confidence.
"""
from __future__ import annotations

import io
import logging
import os
import shutil
from dataclasses import dataclass

from PIL import Image, ImageFilter, ImageOps

log = logging.getLogger("scamcheck.ocr")

# Stop early when recognition is already this confident (measured: good images >= 90,
# failed recognitions <= 50).
CONF_STOP = 85
UPSCALE_TARGET = 1200
UPSCALE_MAX = 3.0

# Known install locations when the binary is not on PATH (Windows installers often
# skip PATH in silent mode).
_TESSERACT_CANDIDATES = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)


class OcrUnavailable(RuntimeError):
    """Tesseract binary or its Python wrapper is missing."""


class OcrLanguageError(RuntimeError):
    """The requested OCR language pack is not installed on this machine."""


@dataclass
class OcrResult:
    text: str
    confidence: float  # mean Tesseract word confidence, 0-100
    variant: str       # which pipeline produced the text
    rotated: bool      # orientation correction was applied


def ensure_tesseract() -> str | None:
    """Locate the Tesseract binary and teach pytesseract where it is."""
    exe = shutil.which("tesseract")
    if not exe:
        for cand in _TESSERACT_CANDIDATES:
            if os.path.isfile(cand):
                exe = cand
                break
    if exe:
        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = exe
        except Exception:  # wrapper missing - caller turns this into OcrUnavailable
            return None
    return exe


def _upscale(g: Image.Image) -> Image.Image:
    """LANCZOS upscale of small images (phone screenshots) - only when it can help."""
    if g.width >= UPSCALE_TARGET:
        return g
    f = min(UPSCALE_MAX, UPSCALE_TARGET / max(1, g.width))
    return g.resize((max(1, int(g.width * f)), max(1, int(g.height * f))), Image.LANCZOS)


def _variant_raw(img: Image.Image) -> Image.Image:
    return img.convert("L")


def _variant_autocontrast(img: Image.Image) -> Image.Image:
    return _upscale(ImageOps.autocontrast(img.convert("L"), cutoff=2))


def _variant_denoise(img: Image.Image) -> Image.Image:
    g = _variant_autocontrast(img)
    return g.filter(ImageFilter.MedianFilter(3)).filter(ImageFilter.SHARPEN)


_VARIANTS = (
    ("autocontrast+upscale", _variant_autocontrast),
    ("denoise+sharpen", _variant_denoise),
)


def _pytesseract():
    try:
        import pytesseract
    except Exception as e:  # noqa: BLE001
        raise OcrUnavailable(f"pytesseract not importable: {type(e).__name__}") from e
    if not ensure_tesseract():
        raise OcrUnavailable("tesseract binary not found")
    return pytesseract


def _recognize(img: Image.Image, lang: str) -> tuple[str, float]:
    """One Tesseract pass -> (text, mean word confidence)."""
    pt = _pytesseract()
    try:
        text = pt.image_to_string(img, lang=lang)
    except pt.TesseractNotFoundError as e:
        raise OcrUnavailable("tesseract binary disappeared") from e
    except Exception as e:  # e.g. TesseractError for a language pack that is not installed
        msg = str(e).lower()
        if "language" in msg or "failed loading" in msg:
            raise OcrLanguageError(lang) from e
        raise
    text = text.strip()
    conf = 0.0
    if text:
        try:
            data = pt.image_to_data(img, lang=lang, output_type=pt.Output.DICT)
            scores = [int(c) for c, t in zip(data["conf"], data["text"]) if int(c) >= 0 and str(t).strip()]
            conf = sum(scores) / len(scores) if scores else 0.0
        except Exception:  # confidence is advisory only
            conf = 50.0
    return text, conf


def _detect_rotation(img: Image.Image) -> int:
    """Degrees to rotate so the text is upright (0 when unsure/unsupported)."""
    pt = _pytesseract()
    try:
        osd = pt.image_to_osd(img)
    except Exception:  # OSD data missing or detection failed - never fatal
        return 0
    for line in osd.splitlines():
        if line.startswith("Rotate"):
            try:
                return int(line.split(":")[1].strip()) % 360
            except (ValueError, IndexError):
                return 0
    return 0


def extract_text(img: Image.Image, lang: str = "eng", max_chars: int = 6000) -> OcrResult:
    """Recognize text in an image, spending extra passes only when needed."""
    _pytesseract()  # fail fast if unavailable
    gray = img.convert("L")

    text, conf = _recognize(gray, lang)
    best_text, best_conf, best_variant, rotated = text, conf, "raw", False

    if best_conf < CONF_STOP:
        deg = _detect_rotation(gray)
        if deg in (90, 180, 270):
            rtext, rconf = _recognize(gray.rotate(-deg, expand=True), lang)
            if rconf > best_conf:
                best_text, best_conf, best_variant, rotated = rtext, rconf, f"raw+rotate{deg}", True

    if best_conf < CONF_STOP:
        for name, fn in _VARIANTS:
            vtext, vconf = _recognize(fn(img), lang)
            if vconf > best_conf:
                best_text, best_conf, best_variant = vtext, vconf, name

    if len(best_text) > max_chars:
        best_text = best_text[:max_chars]
    log.info("ocr done variant=%s conf=%.1f rotated=%s chars=%d", best_variant, best_conf, rotated, len(best_text))
    return OcrResult(text=best_text, confidence=round(best_conf, 1), variant=best_variant, rotated=rotated)


def decode_image(data: bytes) -> Image.Image:
    """Decode upload bytes -> RGB image, raising ValueError on anything that is not
    a real, sane image. Dimensions are checked from the header *before* pixels are
    decoded, so a malicious huge image never gets fully loaded."""
    try:
        img = Image.open(io.BytesIO(data))  # header only
        if img.width * img.height > 25_000_000:
            raise ValueError("resolution too large")
        if img.width < 8 or img.height < 8:
            raise ValueError("image too small")
        img.verify()  # integrity pass (no full decode)
        img = Image.open(io.BytesIO(data))
        img.load()  # full decode - catches truncated/corrupt payloads
    except ValueError:
        raise
    except Exception as e:  # noqa: BLE001
        raise ValueError("not an image") from e
    # Phone cameras often store orientation only in EXIF - apply it so sideways
    # screenshots are upright before OCR sees them.
    from PIL import ImageOps
    transposed = ImageOps.exif_transpose(img)
    return (transposed or img).convert("RGB")
