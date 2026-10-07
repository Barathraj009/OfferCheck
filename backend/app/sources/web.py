"""Domain registration (RDAP -> DNS fallback) and website-safety (Google Safe Browsing ->
OpenPhish feed) adapters, both layered for zero-cost operation. We never fetch the suspect
page itself - only public records about its address. 'No match in a feed' is never reported
as 'safe'; it means exactly what it says."""
from __future__ import annotations
import asyncio
import socket
from datetime import datetime, timezone
from urllib.parse import urlsplit
from .common import SourceError, cached, request_json, request_text, result
from ..validators import registrable_domain


async def _rdap(dom: str, s) -> dict:
    try:
        d = await cached(f"rdap:{dom}", s.cache_ttl * 6, lambda: request_json("GET", f"https://rdap.org/domain/{dom}", timeout=s.http_timeout))
    except SourceError as e:
        if e.kind == "not_found":
            raise SourceError("No public RDAP record for this domain/TLD, so its age could not be determined.", "not_found")
        raise
    reg = next((ev.get("eventDate") for ev in d.get("events", []) if ev.get("eventAction") == "registration"), None)
    if not reg:
        raise SourceError("The registry did not publish a registration date.", "malformed")
    try:
        dt = datetime.fromisoformat(reg.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except ValueError:
        raise SourceError("The registration date was in an unreadable format.", "malformed")
    age = max(0, (datetime.now(timezone.utc) - dt).days)
    return result("domain", "RDAP (rdap.org)", "verified", f"Registered {age} days ago.",
                  data={"domain": dom, "registered": dt.date().isoformat(), "age_days": age, "provider": "RDAP"})


async def _dns(site: dict, s) -> dict:
    """Fallback when RDAP has no record: does the name resolve at all? This gives existence
    evidence only - never a registration date (which is left as unknown, not guessed)."""
    host = site["host"]

    def resolve():
        infos = socket.getaddrinfo(host, None)
        return sorted({i[4][0] for i in infos})

    try:
        ips = await asyncio.to_thread(resolve)
    except socket.gaierror:
        return result("domain", "DNS (system resolver)", "verified",
                      "The domain name does not resolve to any address (it may not exist, or DNS may be temporarily unavailable).",
                      data={"domain": site["domain"], "registered": None, "age_days": None, "resolves": False, "addresses": [], "provider": "DNS"})
    except Exception as e:  # noqa: BLE001 - unusual resolver failure, report as unavailable
        raise SourceError("The domain name could not be looked up right now.", "network")
    return result("domain", "DNS (system resolver)", "verified",
                  f"Domain resolves to {len(ips)} address(es). Registration date unavailable (RDAP had no record).",
                  data={"domain": site["domain"], "registered": None, "age_days": None, "resolves": True,
                        "addresses": ips[:6], "provider": "DNS"})


async def check_domain(site: dict, s) -> dict:
    """RDAP first (gives real age); DNS only as fallback evidence."""
    from .base import run_chain
    return await run_chain("domain", [("RDAP", lambda p, st: _rdap(p["domain"], st)),
                                      ("DNS", lambda p, st: _dns(p, st))], {"domain": site["domain"], "host": site["host"], "url": site["url"]}, s)


async def _safe_browsing(site: dict, s) -> dict:
    if not s.safe_browsing_api_key:
        raise SourceError("No GOOGLE_SAFE_BROWSING_API_KEY configured.", "no_key")
    body = {"client": {"clientId": "scamcheck", "clientVersion": "1.0"},
            "threatInfo": {"threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE", "POTENTIALLY_HARMFUL_APPLICATION"],
                           "platformTypes": ["ANY_PLATFORM"], "threatEntryTypes": ["URL"], "threatEntries": [{"url": site["url"]}]}}
    d = await cached(f"sb:{site['url']}", s.cache_ttl, lambda: request_json("POST", "https://safebrowsing.googleapis.com/v4/threatMatches:find", params={"key": s.safe_browsing_api_key}, json=body, timeout=s.http_timeout))
    threats = sorted({m.get("threatType", "UNKNOWN") for m in d.get("matches", [])})
    return result("webSafety", "Google Safe Browsing", "verified", "Flagged: " + ", ".join(threats) if threats else "No match in Safe Browsing lists.", data={"threats": threats, "provider": "Google Safe Browsing"})


async def _openphish(site: dict, s) -> dict:
    """Keyless fallback: the OpenPhish community feed of currently active phishing URLs."""

    async def feed():
        return await request_text("https://openphish.com/feed.txt", timeout=s.http_timeout)

    text = await cached("openphish:feed", 3600, feed)
    hosts, domains = set(), set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            h = urlsplit(line if "//" in line else "http://" + line).hostname
        except ValueError:
            continue
        if h:
            hosts.add(h.lower())
            domains.add(registrable_domain(h.lower()))
    hit = site["host"] in hosts or site["domain"] in domains or any(d.endswith("." + site["domain"]) for d in domains)
    threats = ["Listed in the OpenPhish active phishing feed"] if hit else []
    return result("webSafety", "OpenPhish (openphish.com)", "verified",
                  "Flagged: active phishing feed listing." if hit else f"No match in the OpenPhish active-phishing feed ({len(domains)} sites checked). This is not a safety guarantee.",
                  data={"threats": threats, "feed_sites": len(domains), "provider": "OpenPhish"})


async def check_web_safety(site: dict, s) -> dict:
    from .base import run_chain
    return await run_chain("webSafety", [("Google Safe Browsing", _safe_browsing), ("OpenPhish", _openphish)], site, s)
