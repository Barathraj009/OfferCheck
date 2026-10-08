"""Server-side upload validation and media signature verification."""
from __future__ import annotations

import PIL.Image

# Harden Pillow against decompression bomb attacks (DoS via massive dimension images)
PIL.Image.MAX_IMAGE_PIXELS = 10_000_000


def detect_media_magic(data: bytes) -> str | None:
    """Detect MIME type strictly from binary magic byte signatures.
    Returns standard MIME string or None if unrecognised.
    """
    if not data or len(data) < 4:
        return None

    # --- Image & PDF formats ---
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"BM"):
        return "image/bmp"
    if data.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if data.startswith(b"%PDF-"):
        return "application/pdf"

    # --- Audio formats ---
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "audio/wav"
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        # EBML header (WebM and Matroska containers)
        return "audio/webm"
    if data.startswith(b"OggS"):
        return "audio/ogg"
    if data.startswith(b"ID3") or (len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return "audio/mpeg"
    if data.startswith(b"fLaC"):
        return "audio/flac"
    if len(data) >= 8 and data[4:8] in (b"ftyp", b"moov", b"wide", b"mdat"):
        return "audio/mp4"

    return None
