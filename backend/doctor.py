"""Environment doctor: does this machine have everything for a full zero-cost run?

Run from /backend:  python doctor.py [--probe]
  --probe   also makes one quick live request to each free source (needs internet)

Status meanings:
  READY    present and usable
  OPTIONAL missing but the app works without it (a free alternative covers it, or the
           feature is enhancement-only)
  MISSING  missing - the listed feature will be unavailable until it is installed/configured
Nothing is downloaded or installed by this script.
"""
from __future__ import annotations

import argparse
import importlib
import os
import shutil
import sys

try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(_env_path):
        load_dotenv(_env_path, override=True)
    else:
        load_dotenv(override=True)
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.key_check import is_placeholder, probe_key_status

R, O, M = "READY", "OPTIONAL", "MISSING"
rows: list[tuple[str, str, str]] = []


def add(name: str, status: str, detail: str) -> None:
    rows.append((name, status, detail))


def check_pkg(mod: str, name: str, required: bool, how: str = "pip install -r requirements.txt") -> bool:
    try:
        importlib.import_module(mod)
        add(name, R, "import ok")
        return True
    except Exception as e:  # noqa: BLE001
        add(name, O if not required else M, f"not importable ({type(e).__name__}); fix: {how}")
        return False


def check_key(var: str, name: str, provider: str, signup_url: str = "", why_optional: str = "") -> None:
    val = os.environ.get(var, "").strip()
    if not val:
        add(name, O, f"unset - {why_optional}")
        return

    if is_placeholder(val):
        msg = f"placeholder ('{val[:15]}...'); replace with real key"
        if signup_url:
            msg += f" from {signup_url}"
        add(name, O, msg)
        return

    st = probe_key_status(provider, val, timeout=3.0)
    if st == "valid":
        add(name, R, "valid (authenticated)")
    elif st == "invalid":
        msg = f"invalid API key (auth rejected)"
        if signup_url:
            msg += f"; get valid key at {signup_url}"
        add(name, M, msg)
    elif st == "placeholder":
        add(name, O, f"placeholder ('{val[:15]}...')")
    else:  # unverified
        add(name, R, "set (unverified / network unreachable)")


