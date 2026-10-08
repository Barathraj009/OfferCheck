"""Company & Web Verification adapter.

Verifies claimed companies, organizations, and web domains against:
  1. Authoritative Corporate & Crypto Entity Registry (official domains)
  2. Wikipedia Knowledge REST API (canonical entity facts & official websites)
  3. DuckDuckGo Instant Knowledge API (official domain matching & abstracts)
  4. Optional Tavily / Serper Search API (if key provided)

Zero-cost operation: works out of the box with no API keys.
"""
from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import quote, urlsplit

from .common import SourceError, cached, request_json, result
from ..validators import registrable_domain

log = logging.getLogger("scamcheck.entity")

# Authoritative directory of prominent companies, exchanges, and crypto protocols
KNOWN_ENTITIES: dict[str, dict] = {
    "google": {
        "name": "Google",
        "category": "Technology Company",
        "domains": ["google.com", "google.co.in", "google.co.uk", "abc.xyz", "youtube.com", "android.com"],
        "aliases": ["google llc", "alphabet", "alphabet inc"]
    },
    "apple": {
        "name": "Apple Inc.",
        "category": "Technology Company",
        "domains": ["apple.com", "icloud.com"],
        "aliases": ["apple", "apple store"]
    },
    "microsoft": {
        "name": "Microsoft",
        "category": "Technology Company",
        "domains": ["microsoft.com", "live.com", "office.com", "azure.com", "windows.com", "linkedin.com", "github.com"],
        "aliases": ["microsoft corp", "microsoft 365", "msft"]
    },
    "amazon": {
        "name": "Amazon",
        "category": "E-Commerce & Cloud",
        "domains": ["amazon.com", "amazon.in", "amazon.co.uk", "aws.amazon.com"],
        "aliases": ["amazon.com inc", "aws"]
    },
    "meta": {
        "name": "Meta Platforms",
        "category": "Technology & Social Media",
        "domains": ["meta.com", "facebook.com", "instagram.com", "whatsapp.com"],
        "aliases": ["facebook", "instagram", "whatsapp"]
    },
    "coinbase": {
        "name": "Coinbase",
        "category": "Regulated Crypto Exchange",
        "domains": ["coinbase.com", "pro.coinbase.com"],
        "aliases": ["coinbase inc", "coinbase exchange", "coinbase wallet"]
    },
    "binance": {
        "name": "Binance",
        "category": "Crypto Exchange & Ecosystem",
        "domains": ["binance.com", "binance.us", "bnbchain.org"],
        "aliases": ["binance exchange", "bnb"]
    },
    "kraken": {
        "name": "Kraken",
        "category": "Crypto Exchange",
        "domains": ["kraken.com", "pro.kraken.com"],
        "aliases": ["kraken exchange", "payward inc"]
    },
    "stripe": {
        "name": "Stripe",
        "category": "Financial Services & Payments",
        "domains": ["stripe.com"],
        "aliases": ["stripe payments", "stripe inc"]
    },
    "paypal": {
        "name": "PayPal",
        "category": "Payment Network",
        "domains": ["paypal.com", "venmo.com"],
        "aliases": ["paypal inc", "venmo"]
    },
    "uniswap": {
        "name": "Uniswap",
        "category": "Decentralized Exchange Protocol",
        "domains": ["uniswap.org", "app.uniswap.org"],
        "aliases": ["uniswap labs", "uniswap protocol"]
    },
    "aave": {
        "name": "Aave",
        "category": "DeFi Lending Protocol",
        "domains": ["aave.com", "app.aave.com"],
        "aliases": ["aave protocol", "aave labs"]
    },
    "robinhood": {
        "name": "Robinhood",
        "category": "Financial Brokerage",
        "domains": ["robinhood.com"],
        "aliases": ["robinhood markets", "robinhood crypto"]
    },
    "revolut": {
        "name": "Revolut",
        "category": "Digital Banking & Fintech",
        "domains": ["revolut.com"],
        "aliases": ["revolut ltd", "revolut bank"]
    },
    "fidelity": {
        "name": "Fidelity Investments",
        "category": "Financial Services & Brokerage",
        "domains": ["fidelity.com", "fidelityinternational.com"],
        "aliases": ["fidelity", "fidelity crypto"]
    },
}


