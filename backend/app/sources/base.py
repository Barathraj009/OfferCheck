"""Provider-chain plumbing (Item: zero-cost fallbacks).

A check is a chain of independent providers: Primary -> Secondary -> Tertiary -> unavailable.
Each provider is an async callable `(payload, settings) -> dict` (the standard `result()` shape)
that raises SourceError when it cannot answer. The chain stops at the first provider that
returns an answer (verified / not_found / not_applicable); failures are remembered so the
final "unavailable" reason can say what was actually tried. One broken provider never
crashes an analysis — at worst the check becomes `unavailable`, which lowers confidence.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Awaitable, Callable

from .common import SourceError

log = logging.getLogger("scamcheck")

# When every provider failed, prefer the most informative failure for the user.
KIND_PRIORITY = {"no_key": 0, "auth": 1, "rate_limited": 2, "circuit_open": 3, "timeout": 4,
                 "network": 5, "malformed": 6, "http": 7, "not_found": 8, "error": 9}


async def run_chain(chain_id: str, providers: list[tuple[str, Callable[[dict, object], Awaitable[dict]]]],
                    payload: dict, settings, per_provider_timeout: float | None = None,
                    stop_on: Callable[[dict], bool] | None = None) -> dict:
    """Try each provider in order. Returns the first usable answer.

    stop_on: predicate deciding whether an answer is final. Default = any returned result stops
    the chain. Market data passes `lambda r: r["status"] == "verified"` so a definitive
    'not found' from one source can still be rescued by the next provider.
    Raises SourceError (kind of the most informative failure) when all providers fail."""
    failures: list[tuple[str, str, str]] = []  # (label, kind, reason)
    skipped: list[str] = []  # every provider tried but not used (hard failures + soft answers), in order
    answer: dict | None = None  # a soft (not final) answer, kept as last resort
    timeout = per_provider_timeout if per_provider_timeout is not None else settings.http_timeout + 4
    for label, fn in providers:
        try:
            out = await asyncio.wait_for(fn(payload, settings), timeout)
        except asyncio.TimeoutError:
            log.info("provider timeout chain=%s provider=%s", chain_id, label)
            failures.append((label, "timeout", "did not respond in time"))
            skipped.append(label)
            continue
        except SourceError as e:
            log.info("provider failed chain=%s provider=%s kind=%s", chain_id, label, e.kind)
            failures.append((label, e.kind, e.reason))
            skipped.append(label)
            continue
        except Exception:  # a broken provider must not kill the report
            log.exception("provider crashed chain=%s provider=%s", chain_id, label)
            failures.append((label, "error", "unexpected error"))
            skipped.append(label)
            continue
        if stop_on is None or stop_on(out):
            if skipped:  # degraded but answered - say which providers were tried first
                out = {**out, "data": {**(out.get("data") or {}), "fallback_from": skipped}}
            return out
        if answer is None:
            answer = out
        skipped.append(label)  # answered, but not final (stop_on said keep looking)
    if answer is not None:
        if skipped:
            answer = {**answer, "data": {**(answer.get("data") or {}), "fallback_from": skipped}}
        return answer
    if not failures:
        raise SourceError("No provider is configured for this check.", "no_key")
    kind = min((f[1] for f in failures), key=lambda k: KIND_PRIORITY.get(k, 9))
    reason = next(f[2] for f in failures if f[1] == kind)
    tried = ", ".join(f[0] for f in failures)
    raise SourceError(f"{reason} (tried: {tried})", kind)
