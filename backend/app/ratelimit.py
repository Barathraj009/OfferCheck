"""Thread-safe per-IP rate limiter with sliding window tracking."""
from __future__ import annotations

import ipaddress
import logging
import threading
import time
from collections import defaultdict
from fastapi import Request

log = logging.getLogger("scamcheck.ratelimit")


class IPRateLimiter:
    """In-memory sliding window rate limiter per IP and bucket."""

    def __init__(self, max_tracked_ips: int = 5000):
        self._lock = threading.Lock()
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._max_tracked = max_tracked_ips
        self._last_prune = time.time()

    def get_client_ip(self, request: Request) -> str:
        """Extract sanitized client IP address, handling proxy headers if valid."""
        # 1. Check X-Forwarded-For header if present
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            first_ip = forwarded.split(",")[0].strip()
            try:
                # Validate it parses as an IP address to avoid header injection
                ipaddress.ip_address(first_ip)
                return first_ip
            except ValueError:
                pass

        # 2. Check direct client host
        if request.client and request.client.host:
            return request.client.host

        return "unknown"

    def is_limited(
        self,
        request: Request,
        bucket: str = "default",
        limit: int = 60,
        window_seconds: int = 600,
    ) -> tuple[bool, int]:
        """Check if request exceeds rate limit.
        Returns (is_limited: bool, retry_after_seconds: int).
        """
        ip = self.get_client_ip(request)
        key = f"{bucket}:{ip}"
        now = time.time()

        with self._lock:
            # Periodic prune to bound memory
            if now - self._last_prune > 60 or len(self._hits) > self._max_tracked:
                cutoff = now - window_seconds
                keys_to_remove = [
                    k for k, timestamps in self._hits.items()
                    if not timestamps or timestamps[-1] < cutoff
                ]
                for k in keys_to_remove:
                    self._hits.pop(k, None)
                self._last_prune = now

            # Clean entries older than the window for this key
            cutoff = now - window_seconds
            self._hits[key] = [t for t in self._hits[key] if t >= cutoff]

            if len(self._hits[key]) >= limit:
                # Calculate retry after based on the oldest timestamp in window
                oldest = self._hits[key][0]
                retry_after = max(1, int(oldest + window_seconds - now))
                return True, retry_after

            self._hits[key].append(now)
            return False, 0


# Global rate limiter instance
limiter = IPRateLimiter()
