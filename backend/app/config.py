"""Settings read from environment variables (never hard-coded). Optional .env support."""
from __future__ import annotations
import os
from dataclasses import dataclass

try:  # optional convenience; app works without python-dotenv
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
    else:
        load_dotenv()
except Exception:  # pragma: no cover
    pass


def _e(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    default_mode: str
    gemini_api_key: str
    gemini_model: str
    anthropic_api_key: str
    anthropic_model: str
    coingecko_api_key: str
    etherscan_api_key: str
    safe_browsing_api_key: str
    llm_provider: str  # auto | gemini | ollama | anthropic | none
    ollama_base_url: str
    ollama_model: str  # empty = auto-pick from installed models
    llm_timeout: float
    http_timeout: float
    cache_ttl: int
    max_input_chars: int
    max_upload_bytes: int
    rate_limit_per_10min: int
    allowed_origins: list[str]
    supabase_url: str
    supabase_anon_key: str
    supabase_service_key: str

    def configured(self) -> dict[str, bool]:
        """Which live sources are usable. Everything except Etherscan/Google Safe Browsing
        works with no key at all (Sourcify, public RPC, GoPlus, DexScreener, RDAP, OpenPhish,
        CoinGecko, Binance, Frankfurter are keyless; the LLM works via Gemini / local Ollama)."""
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
            "gemini": bool(self.gemini_api_key),
            "supabase": bool(self.supabase_url and (self.supabase_anon_key or self.supabase_service_key)),
        }


def get_settings() -> Settings:
    mode = _e("APP_MODE", "demo").lower()
    provider_raw = _e("LLM_PROVIDER", "auto").lower()
    valid_providers = ("auto", "gemini", "ollama", "anthropic", "none")
    llm_provider = provider_raw if provider_raw in valid_providers else "auto"

    # Support various Supabase env variable names
    sub_url = _e("NEXT_PUBLIC_SUPABASE_URL") or _e("SUPABASE_URL")
    sub_anon = _e("NEXT_PUBLIC_SUPABASE_ANON_KEY") or _e("SUPABASE_ANON_KEY")
    sub_svc = _e("SUPABASE_SERVICE_ROLE_KEY") or _e("SUPABASE_SERVICE_KEY")

    return Settings(
        default_mode=mode if mode in ("demo", "live") else "demo",
        gemini_api_key=_e("GEMINI_API_KEY"),
        gemini_model=_e("GEMINI_MODEL", "gemini-2.5-flash"),
        anthropic_api_key=_e("ANTHROPIC_API_KEY"),
        anthropic_model=_e("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
        coingecko_api_key=_e("COINGECKO_API_KEY"),
        etherscan_api_key=_e("ETHERSCAN_API_KEY"),
        safe_browsing_api_key=_e("GOOGLE_SAFE_BROWSING_API_KEY"),
        llm_provider=llm_provider,
        ollama_base_url=_e("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/"),
        ollama_model=_e("OLLAMA_MODEL"),
        llm_timeout=float(_e("LLM_TIMEOUT_SECONDS", "120")),
        http_timeout=float(_e("HTTP_TIMEOUT_SECONDS", "8")),
        cache_ttl=int(_e("CACHE_TTL_SECONDS", "600")),
        max_input_chars=int(_e("MAX_INPUT_CHARS", "6000")),
        max_upload_bytes=int(_e("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))),
        rate_limit_per_10min=int(_e("RATE_LIMIT_PER_10MIN", "60")),
        allowed_origins=[o.strip() for o in _e("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()],
        supabase_url=sub_url,
        supabase_anon_key=sub_anon,
        supabase_service_key=sub_svc,
    )
