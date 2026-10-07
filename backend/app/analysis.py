"""Orchestrator: Input -> claims -> verification -> deterministic scoring -> confidence -> explanation."""
from __future__ import annotations
import asyncio
import hashlib
import logging
from . import demo
from .explain import CHECKLIST, DISCLAIMERS, NEVER_SHARE, compact_for_llm, template_summary
from .extraction import KNOWN_ASSETS, heuristic_extract, merge_llm
from .llm import LANGS, extract_claims_llm, summarize_llm
from .scoring import CHECKS, assess
from .sources.chain import check_explorer, check_liquidity, check_security
from .sources.common import SourceError, now_iso, result
from .sources.market import check_market
from .sources.web import check_domain, check_web_safety
from .validators import CHAINS, ValidationFailure, normalize_url, sanitize_text, validate_address

log = logging.getLogger("scamcheck")
SRC = {"market": "CoinGecko", "explorer": "Contract verification", "security": "GoPlus Security", "liquidity": "DexScreener", "domain": "RDAP (rdap.org)", "webSafety": "Threat-feed check"}


def _na(cid, reason):
    return result(cid, SRC[cid], "not_applicable", reason, reason=reason)


def _unavail(cid, src, reason):
    return result(cid, src, "unavailable", "Verification unavailable from this source.", reason=reason)


async def _safe(cid, src, coro, timeout):
    try:
        return await asyncio.wait_for(coro, timeout)
    except asyncio.TimeoutError:
        log.warning("timeout check=%s", cid)
        return _unavail(cid, src, "The service did not respond in time.")
    except SourceError as e:
        log.info("source unavailable check=%s kind=%s", cid, e.kind)
        if e.kind == "no_key":
            return _unavail(cid, src, e.reason + " Add it to .env to enable this check.")
        return _unavail(cid, src, e.reason)
    except Exception:  # never let one source break the report
        log.exception("unexpected error check=%s", cid)
        return _unavail(cid, src, "Unexpected error while contacting this source.")


async def run_analysis(p: dict, s) -> dict:
    mode = p.get("mode") if p.get("mode") in ("demo", "live") else s.default_mode
    scenario = p.get("demo_scenario") if mode == "demo" and p.get("demo_scenario") in demo.SCENARIOS else None
    if scenario:  # a sample can be requested by id alone; blank fields are filled from the scenario
        p = dict(p)
        for k, v in demo.SCENARIOS[scenario]["inputs"].items():
            if v and not str(p.get(k) or "").strip():
                p[k] = v
    text = sanitize_text(p.get("text"), s.max_input_chars)
    token = sanitize_text(p.get("token_name"), 100)
    url_raw, addr_raw = (p.get("url") or "").strip(), (p.get("contract_address") or "").strip()
    if not (text or token or url_raw or addr_raw):
        raise ValidationFailure("text", "Add something to check: describe the offer, or enter a website, token name or contract address.")
    lang = p.get("language") if p.get("language") in LANGS else "en"

    # ---- STEP 1: claims ----
    claims = heuristic_extract(text)
    llm_provider = None
    if mode == "live" and text:
        out = await extract_claims_llm(text, s)
        if out:
            llm_claims, llm_provider = out
            claims = merge_llm(claims, llm_claims)
    if token:
        claims.update(asset_name=token, asset_id=None, asset_symbol=None)
        for aid, (name, sym, _) in KNOWN_ASSETS.items():
            if token.lower() in (name.lower(), sym.lower(), aid):
                claims.update(asset_id=aid, asset_name=name, asset_symbol=sym)
    chain = (p.get("chain") or claims.get("chain") or "").lower()
    claims["chain"] = chain or None
    claims["contract_address"] = validate_address(addr_raw or claims.get("contract_address") or "", chain) or None
    site, notes = None, []
    if url_raw:
        site = normalize_url(url_raw)  # explicit link: invalid -> clear error
    elif claims.get("website_url"):
        try:
            site = normalize_url(claims["website_url"])
        except ValidationFailure as e:
            notes.append("A link found in the text was not analysed: " + e.message)
    claims["website_url"] = site["url"] if site else None

    # ---- STEP 2: verification ----
    addr, c_ok = claims["contract_address"], claims["chain"] in CHAINS
    plan: dict[str, tuple[str, object]] = {}  # cid -> ("skip"|"run", payload)
    ident = bool(addr or claims.get("asset_name") or claims.get("asset_id"))
    if not ident:
        plan["market"] = ("skip", "No asset name or contract address provided.")
    elif addr and not c_ok and not claims.get("asset_name"):
        plan["market"] = ("unavail", f"Contract lookups on '{claims['chain']}' are not supported yet.")
    else:
        plan["market"] = ("run", check_market)
    for cid, fn in (("explorer", check_explorer), ("security", check_security), ("liquidity", check_liquidity)):
        plan[cid] = ("skip", "No contract address provided.") if not addr else ("run", fn) if c_ok else ("unavail", f"The network '{claims['chain']}' cannot be verified yet.")
    for cid, fn in (("domain", check_domain), ("webSafety", check_web_safety)):
        plan[cid] = ("run", fn) if site else ("skip", "No website provided.")

    checks: dict[str, dict] = {}
    tasks = {}
    for cid, (kind, x) in plan.items():
        src = CHAINS[claims["chain"]]["explorer"] if cid == "explorer" and c_ok else SRC[cid]
        if kind == "skip":
            checks[cid] = _na(cid, x)
        elif kind == "unavail":
            checks[cid] = _unavail(cid, src, x)
        elif mode == "demo":
            checks[cid] = demo.demo_check(scenario, cid)
        else:
            arg = site if cid in ("domain", "webSafety") else claims
            tasks[cid] = _safe(cid, src, x(arg, s), s.http_timeout + 4)
    if tasks:  # all live checks run concurrently; one failure never blocks the others
        for cid, res in zip(tasks, await asyncio.gather(*tasks.values())):
            checks[cid] = res

    # ---- STEP 3: deterministic scoring + confidence ----
    core = assess(claims, checks)

    # ---- STEP 4: explanation ----
    summary, method = template_summary(core), "template"
    if mode == "live":
        out = await summarize_llm(compact_for_llm(core), lang, s)
        if out:
            summary, method = out[0], "llm"
            llm_provider = llm_provider or out[1]
    return {
        "mode": mode, "is_demo": mode == "demo", "demo_scenario": scenario, "generated_at": now_iso(),
        "input_id": hashlib.sha256((text + token + url_raw + addr_raw).encode()).hexdigest()[:16],
        "claims": claims, "extraction": {"method": claims["extraction_method"], "llm_configured": s.configured()["llm"],
                                         "llm_provider": llm_provider, "notes": notes},
        "checks": [checks[c] | {"label": CHECKS[c][0]} for c in CHECKS], **core,
        "summary": {"text": summary, "method": method, "language": lang if method == "llm" else "en"},
        "checklist": CHECKLIST, "never_share": NEVER_SHARE, "disclaimers": DISCLAIMERS,
    }
