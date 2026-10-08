"""Shared plumbing for external sources: TTL cache, in-flight de-duplication,
uniform error type, JSON fetch helper, and the standard verification-result shape."""
from __future__ import annotations
import asyncio
import json as json_lib
import logging
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

log = logging.getLogger("scamcheck")


class SourceError(Exception):
    """A source could not give a usable answer. `kind` drives how we describe it to the user."""
    def __init__(self, reason: str, kind: str = "error"):
        super().__init__(reason)
        self.reason, self.kind = reason, kind


class TTLCache:
    def __init__(self, max_items: int = 500):
        self._d: dict[str, tuple[float, Any]] = {}
        self._max = max_items

    def get(self, key: str):
        hit = self._d.get(key)
        if not hit:
            return None
        if hit[0] < time.time():
            self._d.pop(key, None)
            return None
        return hit[1]

    def set(self, key: str, value: Any, ttl: int):
        if len(self._d) >= self._max:
            self._d.pop(next(iter(self._d)), None)
        self._d[key] = (time.time() + ttl, value)


_cache = TTLCache()
_inflight: dict[str, asyncio.Future] = {}

# Circuit breaker: after N consecutive failures per host, fail fast for a cooldown instead of
# hammering a free service that is down or rate-limiting us. Success resets it.
_CB_FAILS = 3
_CB_COOLDOWN = 60.0
_cb: dict[str, dict] = {}  # host -> {"fails": int, "open_until": float}


# Hardening limits for every outbound provider call:
#  * response bodies are streamed and capped (a broken/compromised provider cannot
#    exhaust memory);
#  * redirects are bounded;
#  * a hard total deadline (`timeout * 2 + 1`) catches slow-drip responses that
#    would otherwise reset the per-read timeout forever.
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_REDIRECTS = 5


def _host(url: str) -> str:
    return url.split("/")[2] if "//" in url else url


async def _request(method: str, url: str, *, params=None, headers=None, json=None, timeout: float = 8.0) -> tuple[int, bytes]:
    """Transport-level request with bounded redirects, a hard total deadline and a
    capped response body. Returns (status_code, body). Raises SourceError for every
    transport failure; status-code handling belongs to the callers."""
    import httpx  # lazy so the pure-logic modules/tests need no third-party packages
    host = _host(url)
    _cb_check(host)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, max_redirects=MAX_REDIRECTS) as client:
            async with asyncio.timeout(timeout * 2 + 1):
                async with client.stream(method, url, params=params, headers=headers, json=json) as r:
                    declared = r.headers.get("content-length", "")
                    if declared.isdigit() and int(declared) > MAX_RESPONSE_BYTES:
                        raise SourceError("The service returned a response larger than we accept.", "too_large")
                    chunks: list[bytes] = []
                    total = 0
                    async for chunk in r.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_RESPONSE_BYTES:
                            raise SourceError("The service returned a response larger than we accept.", "too_large")
                        chunks.append(chunk)
                    return r.status_code, b"".join(chunks)
    except SourceError:
        raise
    except (TimeoutError, httpx.TimeoutException) as exc:
        _cb_record(host, False)
        log.warning("Timeout on %s %s: %s", method, url, exc)
        raise SourceError(f"The service at {host} did not respond in time.", "timeout")
    except httpx.TooManyRedirects:
        _cb_record(host, False)
        log.warning("Too many redirects on %s %s", method, url)
        raise SourceError(f"The service at {host} sent too many redirects.", "network")
    except httpx.HTTPError as exc:
        _cb_record(host, False)
        log.warning("Network error on %s %s: %s", method, url, exc)
        raise SourceError(f"Could not connect to {host} ({type(exc).__name__}).", "network")


def _cb_check(host: str) -> None:
    st = _cb.get(host)
    if st and st["open_until"] > time.time():
        raise SourceError(f"This source ({host}) is being skipped for a moment after repeated failures. Try again shortly.", "circuit_open")