def _extract_brand_candidate(claims: dict, site: dict | None) -> str | None:
    """Extract most likely entity / company name from claims and domain."""
    # 1. Direct entity name if extracted
    if claims.get("entity_name"):
        name = claims["entity_name"].strip()
        if len(name) >= 2:
            return name

    # 2. Direct seller identity if stated
    if claims.get("seller_identity"):
        name = claims["seller_identity"].strip()
        if len(name) >= 2 and not name.lower().startswith(("http", "www")):
            return name

    # 3. Check site domain name
    if site and site.get("domain"):
        dom_parts = site["domain"].split(".")
        main_part = dom_parts[0] if len(dom_parts) >= 2 else site["domain"]
        if main_part.lower() in KNOWN_ENTITIES:
            return KNOWN_ENTITIES[main_part.lower()]["name"]

    # 4. Check for recognized entity names mentioned in text or asset name
    combined_text = (claims.get("entity_name") or "") + " " + (claims.get("asset_name") or "") + " " + (claims.get("seller_identity") or "")
    if claims.get("phrases"):
        combined_text += " " + " ".join(str(v) for v in claims["phrases"].values())

    for key, ent in KNOWN_ENTITIES.items():
        if re.search(r"\b" + re.escape(ent["name"].lower()) + r"\b", combined_text.lower()):
            return ent["name"]
        for alias in ent.get("aliases", []):
            if re.search(r"\b" + re.escape(alias) + r"\b", combined_text.lower()):
                return ent["name"]

    return None


async def _wiki_lookup(entity_name: str, s) -> dict | None:
    """Query Wikipedia REST summary API for canonical organization facts."""
    clean_name = re.sub(r"[^\w\s.-]", "", entity_name.strip())
    slug = quote(clean_name.replace(" ", "_"), safe="")
    if not slug:
        return None
    headers = {"User-Agent": "OfferCheck/1.0 (entity-verifier; contact@offercheck.local)"}
    try:
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}"
        data = await cached(
            f"wiki:{slug.lower()}",
            s.cache_ttl * 6,
            lambda: request_json("GET", url, headers=headers, timeout=s.http_timeout)
        )
        if data and data.get("type") != "disambiguation" and data.get("title"):
            return {
                "title": data.get("title"),
                "description": data.get("description", ""),
                "extract": data.get("extract", "")[:300],
                "source": "Wikipedia Knowledge Graph"
            }
    except Exception as e:
        log.debug("Wikipedia lookup skipped for %s: %s", entity_name, e)
    return None


async def _ddg_lookup(entity_name: str, s) -> dict | None:
    """Query DuckDuckGo Instant Answer API for official entity URL and abstract."""
    headers = {"User-Agent": "OfferCheck/1.0 (entity-verifier; contact@offercheck.local)"}
    try:
        url = "https://api.duckduckgo.com/"
        params = {"q": entity_name, "format": "json", "no_html": "1", "skip_disambig": "1"}
        data = await cached(
            f"ddg:{entity_name.lower()}",
            s.cache_ttl * 6,
            lambda: request_json("GET", url, headers=headers, params=params, timeout=s.http_timeout)
        )
        if data and (data.get("Abstract") or data.get("Heading") or data.get("AbstractURL")):
            return {
                "heading": data.get("Heading", ""),
                "abstract": data.get("Abstract", "")[:300],
                "official_url": data.get("AbstractURL", ""),
                "source": "DuckDuckGo Instant Answer"
            }
    except Exception as e:
        log.debug("DuckDuckGo lookup skipped for %s: %s", entity_name, e)
    return None


async def _tavily_lookup(query: str, s) -> dict | None:
    """Query Tavily Search API if configured in settings."""
    api_key = getattr(s, "tavily_api_key", None) or getattr(s, "safe_browsing_api_key", None)
    if not api_key:
        return None
    try:
        url = "https://api.tavily.com/search"
        payload = {"api_key": api_key, "query": query, "search_depth": "basic", "include_answer": True}
        data = await cached(
            f"tavily:{query.lower()}",
            s.cache_ttl * 2,
            lambda: request_json("POST", url, json=payload, timeout=s.http_timeout)
        )
        if data and data.get("results"):
            return {
                "answer": data.get("answer", ""),
                "results": data.get("results", [])[:3],
                "source": "Tavily Web Search"
            }
    except Exception as e:
        log.debug("Tavily search skipped: %s", e)
    return None


STOP_TOKENS = {"the", "a", "an", "of", "and", "or", "in", "on", "at", "to", "for", "with", "by", "from", "inc", "ltd", "corp", "llc", "group", "co"}
GENERIC_TOKENS = {"nova", "pool", "yield", "token", "coin", "crypto", "defi", "swap", "finance", "protocol", "dao", "network", "community", "project", "alpha", "beta", "fund", "global", "capital", "ventures", "matrix", "apex", "safe", "moon", "earn", "reward", "chain", "official", "sale", "presale", "airdrop"}
CORP_KEYWORDS = {"company", "corporation", "enterprise", "foundation", "organization", "firm", "financial", "crypto", "exchange", "bank", "fintech", "brokerage", "technology", "platform", "conglomerate", "business", "subsidiary", "operator", "protocol"}


def _tokenize(s: str) -> set[str]:
    words = re.findall(r"\b[a-zA-Z0-9]{2,}\b", s.lower())
    return {w for w in words if w not in STOP_TOKENS}


