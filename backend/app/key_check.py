"""API Key validation, placeholder detection, and cached status probing."""
from __future__ import annotations

import logging
import re
import time
import urllib.error
import urllib.request

log = logging.getLogger("scamcheck.keycheck")

# In-memory cache for key status results: key_fingerprint -> (status, timestamp)
_KEY_STATUS_CACHE: dict[str, tuple[str, float]] = {}
_CACHE_TTL_SECONDS = 600.0  # 10 minutes cache TTL

# Patterns that clearly identify dummy template placeholder keys
_PLACEHOLDER_PATTERNS = [
    re.compile(r"^your[-_]", re.I),
    re.compile(r"[-_]placeholder$", re.I),
    re.compile(r"[-_]here$", re.I),
    re.compile(r"^gsk_placeholder", re.I),
    re.compile(r"^sk[-_]placeholder", re.I),
    re.compile(r"^(replace|changeme|todo|example|dummy|none|xxxx)", re.I),
    re.compile(r"your[-_]groq", re.I),
    re.compile(r"your[-_]gemini", re.I),
    re.compile(r"your[-_]openrouter", re.I),
    re.compile(r"your[-_]anthropic", re.I),
    re.compile(r"your[-_]key", re.I),
]


def is_placeholder(key: str | None) -> bool:
    """Returns True if the key is empty, too short, or matches known placeholder templates."""
    if not key or not isinstance(key, str):
        return True
    k = key.strip()
    if not k or len(k) < 8:
        return True
    return any(pat.search(k) for pat in _PLACEHOLDER_PATTERNS)


def probe_key_status(provider: str, key: str | None, timeout: float = 3.0) -> str:
    """Probe an API key once and cache the result.
    Returns: 'unset' | 'placeholder' | 'valid' | 'invalid' | 'unverified'
    """
    if not key or not key.strip():
        return "unset"
    
    k = key.strip()
    if is_placeholder(k):
        return "placeholder"

    cache_key = f"{provider}:{k[:6]}...{k[-4:]}"
    now = time.time()
    if cache_key in _KEY_STATUS_CACHE:
        cached_status, cached_time = _KEY_STATUS_CACHE[cache_key]
        if now - cached_time < _CACHE_TTL_SECONDS:
            return cached_status

    status = "unverified"
    try:
        if provider == "groq":
            req = urllib.request.Request(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {k}", "User-Agent": "OfferCheck/1.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    status = "valid"
        elif provider == "openrouter":
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/auth/key",
                headers={"Authorization": f"Bearer {k}", "User-Agent": "OfferCheck/1.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    status = "valid"
        elif provider == "gemini":
            req = urllib.request.Request(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={k}",
                headers={"User-Agent": "OfferCheck/1.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    status = "valid"
        elif provider == "anthropic":
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/models",
                headers={"x-api-key": k, "anthropic-version": "2023-06-01", "User-Agent": "OfferCheck/1.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status in (200, 400):  # 400 with valid auth is still authenticated
                    status = "valid"
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            status = "invalid"
        elif e.code == 400:
            # Check body for invalid key message
            try:
                body = e.read().decode(errors="replace").lower()
                if "api key" in body or "invalid" in body or "unauthorized" in body:
                    status = "invalid"
                else:
                    status = "unverified"
            except Exception:
                status = "unverified"
        else:
            status = "unverified"
    except Exception as e:
        # Network unreachable / timeout -> keep as unverified so offline/local environments don't disable valid keys
        log.debug("Key probe for %s network error: %s", provider, e)
        status = "unverified"

    _KEY_STATUS_CACHE[cache_key] = (status, now)
    return status
