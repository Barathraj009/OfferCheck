"""Settings read from environment variables (never hard-coded). Optional .env support."""
from __future__ import annotations
import os
from dataclasses import dataclass

try:  # optional convenience; app works without python-dotenv
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # pragma: no cover
    pass


def _e(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    default_mode: str
    anthropic_api_key: str
    anthropic_model: str
    coingecko_api_key: str
    etherscan_api_key: str
    safe_browsing_api_key: str
    llm_provider: str  # auto | ollama | anthropic | none
    ollama_base_url: str
    ollama_model: str  # empty = auto-pick from installed models
    llm_timeout: float
    http_timeout: float
    cache_ttl: int
    max_input_chars: int
    max_upload_bytes: int
    rate_limit_per_10min: int
    allowed_origins: list[str]

    def configured(self) -> dict[str, bool]:
        """Which live sources are usable. Everything except Etherscan/Google Safe Browsing
        works with no key at all (Sourcify, public RPC, GoPlus, DexScreener, RDAP, OpenPhish,
        CoinGecko, Binance, Frankfurter are keyless; the LLM works locally via Ollama)."""
        return {
            "coingecko": True,
            "goplus": True,
            "dexscreener": True,
            "rdap": True,
            "sourcify": True,
            "rpc": True,
            "openphish": True,
            "etherscan": bool(self.etherscan_api_key),
            "safe_browsing": bool(self.safe_browsing_api_key),
            "llm": self.llm_provider != "none",
        }


def get_settings() -> Settings:
    mode = _e("APP_MODE", "demo").lower()
    return Settings(
        default_mode=mode if mode in ("demo", "live") else "demo",
        anthropic_api_key=_e("ANTHROPIC_API_KEY"),
        anthropic_model=_e("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
        coingecko_api_key=_e("COINGECKO_API_KEY"),
        etherscan_api_key=_e("ETHERSCAN_API_KEY"),
        safe_browsing_api_key=_e("GOOGLE_SAFE_BROWSING_API_KEY"),
        llm_provider=_e("LLM_PROVIDER", "auto").lower() if _e("LLM_PROVIDER", "auto").lower() in ("auto", "ollama", "anthropic", "none") else "auto",
        ollama_base_url=_e("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
        ollama_model=_e("OLLAMA_MODEL"),
        llm_timeout=float(_e("LLM_TIMEOUT_SECONDS", "120")),
        http_timeout=float(_e("HTTP_TIMEOUT_SECONDS", "8")),
        cache_ttl=int(_e("CACHE_TTL_SECONDS", "600")),
        max_input_chars=int(_e("MAX_INPUT_CHARS", "6000")),
        max_upload_bytes=int(_e("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024))),
        rate_limit_per_10min=int(_e("RATE_LIMIT_PER_10MIN", "30")),
        allowed_origins=[o.strip() for o in _e("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()],
    )