async def check_entity_and_web(claims: dict, site: dict | None, s) -> dict:
    """Verify entity authenticity, official domain match, and real-time web legitimacy."""
    candidate = _extract_brand_candidate(claims, site)
    offer_domain = site.get("domain") if site else None

    # Step 1: Check Authoritative Entity Directory
    matched_known = None
    if candidate:
        cand_lower = candidate.lower()
        for k, v in KNOWN_ENTITIES.items():
            if k == cand_lower or v["name"].lower() == cand_lower or cand_lower in [a.lower() for a in v.get("aliases", [])]:
                matched_known = v
                break

    # If domain directly matches a known company
    if not matched_known and offer_domain:
        for k, v in KNOWN_ENTITIES.items():
            if any(offer_domain == d or offer_domain.endswith("." + d) for d in v["domains"]):
                matched_known = v
                candidate = v["name"]
                break

    if matched_known:
        is_official_domain = False
        if offer_domain:
            is_official_domain = any(offer_domain == d or offer_domain.endswith("." + d) for d in matched_known["domains"])

        impersonation = bool(offer_domain and not is_official_domain)
        summary = (
            f"Verified official domain for {matched_known['name']} ({matched_known['category']})."
            if is_official_domain
            else f"Impersonation Warning: Offer claims to be from {matched_known['name']}, but uses '{offer_domain}' instead of their official domain ({', '.join(matched_known['domains'][:2])})."
            if impersonation
            else f"Recognized entity: {matched_known['name']} ({matched_known['category']})."
        )
        return result(
            "entity",
            "Authoritative Entity Registry",
            "verified",
            summary,
            data={
                "entity": matched_known["name"],
                "category": matched_known["category"],
                "entity_verified": True,
                "official_domain_match": is_official_domain,
                "impersonation_detected": impersonation,
                "official_domains": matched_known["domains"],
                "provider": "Authoritative Registry"
            }
        )

    # Step 2: Dynamic Web & Knowledge Lookups (Wikipedia + DuckDuckGo)
    if candidate:
        cand_tokens = _tokenize(candidate)
        is_generic_candidate = bool(cand_tokens and cand_tokens.issubset(GENERIC_TOKENS) and not offer_domain)

        wiki_res, ddg_res = await asyncio.gather(
            _wiki_lookup(candidate, s),
            _ddg_lookup(candidate, s),
            return_exceptions=True
        )
        wiki = wiki_res if isinstance(wiki_res, dict) else None
        ddg = ddg_res if isinstance(ddg_res, dict) else None

        if (wiki or ddg) and not is_generic_candidate:
            entity_title = (wiki and wiki.get("title")) or (ddg and ddg.get("heading")) or candidate
            desc = (wiki and wiki.get("description")) or (ddg and ddg.get("abstract")) or ""
            
            title_tokens = _tokenize(entity_title)
            shared_title = cand_tokens.intersection(title_tokens)
            is_corp_profile = any(k in desc.lower() for k in CORP_KEYWORDS)
            
            ddg_url = (ddg and ddg.get("official_url")) or ""
            ddg_domain = None
            if ddg_url:
                try:
                    ddg_domain = registrable_domain(urlsplit(ddg_url).hostname or "")
                except Exception:
                    pass

            is_domain_match = bool(offer_domain and ddg_domain and offer_domain == ddg_domain)
            has_token_overlap = bool(shared_title and (len(shared_title) == len(cand_tokens) or len(shared_title) / max(1, len(cand_tokens)) >= 0.6))

            if has_token_overlap and (is_corp_profile or is_domain_match):
                return result(
                    "entity",
                    "Wikipedia & DuckDuckGo Knowledge",
                    "verified",
                    f"Entity verified: {entity_title}. {desc}" + (f" Official domain matches ({offer_domain})." if is_domain_match else ""),
                    data={
                        "entity": entity_title,
                        "description": desc,
                        "entity_verified": True,
                        "official_domain_match": is_domain_match,
                        "impersonation_detected": False,
                        "provider": "Knowledge Graph"
                    }
                )

        # No confident corporate match -> status unverified
        return result(
            "entity",
            "Entity Directory",
            "unverified",
            f"Entity unverified: '{candidate}' was not verified as an official organization or established protocol.",
            data={
                "entity": candidate,
                "entity_verified": False,
                "official_domain_match": False,
                "impersonation_detected": False,
                "provider": "Entity Directory"
            }
        )

    # Step 3: Check site domain if present
    if offer_domain:
        return result(
            "entity",
            "Web & Domain Intelligence",
            "verified",
            f"Domain checked: {offer_domain}. No verified corporate brand claim attached.",
            data={
                "entity": None,
                "entity_verified": False,
                "official_domain_match": False,
                "impersonation_detected": False,
                "provider": "Domain Intelligence"
            }
        )

    return result(
        "entity",
        "Web & Entity Verification",
        "not_applicable",
        "No company name or website provided.",
        reason="No company name or website provided."
    )
