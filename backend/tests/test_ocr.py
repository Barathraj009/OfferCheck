"""Unit tests for the local OCR pipeline (app/ocr.py).

Real Tesseract runs (fast, local, no network). Tests that need the binary are
skipped on machines where it is absent - the endpoint still degrades to 503 there.
"""
from __future__ import annotations

import io
import unittest

from PIL import Image, ImageDraw, ImageFont

from app.ocr import (
    OcrUnavailable,
    decode_image,
    ensure_tesseract,
    extract_text,
)

HAVE_TESSERACT = bool(ensure_tesseract())

LINES = [
    "GUARANTEED 10x RETURN in 30 days!",
    "Bitcoin Flash Sale - 1 BTC only $30,000",
    "Refer 3 friends and earn $500 bonus",
    "Offer expires in 2 hours - act now!",
    "Contract: 0x123456789012345678901234567890123456789a",
    "https://bitcoingiveaway.example.com",
]


def _font(size: int):
    for path in (r"C:\Windows\Fonts\arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def text_image(lines=LINES, size=30, fg="black", bg="white", pad=40) -> Image.Image:
    font = _font(size)
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    w = max(probe.textlength(line, font=font) for line in lines) + 2 * pad
    img = Image.new("RGB", (int(w), pad * 2 + size * 2 * len(lines)), bg)
    d = ImageDraw.Draw(img)
    y = pad
    for line in lines:
        d.text((pad, y), line, fill=fg, font=font)
        y += int(size * 2)
    return img


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


class DecodeImageTests(unittest.TestCase):
    def test_accepts_valid_png_rgb(self):
        img = decode_image(png_bytes(Image.new("RGB", (50, 50), "white")))
        self.assertEqual(img.mode, "RGB")
        self.assertEqual(img.size, (50, 50))

    def test_rejects_garbage_bytes(self):
        with self.assertRaises(ValueError):
            decode_image(b"not an image at all \x00\x01\x02")

    def test_rejects_tiny_image(self):
        with self.assertRaises(ValueError) as ctx:
            decode_image(png_bytes(Image.new("RGB", (2, 2), "white")))
        self.assertIn("small", str(ctx.exception))

    def test_rejects_huge_resolution(self):
        # 5001 x 5001 = 25,005,001 pixels > 25M limit; small file (solid colour).
        big = Image.new("RGB", (5001, 5001), "white")
        with self.assertRaises(ValueError) as ctx:
            decode_image(png_bytes(big))
        self.assertIn("resolution", str(ctx.exception))


@unittest.skipUnless(HAVE_TESSERACT, "tesseract binary not installed")
class ExtractTextTests(unittest.TestCase):
    def test_good_image_extracts_all_key_facts(self):
        result = extract_text(text_image())
        low = result.text.lower()
        self.assertTrue(result.text.strip())
        self.assertGreater(result.confidence, 60)
        for needle in ("guaranteed", "10x", "bitcoin", "30,000", "0x123456789012345678901234567890123456789a",
                       "bitcoingiveaway.example.com"):
            self.assertIn(needle, low, f"missing {needle!r} in {result.text!r}")

    def test_blank_image_returns_empty_text(self):
        result = extract_text(Image.new("RGB", (400, 200), "white"))
        self.assertEqual(result.text, "")
        self.assertEqual(result.confidence, 0.0)

    def test_low_contrast_small_text_still_read(self):
        img = text_image(size=16, fg=(106, 106, 106), bg=(216, 216, 216), pad=20)
        result = extract_text(img)
        low = result.text.lower()
        self.assertTrue(any(k in low for k in ("guaranteed", "bitcoin", "refer", "expires")),
                        f"nothing usable extracted: {result.text!r}")

    def test_rotated_screenshot_text_recovered(self):
        # Sideways phone photo: Tesseract auto-orients; when it cannot, our OSD
        # fallback fixes it. Either way the user must get the text back.
        rotated = text_image().rotate(-90, expand=True, fillcolor="white")
        result = extract_text(rotated)
        self.assertIn("bitcoin", result.text.lower(), f"rotation not handled: {result}")

    def test_upside_down_screenshot_text_recovered(self):
        flipped = text_image().rotate(180, expand=True, fillcolor="white")
        result = extract_text(flipped)
        self.assertIn("guaranteed", result.text.lower(), f"180° not handled: {result}")

    def test_orientation_detector_sees_sideways_text(self):
        from app.ocr import _detect_rotation
        rotated = text_image().rotate(-90, expand=True, fillcolor="white").convert("L")
        self.assertIn(_detect_rotation(rotated), (90, 270))

    def test_max_chars_truncates(self):
        result = extract_text(text_image(), max_chars=25)
        self.assertLessEqual(len(result.text), 25)

    def test_missing_language_pack_gives_clear_error(self):
        # A pack like 'xxx' is not installed; the caller maps this to a friendly 422.
        from app.ocr import OcrLanguageError
        with self.assertRaises(OcrLanguageError):
            extract_text(text_image(), lang="xxx")


class UnavailableTests(unittest.TestCase):
    def test_missing_binary_raises_ocr_unavailable(self):
        from unittest import mock
        with mock.patch("app.ocr.ensure_tesseract", return_value=None):
            with self.assertRaises(OcrUnavailable):
                extract_text(Image.new("RGB", (50, 50), "white"))


if __name__ == "__main__":
    unittest.main()
