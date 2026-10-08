"""faster-whisper transcription endpoint for OfferCheck."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import File, HTTPException, Request, UploadFile
from fastapi import APIRouter
from fastapi.responses import JSONResponse

api_whisper_router = APIRouter(prefix="/whisper", tags=["whisper"])

log = logging.getLogger("scamcheck")

# Module-level Whisper model (loaded once at startup)
_whisper_model: Any = None


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


def _transcribe_audio_file(file_path: str, language: str | None = None) -> str:
    """Transcribe a WAV audio file using faster-whisper.

    Returns the full combined text from all segments.
    """
    model = _get_whisper_model()
    if model is None:
        raise HTTPException(status_code=503, detail="faster-whisper is not available on this server.")

    try:
        segments, info = model.transcribe(file_path, language=language)
        # Combine all segments into full text
        text_parts = [segment.text.strip() for segment in segments if segment.text.strip()]
        full_text = " ".join(text_parts).strip()
        log.info(
            "faster-whisper transcription: %d chars, language=%s, %.1f%% confidence",
            len(full_text),
            info.language,
            info.language_probability * 100 if info.language_probability else 0.0,
        )
        return full_text
    except Exception as e:
        log.exception("faster-whisper transcription failed")
        raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)[:200]}")


@api_whisper_router.post("/api/whisper-transcribe")
async def whisper_transcribe(
    file: UploadFile = File(...),
    language: str | None = None,
):
    """Transcribe uploaded WAV audio using faster-whisper.

    Accepts WAV audio files. Returns the transcribed text.
    """
    # Validate file type
    if file.content_type not in ("audio/wav", "audio/x-wav", "audio/pcm", "audio/wave"):
        raise HTTPException(status_code=415, detail="Please upload a WAV audio file.")

    # Read and save the uploaded file temporarily
    MAX_AUDIO_BYTES = S.max_upload_bytes  # from config, default 5MB
    data = await file.read()
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail=f"Audio file too large (max {MAX_AUDIO_BYTES // 1_048_576}MB).")

    # Save temporarily for whisper
    try:
        tmp_path = Path("/tmp") / f"whisper_{os.urandom(8).hex()}.wav"
        with open(tmp_path, "wb") as f:
            f.write(data)

        # Transcribe
        text = _transcribe_audio_file(str(tmp_path), language=language)

        # Clean up temp file
        try:
            os.unlink(tmp_path)
        except OSError:
            pass

        if not text or not text.strip():
            raise HTTPException(status_code=422, detail="No speech detected in the audio file.")

        return {"text": text.strip()}

    except HTTPException:
        raise
    except Exception as e:
        log.exception("whisper transcribe endpoint error")
        # Clean up on error
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise HTTPException(status_code=500, detail=f"Transcription error: {str(e)[:200]}")