def _cb_record(host: str, ok: bool) -> None:
    st = _cb.setdefault(host, {"fails": 0, "open_until": 0.0})
    if ok:
        st["fails"], st["open_until"] = 0, 0.0
    else:
        st["fails"] += 1
        if st["fails"] >= _CB_FAILS:
            st["open_until"] = time.time() + _CB_COOLDOWN
            log.warning("circuit open host=%s for %.0fs", host, _CB_COOLDOWN)


async def cached(key: str, ttl: int, factory: Callable[[], Awaitable[Any]]):
    """Return a cached value, or run `factory` once even if called concurrently. Failures are not cached."""
    hit = _cache.get(key)
    if hit is not None:
        return hit
    if key in _inflight:
        return await _inflight[key]
    fut: asyncio.Future = asyncio.get_running_loop().create_future()
    _inflight[key] = fut
    try:
        val = await factory()
        _cache.set(key, val, ttl)
        fut.set_result(val)
        return val
    except BaseException as exc:
        fut.set_exception(exc)
        fut.exception()  # mark retrieved so asyncio doesn't warn when nobody else awaited
        raise
    finally:
        _inflight.pop(key, None)


async def request_json(method: str, url: str, *, params=None, headers=None, json=None, timeout: float = 8.0):
    """HTTP helper. Raises SourceError with a human-readable reason for every failure mode.
    Consults and updates the per-host circuit breaker."""
    host = _host(url)
    status, body = await _request(method, url, params=params, headers=headers, json=json, timeout=timeout)
    if status == 429:
        _cb_record(host, False)
        body_snip = body.decode("utf-8", errors="replace")[:200]
        log.warning("Rate limit on %s %s: HTTP 429 body=%s", method, url, body_snip)
        raise SourceError(f"Rate limit reached for {host} (HTTP 429).", "rate_limited")
    if status == 404:
        _cb_record(host, True)  # a definitive answer, not a failing host
        raise SourceError("Not found.", "not_found")
    if status in (401, 403):
        _cb_record(host, False)
        body_snip = body.decode("utf-8", errors="replace")[:200]
        log.warning("Auth error on %s %s: HTTP %s body=%s", method, url, status, body_snip)
        raise SourceError(f"The service at {host} rejected the request (HTTP {status}).", "auth")
    if status >= 400:
        _cb_record(host, False)
        body_snip = body.decode("utf-8", errors="replace")[:200]
        log.warning("HTTP %s on %s %s: body=%s", status, method, url, body_snip)
        raise SourceError(f"The service at {host} returned HTTP {status}.", "http")
    try:
        data = json_lib.loads(body)
    except ValueError:
        _cb_record(host, False)
        log.warning("malformed JSON from %s", url.split("?")[0])
        raise SourceError(f"The service at {host} returned a malformed response.", "malformed")
    _cb_record(host, True)
    return data


async def request_text(url: str, *, timeout: float = 8.0) -> str:
    """Plain-text GET (used for the OpenPhish feed). Same error semantics and circuit breaker."""
    host = _host(url)
    status, body = await _request("GET", url, timeout=timeout)
    if status == 429:
        _cb_record(host, False)
        raise SourceError("Rate limit reached for this free service. Try again later.", "rate_limited")
    if status >= 400:
        _cb_record(host, False)
        raise SourceError(f"The service returned HTTP {status}.", "http")
    _cb_record(host, True)
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return body.decode("utf-8", errors="replace")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def result(check_id: str, source: str, status: str, summary: str, *, data: dict | None = None,
           reason: str | None = None, demo: bool = False) -> dict:
    """Standard verification result.
    status: verified | not_found | unavailable | not_applicable
    `not_found` = the source answered and has no record (NOT proof of a scam)."""
    return {"check_id": check_id, "source": source, "status": status, "summary": summary,
            "data": data or {}, "reason": reason, "timestamp": now_iso(), "demo": demo}