def probe(url: str, timeout: float = 5.0) -> tuple[bool, str]:
    try:
        import httpx
        r = httpx.get(url, timeout=timeout, follow_redirects=True)
        return r.status_code < 400, f"HTTP {r.status_code}"
    except Exception as e:  # noqa: BLE001
        return False, type(e).__name__


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true", help="also probe the free online sources")
    args = ap.parse_args()

    py_ok = sys.version_info >= (3, 11)
    add("Python >= 3.11", R if py_ok else M, f"{sys.version.split()[0]}")

    required = all([
        check_pkg("fastapi", "fastapi (web framework)", True),
        check_pkg("uvicorn", "uvicorn (server)", True),
        check_pkg("httpx", "httpx (HTTP client)", True),
        check_pkg("pydantic", "pydantic", True),
        check_pkg("PIL", "Pillow (image handling)", True),
    ])
    check_pkg("dotenv", "python-dotenv (optional .env loading)", False)
    check_pkg("pytesseract", "pytesseract (Python OCR wrapper)", False)

    # Tesseract binary (screenshot OCR) - PATH first, then the default Windows install dir
    binary = shutil.which("tesseract")
    if not binary:
        try:
            from app.ocr import ensure_tesseract  # type: ignore
            binary = ensure_tesseract()
        except Exception:  # noqa: BLE001
            binary = None
    if binary:
        add("Tesseract OCR binary", R, binary)
    else:
        add("Tesseract OCR binary", M, "screenshot text extraction unavailable; typing works. "
                                        "Windows: winget install -e --id UB-Mannheim.TesseractOCR")

    # Ollama (local LLM; optional - template summary works without it)
    base = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    daemon, detail = probe(base + "/api/tags", timeout=3.0)
    if not daemon:
        add("Ollama daemon", M, f"not reachable at {base}; local AI reading/explanation off "
                                "(start the Ollama app; app still works with rule-based extraction)")
    else:
        try:
            import httpx
            names = [m.get("name", "") for m in (httpx.get(base + "/api/tags", timeout=3.0).json().get("models") or [])]
        except Exception:  # noqa: BLE001
            names = []
        chat = [n for n in names if "embed" not in n.lower()]
        if chat:
            add("Ollama daemon", R, f"up; models: {', '.join(chat)}")
        else:
            add("Ollama daemon", R, "up, but no chat model installed")
            add("Local chat model", M, "run: ollama pull llama3.2:1b  (never auto-downloaded by this app)")

    check_key("GROQ_API_KEY", "Groq key (primary cloud AI)", "groq", signup_url="https://console.groq.com/keys", why_optional="local Ollama / heuristics used without it")
    check_key("OPENROUTER_API_KEY", "OpenRouter key (optional secondary cloud AI)", "openrouter", signup_url="https://openrouter.ai/keys", why_optional="local Ollama / heuristics used without it")
    check_key("GEMINI_API_KEY", "Gemini key (optional tertiary cloud AI)", "gemini", signup_url="https://aistudio.google.com/app/apikey", why_optional="local Ollama / heuristics used without it")
    check_key("ANTHROPIC_API_KEY", "Anthropic key (optional AI fallback)", "anthropic", signup_url="https://console.anthropic.com/", why_optional="local Ollama used instead")

    # Non-AI provider keys
    eth_key = os.environ.get("ETHERSCAN_API_KEY", "").strip()
    add("Etherscan key (optional extra verify layer)", R if eth_key and not is_placeholder(eth_key) else O,
        "set" if eth_key and not is_placeholder(eth_key) else "unset - Sourcify + public RPCs verify without it")

    sb_key = os.environ.get("GOOGLE_SAFE_BROWSING_API_KEY", "").strip()
    add("Safe Browsing key (optional)", R if sb_key and not is_placeholder(sb_key) else O,
        "set" if sb_key and not is_placeholder(sb_key) else "unset - the OpenPhish feed is used without it")

    cg_key = os.environ.get("COINGECKO_API_KEY", "").strip()
    add("CoinGecko key (optional, raises rate limits)", R if cg_key and not is_placeholder(cg_key) else O,
        "set" if cg_key and not is_placeholder(cg_key) else "unset - CoinGecko works keyless")

    if args.probe:
        for name, url in [
            ("Source: Sourcify (contract verify)", "https://sourcify.dev/server/v2/contract/1/0x0000000000000000000000000000000000000000"),
            ("Source: GoPlus (token security)", "https://api.gopluslabs.io/api/v1/is_honeypot?contract_addresses=0x0000000000000000000000000000000000000000"),
            ("Source: DexScreener (price/liquidity)", "https://api.dexscreener.com/token-pairs/v1/bsc/0x0000000000000000000000000000000000000000"),
            ("Source: CoinGecko (market data)", "https://api.coingecko.com/api/v3/ping"),
            ("Source: OpenPhish (phishing feed)", "https://openphish.com/feed.txt"),
            ("Source: Binance (major prices)", "https://api.binance.com/api/v3/ping"),
            ("Source: Frankfurter (FX rates)", "https://api.frankfurter.app/latest?from=USD&to=INR"),
            ("Source: 1rpc.io (public RPC)", "https://ethereum-rpc.1rpc.io/"),
        ]:
            ok, info = probe(url)
            add(name, R if ok else O, info + ("" if ok else " - unreachable now; the check reports unavailable and confidence drops"))

    w = max(len(n) for n, _, _ in rows)
    print("\nCrypto Offer Verifier - environment doctor\n" + "=" * 61)
    for n, st, d in rows:
        print(f"[{st:<7}] {n:<{w}}  {d}")
    print("=" * 61)
    print("Zero-cost operation: every verification check works with no API keys")
    print("(Sourcify, public RPCs, GoPlus, DexScreener, RDAP, OpenPhish, Binance, CoinGecko, Frankfurter).")
    print("MISSING items only disable their own optional feature - never the whole app.")
    return 0 if required and py_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
