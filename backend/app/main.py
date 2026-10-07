"""FastAPI service. Run from /backend:  uvicorn app.main:app --reload"""
from __future__ import annotations
import asyncio
import io
import logging
import re
import time
from collections import defaultdict
from pathlib import Path
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from . import demo
from .analysis import run_analysis
from .config import get_settings
from .validators import CHAINS, ValidationFailure

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("scamcheck")
S = get_settings()
app = FastAPI(title="Crypto Offer Verification API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=S.allowed_origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

_hits: dict[str, list[float]] = defaultdict(list)


def _limited(request: Request) -> bool:
    ip = request.client.host if request.client else "?"
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
    text: str = Field("", max_length=20000)
    url: str = Field("", max_length=2100)
    token_name: str = Field("", max_length=200)
    contract_address: str = Field("", max_length=200)
    chain: str = Field("", max_length=30)
    mode: str = Field("demo", max_length=10)
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
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        img.verify()
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > 25_000_000:
            return _err(413, "file", "The image resolution is too large.")
        img = img.convert("RGB")
    except Exception:
        return _err(422, "file", "This file could not be read as an image.")
    try:
        from PIL import ImageOps
        # Preprocess for recognition on CPU-only Tesseract: grayscale + autocontrast for
        # screenshots with poor contrast, upscale small images (phones) so glyphs are readable.
        proc = ImageOps.autocontrast(img.convert("L"))
        if proc.width < 1200:  # never upscale large images: cost without benefit
            f = min(3.0, 1200 / max(1, proc.width))
            proc = proc.resize((max(1, int(proc.width * f)), max(1, int(proc.height * f))))
    except Exception:  # preprocessing is best-effort; raw image still works
        proc = img
    try:
        import pytesseract
        text = await asyncio.to_thread(pytesseract.image_to_string, proc, lang)
    except Exception as e:
        log.warning("ocr unavailable: %s", type(e).__name__)
        return _err(503, None, "Text extraction (OCR) is not available on this server. Install Tesseract (see README) or type the text instead.")
    text = text.strip()[: S.max_input_chars]
    return {"text": text, "empty": not text}


_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _dist.is_dir():  # optional single-server deployment after `npm run build`
    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")
