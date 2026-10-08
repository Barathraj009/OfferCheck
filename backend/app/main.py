"""FastAPI service. Run from /backend:  uvicorn app.main:app --reload"""
from __future__ import annotations
import asyncio
import json
import logging
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import os  # added for .env reading
from typing import Literal
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import demo, store
from .analysis import run_analysis
from .config import get_settings
from .validators import CHAINS, ValidationFailure

# Whisper transcription router
from .whisper_routes import api_whisper_router

# Module-level settings instance (required by this module)
S = get_settings()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("scamcheck")

# --- Supabase configuration (optional, zero-cost mode if absent) ---
supabase_url = ''
supabase_anon_key = ''
supabase_service_key = ''

env_path = os.path.join(Path(__file__).resolve().parent.parent, '.env')
if os.path.exists(env_path):
    with open(env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line.startswith('NEXT_PUBLIC_SUPABASE_URL'):
                supabase_url = _line.split('=', 1)[1].strip() if '=' in _line else ''
            if _line.startswith('NEXT_PUBLIC_SUPABASE_ANON_KEY'):
                supabase_anon_key = _line.split('=', 1)[1].strip() if '=' in _line else ''
            if _line.startswith('SUPABASE_SERVICE_ROLE_KEY'):
                supabase_service_key = _line.split('=', 1)[1].strip() if '=' in _line else ''

try:
    from supabase import create_client, Client
    if supabase_url:
        supabase: Client | None = create_client(supabase_url, supabase_anon_key or supabase_service_key or '')
    else:
        supabase = None
except Exception:
    supabase = None

# --- Gemini configuration (optional, for offer understanding/explanation) ---
gemini_key = os.getenv('GEMINI_API_KEY')
gemini_enabled = False
gemini_model = None
if gemini_key:
    try:
        import google.generativeai as genai
        genai.configure(api_key=gemini_key)
        gemini_enabled = True
        gemini_model = genai.GenerativeModel('gemini-3.5-flash')
    except Exception:
        gemini_enabled = False
        gemini_model = None

log = logging.getLogger("scamcheck")
app = FastAPI(title="Crypto Offer Verification API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=S.allowed_origins, allow_methods=["GET", "POST", "DELETE"], allow_headers=["Content-Type"])

_hits: dict[str, list[float]] = defaultdict(list)


def _limited(request: Request, bucket: str = "") -> bool:
    ip = request.client.host if request.client else "?"
    if bucket:
        ip = f"{bucket}:{ip}"
    now = time.time()
    if len(_hits) > 1000:  # bound memory even if many distinct IPs appear
        for k in [k for k, v in _hits.items() if not v or now - v[-1] >= 600]:
            _hits.pop(k, None)
    _hits[ip] = [t for t in _hits[ip] if now - t < 600]
    if len(_hits[ip]) >= S.rate_limit_per_10min:
        return True
    _hits[ip].append(now)
    return False


def _err(status: int, field: str | None, message: str):
    return JSONResponse(status_code=status, content={"error": {"field": field, "message": message}})


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError):
    """Pydantic/body errors use the same {error:{field,message}} shape as everything else."""
    err = exc.errors()[0] if exc.errors() else {}
    loc = [str(x) for x in err.get("loc", []) if x not in ("body", "query", "path")]
    return _err(422, loc[0] if loc else None, err.get("msg") or "The submitted data is not valid.")


class AnalyzeIn(BaseModel):
    model_config = {"extra": "forbid"}  # unknown fields are a client bug, not silently dropped

    text: str = Field("", max_length=20000)
    url: str = Field("", max_length=2100)
    token_name: str = Field("", max_length=200)
    contract_address: str = Field("", max_length=200)
    chain: str = Field("", max_length=30)
    mode: Literal["demo", "live"] = "demo"
    demo_scenario: str | None = Field(None, max_length=40)
    language: str = Field("en", max_length=5)


@app.get("/api/health")
async def health():
    from .llm import ollama_status
    cfg = dict(S.configured())
    ollama = await ollama_status(S)
    # Report the LLM as usable only when something actually answers (local model or optional key).
    cfg["llm"] = bool(ollama.get("available") and ollama.get("model")) or bool(S.anthropic_api_key)
    # Zero-cost ready = every verification source runs with no paid key/token (LLM is optional
    # enrichment: the heuristic extractor and template summary work without any model).
    free = {k: v for k, v in cfg.items() if k not in ("etherscan", "safe_browsing", "llm")}
    return {"ok": True, "default_mode": S.default_mode, "sources": cfg, "chains": {k: v["label"] for k, v in CHAINS.items()},
            "max_input_chars": S.max_input_chars,
            "llm_provider": S.llm_provider, "llm": ollama, "zero_cost_ready": all(free.values())}


@app.get("/api/demo-scenarios")
def scenarios():
    return demo.list_scenarios()


@app.post("/api/analyze")
async def analyze(body: AnalyzeIn, request: Request):
    if body.mode == "live" and _limited(request):
        return _err(429, None, "Too many live analyses from this address. Please wait a few minutes.")
    try:
        return await run_analysis(body.model_dump(), S)
    except ValidationFailure as e:
        log.info("validation failed field=%s", e.field)
        return _err(422, e.field, e.message)
    except Exception:
        log.exception("analysis crashed")
        return _err(500, None, "Something went wrong while analysing this offer. No result was produced - please try again.")


@app.post("/api/ocr")
async def ocr(request: Request, file: UploadFile = File(...), lang: str = "eng"):
    if _limited(request):
        return _err(429, None, "Too many requests. Please wait a few minutes.")
    if file.content_type not in ("image/png", "image/jpeg", "image/webp"):
        return _err(415, "file", "Please upload a PNG, JPEG or WebP image.")
    if not re.fullmatch(r"[a-z]{3}(\+[a-z]{3}){0,2}", lang):
        return _err(422, "lang", "Invalid OCR language code.")
    data = await file.read(S.max_upload_bytes + 1)
    if len(data) > S.max_upload_bytes:
        return _err(413, "file", f"The image is larger than {S.max_upload_bytes // 1_048_576} MB.")
    try:
        from .ocr import OcrLanguageError, OcrUnavailable, decode_image, extract_text
    except ImportError as e:  # pragma: no cover - Pillow/pytesseract wrapper missing
        log.warning("ocr module unavailable: %s", e)
        return _err(503, None, "Text extraction (OCR) is not available on this server. Type the text instead.")
    try:
        img = decode_image(data)
    except ValueError as e:
        msg = str(e)
        if "resolution" in msg:
            return _err(413, "file", "The image resolution is too large.")
        if "too small" in msg:
            return _err(422, "file", "That image is too small to contain readable text.")
        return _err(422, "file", "This file could not be read as an image.")
    try:
        # Adaptive local OCR: grayscale first, extra passes + orientation fix only when
        # Tesseract's own confidence is low (see app/ocr.py). Runs in a worker thread.
        result = await asyncio.to_thread(extract_text, img, lang, S.max_input_chars)
    except OcrUnavailable:
        log.warning("ocr unavailable: tesseract missing")
        return _err(503, None, "Text extraction (OCR) is not available on this server. Install Tesseract (see README) or type the text instead.")
    except OcrLanguageError:
        return _err(422, "lang", "That text-recognition language is not installed on this server. English OCR is available - try lang=eng.")
    except Exception:
        log.exception("ocr crashed")
        return _err(500, None, "Reading that image failed. Please try another screenshot or type the text instead.")
    return {"text": result.text, "empty": not result.text,
            "confidence": result.confidence, "variant": result.variant, "rotated": result.rotated}


@app.post("/api/reports")
async def save_report(request: Request):
    """Persist a generated report (explicit user action; raw input text is never stored)."""
    if _limited(request, "report"):
        return _err(429, None, "Too many saves from this address. Please wait a few minutes.")
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > store.MAX_PAYLOAD_BYTES:
            return _err(413, None, "This report is too large to save.")
    if not body:
        return _err(422, None, "No report was submitted.")
    try:
        report = json.loads(body)
    except ValueError:
        return _err(422, None, "The submitted report is not valid JSON.")
    try:
        rid = store.save(report)
    except store.InvalidReport as e:
        return _err(422, None, f"This is not a complete report ({e}).")
    except Exception:
        log.exception("saving report failed")
        return _err(500, None, "The report could not be saved. Please try again.")
    return {"id": rid, "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}


@app.get("/api/reports")
async def list_reports():
    return {"reports": store.list_reports()}


@app.get("/api/reports/{rid}")
async def get_report(rid: str):
    report = store.get(rid)
    if report is None:
        return _err(404, "id", "No saved report with that id. It may have been deleted or pruned.")
    return report


@app.delete("/api/reports/{rid}")
async def delete_report(rid: str):
    if not store.delete(rid):
        return _err(404, "id", "No saved report with that id.")
    return {"deleted": True}


_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.is_dir():  # optional single-server deployment after `npm run build`
    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")

# Include whisper routes
app.include_router(api_whisper_router, prefix="/api", tags=["whisper"])
