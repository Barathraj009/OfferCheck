"""faster-whisper transcription endpoint for OfferCheck.
Hardened with per-IP rate limiting, magic bytes validation, and audio duration capping."""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from .config import get_settings
from .media_check import detect_media_magic
from .ratelimit import limiter

api_whisper_router = APIRouter(tags=["whisper"])

log = logging.getLogger("scamcheck.whisper")

# Module-level Whisper model (loaded once at startup)
_whisper_model: Any = None
MAX_AUDIO_DURATION_SECONDS = 120.0


def _get_whisper_model() -> Any:
    """Lazy-load the faster-whisper model once per process."""
    global _whisper_model
    if _whisper_model is None:
        try:
            import faster_whisper
            model_size = os.getenv("WHISPER_MODEL_SIZE", "tiny")
            compute_type = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
            log.info("Loading faster-whisper model: %s (%s)", model_size, compute_type)
            _whisper_model = faster_whisper.WhisperModel(
                model_size, device="cpu", compute_type=compute_type
            )
            log.info("faster-whisper model loaded successfully")
        except ImportError as e:
            log.warning(f"faster-whisper not available: {e}")
            _whisper_model = None
    return _whisper_model


def warm_whisper_model() -> Any:
    """Preload / warm up the faster-whisper model at startup."""
    try:
        return _get_whisper_model()
    except Exception as e:
        log.warning("faster-whisper warmup failed: %s", e)
        return None


def _transcribe_audio_file(file_path: str, language: str | None = None) -> tuple[str, str | None]:
    """Transcribe an audio file using faster-whisper.
    Returns (combined_text, detected_language).
    """
    model = _get_whisper_model()
    if model is None:
        raise HTTPException(
            status_code=503,
            detail="faster-whisper is not available on this server. Please check faster-whisper installation or type the offer text directly."
        )

    try:
        segments, info = model.transcribe(file_path, language=language if language else None)
        if info and info.duration and info.duration > MAX_AUDIO_DURATION_SECONDS:
            raise HTTPException(
                status_code=413,
                detail=f"Audio duration ({info.duration:.1f}s) exceeds the maximum allowed limit of {int(MAX_AUDIO_DURATION_SECONDS)} seconds."
            )
        text_parts = [segment.text.strip() for segment in segments if segment.text.strip()]
        full_text = " ".join(text_parts).strip()
        detected_lang = info.language if info else None
        log.info(
            "faster-whisper transcription: %d chars, language=%s, duration=%.1fs",
            len(full_text),
            detected_lang,
            info.duration if info else 0.0,
        )
        return full_text, detected_lang
    except HTTPException:
        raise
    except Exception as e:
        log.exception("faster-whisper transcription failed")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)[:200]}")


@api_whisper_router.get("/whisper/health")
async def whisper_health():
    model = _get_whisper_model()
    return {"available": model is not None, "engine": "faster-whisper", "model": os.getenv("WHISPER_MODEL_SIZE", "tiny")}


@api_whisper_router.post("/whisper-transcribe")
async def whisper_transcribe(
    request: Request,
    file: UploadFile = File(...),
    language: str | None = None,
):
    """Transcribe uploaded audio file using faster-whisper."""
    # Rate limit: 20 transcriptions per 10 minutes per IP
    limited, retry_after = limiter.is_limited(
        request, bucket="whisper", limit=20, window_seconds=600
    )
    if limited:
        return JSONResponse(
            status_code=429,
            content={"error": {"field": None, "message": "Too many transcription requests from this IP address. Please wait a few minutes."}},
            headers={"Retry-After": str(retry_after)}
        )

    s = get_settings()
    max_bytes = min(s.max_upload_bytes, 10 * 1024 * 1024)

    # Accept common audio formats
    allowed_types = (
        "audio/wav", "audio/x-wav", "audio/pcm", "audio/wave",
        "audio/webm", "audio/ogg", "audio/mp4", "audio/mpeg",
        "audio/mp3", "audio/aac", "audio/flac", "application/octet-stream"
    )
    if file.content_type and file.content_type not in allowed_types:
        ext = (file.filename or "").lower().split(".")[-1]
        if ext not in ("wav", "webm", "ogg", "mp3", "m4a", "aac", "flac", "mp4"):
            raise HTTPException(
                status_code=415,
                detail="Please upload a supported audio file (WAV, WebM, MP3, OGG, M4A)."
            )

    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Audio file is larger than {max_bytes // 1_048_576} MB."
        )
    if not data:
        raise HTTPException(status_code=422, detail="Empty audio file.")

    # Server-side binary magic bytes validation
    magic_mime = detect_media_magic(data)
    if not magic_mime or magic_mime not in (
        "audio/wav", "audio/webm", "audio/ogg", "audio/mpeg", "audio/flac", "audio/mp4"
    ):
        raise HTTPException(
            status_code=415,
            detail="Unsupported audio file format. File signature does not match audio formats."
        )

    ext = ".wav"
    if magic_mime == "audio/webm":
        ext = ".webm"
    elif magic_mime in ("audio/mpeg", "audio/mp3"):
        ext = ".mp3"
    elif magic_mime == "audio/ogg":
        ext = ".ogg"
    elif magic_mime == "audio/flac":
        ext = ".flac"
    elif file.filename and "." in file.filename:
        ext = "." + file.filename.rsplit(".", 1)[-1].lower()

    tmp_file = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    try:
        tmp_file.write(data)
        tmp_file.close()

        text, detected_lang = _transcribe_audio_file(tmp_file.name, language=language)

        return {
            "text": text,
            "empty": not bool(text),
            "language": detected_lang,
            "success": True,
        }
    finally:
        try:
            if os.path.exists(tmp_file.name):
                os.unlink(tmp_file.name)
        except OSError:
            pass