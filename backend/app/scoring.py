"""STEP 3 - deterministic rule engine. NO LLM involvement.
Evidence (claims + verification results) -> rules -> findings (points) -> score; confidence is computed separately.
Every point in the score is traceable to one finding (rule_id + evidence + source)."""
from __future__ import annotations
from .sources.common import now_iso

# check id -> (label, confidence weight). Weights sum to 100.
CHECKS = {
    "entity": ("Web & Entity verification", 20),
    "market": ("Market data", 20),
    "explorer": ("Contract verification", 10),
    "security": ("Contract security scan", 20),
    "liquidity": ("Liquidity & trading", 10),
    "domain": ("Domain registration", 10),
    "webSafety": ("Website safety", 10),
}
LEVELS = [(80, "very_high", "Very High Risk"), (50, "high", "High Risk"), (25, "moderate", "Moderate Risk"), (0, "low", "Low Risk")]
CLAIM_SRC = "Offer text (your input)"

# Neutral titles + plain-language explanations. Weights live in the rule functions below, next to their conditions.
META = {
    "PRICE_BELOW_MARKET": ("Offer price compared with market price", "Scammers often sell well-known coins far below the real price to lure people who don't know it.", "Real sellers rarely give a large discount, because they could sell at the market price in minutes. A big discount is a common bait."),
    "PRICE_BAIT_UNSTATED_QUANTITY": ("Implausible discount (quantity unstated)", "Real crypto assets are never sold at an 80%+ discount on standard markets without an unstated fractional quantity or bait pricing.", "When an offer promises an asset like Bitcoin far below market price without specifying the amount, it is either an unrealistic bait price or refers to a tiny fraction of a coin. Always verify the exact coin amount you are paying for."),
    "ASSET_NOT_FOUND": ("Listing on a market-data source", "A token that no recognised data source lists is harder to verify.", "Not being listed does not prove a scam - brand-new legitimate tokens may not be indexed yet - but it means you cannot independently confirm that the token is real."),
    "CONTRACT_UNVERIFIED": ("Contract source code published", "If the code is not public, nobody can check what the contract can do.", "Legitimate projects normally publish ('verify') their contract code on the block explorer so anyone can read it. Hidden code can contain traps."),
    "HONEYPOT": ("Honeypot (can you sell?) check", "A honeypot lets people buy but blocks or severely restricts selling.", "A honeypot is a token setup that may allow people to buy the token but prevent or severely restrict them from selling it, so your money gets trapped."),
    "MINTABLE": ("Unlimited minting check", "If the creator can create new tokens at will, your share can be diluted to nearly zero.", "'Minting' means creating new tokens. If an owner can mint without limit they can print tokens and sell them, crashing the price for everyone else."),
    "OWNER_PRIVILEGES": ("Owner / admin powers", "Powerful admin functions let the creator change the rules after you invest.", "Some contracts let the owner reclaim control, edit balances, pause transfers or hide who the owner is. These powers can be used to trap or drain holders."),
    "SELL_TAX": ("Sell tax", "A very high sell tax makes it impractical to get your money back.", "A sell tax is a fee taken each time someone sells. Above ~10% it is unusual; at 30-50%+ most of your money is taken when you exit."),
    "LIQUIDITY": ("Liquidity and trading activity", "Without real liquidity you may be unable to sell at a fair price, or at all.", "Liquidity is the pool of money that lets people trade a token. Tiny or missing liquidity means prices are easy to manipulate and exits may be impossible."),
    "CONCENTRATION": ("Holder concentration", "If a few wallets hold most of the supply, they can crash the price by selling.", "When one wallet or a handful of wallets hold most tokens, they control the market - this is common in 'rug pulls'."),
    "GUARANTEED_RETURNS": ("'Guaranteed' or risk-free language", "No legitimate investment can guarantee profit.", "Real investments always carry risk. Promises such as 'guaranteed' or 'risk-free' are a classic fraud signal."),
    "UNREALISTIC_RETURNS": ("Promised returns", "Very high returns in a short time are not realistic.", "Returns like doubling in a month imply gains of over 1000% per year. Offers like this are typically Ponzi-style or fake-token schemes."),
    "REFERRAL_MODEL": ("Referral / commission model", "Paying you to recruit others is how many pyramid-style schemes spread.", "If the money comes from bringing in new people rather than from a real product, early members are paid with later members' deposits until it collapses."),
    "URGENCY": ("Urgency / pressure language", "Pressure to act fast is meant to stop you from checking.", "Fraudsters create deadlines and 'limited slots' so you pay before you verify."),
    "SECRETS_REQUESTED": ("Request for secret credentials", "Seed phrases, private keys, passwords and OTPs give full access to your funds.", "Nobody legitimate will ever need these. Sharing them lets someone empty your wallet or account instantly."),
    "NEW_DOMAIN": ("Website age", "Scam sites are often created days before a campaign.", "A very recently registered domain has no track record. Many fraud sites are only a few days or weeks old."),
    "MALICIOUS_SITE": ("Known-dangerous website listing", "Browser-safety lists flag sites already reported for phishing or malware.", "A match means a security provider has already classified the site as dangerous."),
    "OFFICIAL_ENTITY_VERIFIED": ("Verified official organization / domain", "The offer originates from a verified legitimate entity on their official domain.", "Verification confirmed this domain belongs to the official organization."),
    "BRAND_IMPERSONATION": ("Brand impersonation warning", "The offer claims to represent a recognized company but uses an unverified or mismatched domain.", "Scammers frequently impersonate trusted brands using lookalike or third-party websites."),
    "WEB_SCAM_ALERT": ("Web fraud warning", "Web intelligence indicates this offer or domain has been flagged as suspicious.", "Public reports and search data associate this entity or offer with fraudulent activity."),
}


def severity(points: int) -> str:
    return "ok" if points <= 0 else "critical" if points >= 35 else "high" if points >= 20 else "medium" if points >= 10 else "low"


def _f(rid: str, points: int, observed: str, check: dict | None = None, *, status: str = "verified", evidence: dict | None = None, source: str | None = None) -> dict:
    title, why, explain = META[rid]
    return {"rule_id": rid, "title": title, "severity": severity(points), "points": points, "observed": observed, "why": why,
            "explanation": explain, "source": source or ((check.get("source") if check else None) or CLAIM_SRC),
            "check_id": (check.get("check_id") if check else None) or "claims", "status": status,
            "timestamp": (check.get("timestamp") if check else None) or now_iso(), "demo": bool(check and check.get("demo")),
            "evidence": evidence or {}}


def _ok(c: dict | None) -> bool:
    return bool(c) and c["status"] == "verified"


def unit_price(cl: dict) -> float | None:
    p = cl.get("claimed_price")
    if p is None:
        return None
    return p if cl.get("price_is_per_unit") or not cl.get("quantity") else p / cl["quantity"]


def money(cur: str, v: float) -> str:
    return f"{cur.upper()} {v:,.2f}" if v < 1000 else f"{cur.upper()} {v:,.0f}"


# ---------------- rules: each returns a finding or None ----------------
def r_price(cl, ck):
    m = ck.get("market")
    unit = unit_price(cl)
    if unit is None or not _ok(m):
        return None
    cur = (cl.get("quoted_currency") or "").lower()
    mkt = (m["data"].get("prices") or {}).get(cur)
    if not mkt:
        return None
    diff = (mkt - unit) / mkt * 100
    if cl.get("quantity_assumed") and diff > 80:
        if not cl.get("price_verbatim"):
            return None
        # Verbatim bait price: quantity unstated + diff > 80% + verbatim in text
        sym = cl.get("asset_symbol") or cl.get("asset_name") or "BTC"
        obs = f"Offer is ~{diff:.1f}% below market — either a bait price or a tiny fraction of 1 {sym}; verify exactly what quantity you receive."
        return _f("PRICE_BAIT_UNSTATED_QUANTITY", 25, obs, m,
                  evidence={"offer_unit_price": unit, "market_price": mkt, "difference_pct": round(diff, 1),
                            "currency": cur.upper(), "quantity_assumed": True, "price_verbatim": True})
    pts = 40 if diff > 60 else 35 if diff > 40 else 28 if diff > 20 else 10 if diff > 10 else 0
    if pts == 0:
        return None
    sym = cl.get("asset_symbol") or "unit"
    note = " (quantity not stated, so 1 unit was assumed)" if cl.get("quantity_assumed") else ""
    obs = f"Offer: {money(cur, unit)} per {sym}{note}. Observed market price: {money(cur, mkt)}. Difference: {abs(diff):.1f}% {'below' if diff >= 0 else 'above'} market."
    return _f("PRICE_BELOW_MARKET", pts, obs, m, evidence={"offer_unit_price": unit, "market_price": mkt, "difference_pct": round(diff, 1), "currency": cur.upper()})


def r_not_found(cl, ck):
    m = ck.get("market")
    if not m:
        return None
    # 3-state model:
    # 1. LISTED (status == "verified"): Handled by r_price, 0 pts here.
    # 2. LOOKUP-FAILED (status in ("unavailable", "error")): 0 pts.
    # 3. NOT-LISTED (status == "not_found"): Successful empty lookup -> 12 pts with evidence.
    if m.get("status") == "not_found":
        target = cl.get("asset_name") or cl.get("asset_symbol") or cl.get("contract_address") or "asset"
        obs = f"The asset '{target}' could not be independently verified through market-data sources ({m.get('source', 'CoinGecko')})."
        return _f("ASSET_NOT_FOUND", 12, obs, m, status="not_found", evidence={"status": "NOT-LISTED", "queried_asset": str(target), "source": m.get("source")})
    return None


def r_unverified(cl, ck):
    e, g = ck.get("explorer"), ck.get("security")
    if _ok(e) and e["data"].get("source_verified") is not None:
        v = e["data"]["source_verified"]
        return _f("CONTRACT_UNVERIFIED", 0 if v else 12, "Contract source code is published and verified." if v else "Contract source code is NOT verified on the block explorer.", e)
    if _ok(g) and g["data"].get("open_source") is not None:  # fallback when explorer is unavailable
        v = g["data"]["open_source"]
        return _f("CONTRACT_UNVERIFIED", 0 if v else 12, ("GoPlus reports the contract as open source." if v else "GoPlus reports the contract source is NOT open/verified.") + " (block-explorer check unavailable)", g)


def r_honeypot(cl, ck):
    g = ck.get("security")
    if not _ok(g):
        return None
    d = g["data"]
    if d.get("honeypot"):
        return _f("HONEYPOT", 40, "Security scan flags this token as a honeypot (selling may be blocked).", g)
    if d.get("cannot_sell_all"):
        return _f("HONEYPOT", 30, "Security scan indicates holders cannot sell all of their tokens.", g)
    if d.get("honeypot") is False:
        return _f("HONEYPOT", 0, "No honeypot indicator in the security scan (this does not guarantee you can sell).", g)


def r_mint(cl, ck):
    g = ck.get("security")
    if _ok(g) and g["data"].get("mintable") is not None:
        return _f("MINTABLE", 35 if g["data"]["mintable"] else 0, "The contract allows new tokens to be minted." if g["data"]["mintable"] else "No minting function flagged.", g)


def r_owner(cl, ck):
    g = ck.get("security")
    if not _ok(g):
        return None
    d = g["data"]
    major = [t for k, t in (("takeback_ownership", "owner can take back ownership"), ("owner_change_balance", "owner can change balances"), ("hidden_owner", "hidden owner"), ("selfdestruct", "contract can self-destruct")) if d.get(k)]
    minor = [t for k, t in (("transfer_pausable", "transfers can be paused"), ("blacklist", "addresses can be blacklisted")) if d.get(k)]
    if major:
        return _f("OWNER_PRIVILEGES", min(30, 20 + 5 * (len(major) - 1)), "Dangerous owner capabilities flagged: " + ", ".join(major + minor) + ".", g, evidence={"major": major, "minor": minor})
    if minor:
        return _f("OWNER_PRIVILEGES", 8, "Owner can restrict users: " + ", ".join(minor) + ".", g, evidence={"minor": minor})
    return _f("OWNER_PRIVILEGES", 0, "No dangerous owner capabilities flagged.", g)


def r_tax(cl, ck):
    g = ck.get("security")
    t = g["data"].get("sell_tax_pct") if _ok(g) else None
    if t is None:
        return None
    pts = 35 if t >= 50 else 30 if t >= 30 else 20 if t > 10 else 0
    return _f("SELL_TAX", pts, f"Sell tax: {t:.1f}% (buy tax: {g['data'].get('buy_tax_pct', 0) or 0:.1f}%).", g)


def r_liq(cl, ck):
    l = ck.get("liquidity")
    if not l:
        return None
    if l["status"] == "not_found":
        return _f("LIQUIDITY", 15, "No trading pairs were found for this contract (a limited signal only - a very new token, an unsupported network, or a token that is not yet tradable can all cause this).", l, status="not_found")
    if not _ok(l):
        return None
    d = l["data"]
    liq = d.get("total_liquidity_usd") or 0
    pts = 25 if liq < 5_000 else 15 if liq < 25_000 else 5 if liq < 100_000 else 0
    return _f("LIQUIDITY", pts, f"Total liquidity across {d.get('pair_count', 0)} pair(s): ${liq:,.0f}; 24h volume: ${d.get('volume_24h_usd') or 0:,.0f}.", l)


def r_conc(cl, ck):
    g = ck.get("security")
    if not _ok(g):
        return None
    t1, t10 = g["data"].get("top_holder_pct"), g["data"].get("top10_pct")
    if t1 is None and t10 is None:
        return None
    pts = 20 if (t1 or 0) >= 50 or (t10 or 0) >= 90 else 15 if (t1 or 0) >= 30 or (t10 or 0) >= 70 else 0
    return _f("CONCENTRATION", pts, f"Largest non-contract holder: {t1 or 0:.1f}% of supply; top 10 holders: {t10 or 0:.1f}%.", g)


def r_guar(cl, ck):
    phrase = ((cl.get("phrases") or {}).get("guaranteed_language") or "").strip()
    if cl.get("guaranteed_language") and phrase:
        return _f("GUARANTEED_RETURNS", 25, f'The offer uses guaranteed / risk-free language: "{phrase}"', status="claim", evidence={"matched_text": phrase, "claim_type": "guaranteed_language"})
    return None


def r_returns(cl, ck):
    pct, mult, days = cl.get("promised_return_pct"), cl.get("promised_multiplier"), cl.get("return_period_days")
    if not pct and mult:
        pct = (mult - 1) * 100
    if not pct or pct <= 0:
        return None
    if days and days > 0:
        ann = pct * 365 / days
        pts = 25 if ann >= 1000 else 20 if ann >= 100 else 0
        obs = f"Promised return: {pct:,.0f}% in {days:g} day(s) - roughly {ann:,.0f}% per year."
    else:
        pts, ann = (15 if pct >= 50 else 0), None
        obs = f"Promised return: {pct:,.0f}% (no time period stated)."
    if pts:
        return _f("UNREALISTIC_RETURNS", pts, obs, status="claim", evidence={"pct": pct, "days": days, "annualised_pct": ann})
    return None


def r_ref(cl, ck):
    phrase = ((cl.get("phrases") or {}).get("referral") or "").strip()
    if cl.get("referral") and phrase:
        return _f("REFERRAL_MODEL", 12, f'The offer rewards you for referring others: "{phrase}"', status="claim", evidence={"matched_text": phrase, "claim_type": "referral"})
    return None


def r_urg(cl, ck):
    phrases = cl.get("phrases") or {}
    phrase = (phrases.get("urgency") or phrases.get("limited_time") or "").strip()
    if (cl.get("urgency") or cl.get("limited_time")) and phrase:
        return _f("URGENCY", 10, f'Pressure / deadline language detected: "{phrase}"', status="claim", evidence={"matched_text": phrase, "claim_type": "urgency"})
    return None


def r_secret(cl, ck):
    phrase = ((cl.get("phrases") or {}).get("requests_secrets") or "").strip()
    if cl.get("requests_secrets") and phrase:
        return _f("SECRETS_REQUESTED", 40, f'The offer mentions seed phrases, private keys, passwords or OTPs: "{phrase}"', status="claim", evidence={"matched_text": phrase, "claim_type": "requests_secrets"})
    return None


def r_domain(cl, ck):
    d = ck.get("domain")
    if not _ok(d) or d["data"].get("age_days") is None:
        return None
    a = d["data"]["age_days"]
    pts = 20 if a < 7 else 15 if a < 30 else 0
    return _f("NEW_DOMAIN", pts, f"Domain {d['data'].get('domain', '')} was registered {a} day(s) ago ({d['data'].get('registered', 'date unknown')}).", d)


def r_web(cl, ck):
    w = ck.get("webSafety")
    if not _ok(w):
        return None
    th = w["data"].get("threats") or []
    if th:
        return _f("MALICIOUS_SITE", 45, "Flagged by the website-safety service: " + ", ".join(th), w)
    return _f("MALICIOUS_SITE", 0, "No match in the website-safety lists. (This does not prove the site is safe - new sites may not be listed yet.)", w)


def r_entity(cl, ck):
    e = ck.get("entity")
    if not _ok(e):
        return None
    d = e.get("data") or {}
    if d.get("impersonation_detected"):
        ent = d.get("entity") or "a recognized organization"
        doms = ", ".join(d.get("official_domains") or [])
        obs = f"The offer claims affiliation with {ent}, but does not use their official domain ({doms})."
        return _f("BRAND_IMPERSONATION", 45, obs, e, evidence={"entity": ent, "official_domains": d.get("official_domains")})
    if d.get("entity_verified") and d.get("official_domain_match"):
        ent = d.get("entity") or "Organization"
        cat = d.get("category") or "Verified Entity"
        obs = f"Verified official domain for {ent} ({cat})."
        return _f("OFFICIAL_ENTITY_VERIFIED", 0, obs, e, evidence={"entity": ent, "category": cat, "official": True})
    return None


RULES = [r_price, r_not_found, r_unverified, r_honeypot, r_mint, r_owner, r_tax, r_liq, r_conc, r_guar, r_returns, r_ref, r_urg, r_secret, r_domain, r_web, r_entity]


def coverage(ck: dict) -> dict:
    avail, unavail, na, aw, apw = [], [], [], 0, 0
    for cid, (label, w) in CHECKS.items():
        c = ck.get(cid)
        st = c["status"] if c else "not_applicable"
        if st == "not_applicable":
            na.append({"check_id": cid, "label": label, "reason": (c or {}).get("reason") or "Required input not provided."})
            continue
        apw += w
        if st in ("verified", "not_found"):
            avail.append(cid)
            aw += w
        else:
            unavail.append({"check_id": cid, "label": label, "source": c["source"], "reason": c.get("reason") or "Unavailable."})
    return {"available": len(avail), "total": len(CHECKS), "unavailable": unavail, "not_applicable": na, "_aw": aw, "_apw": apw}


def detect_conflicts(cl: dict, ck: dict) -> list[str]:
    out = []
    e, g = ck.get("explorer"), ck.get("security")
    if _ok(e) and _ok(g) and e["data"].get("source_verified") is not None and g["data"].get("open_source") is not None and e["data"]["source_verified"] != g["data"]["open_source"]:
        out.append("Sources disagree on whether the contract source code is verified (block explorer vs GoPlus).")
    m, cmp_ = ck.get("market"), cl.get("claimed_market_price")
    if _ok(m) and cmp_:
        obs = (m["data"].get("prices") or {}).get((cl.get("quoted_currency") or "").lower())
        if obs and abs(cmp_ - obs) / obs > 0.25:
            out.append(f"The seller states a market price ({money(cl['quoted_currency'], cmp_)}) that differs by more than 25% from the observed price ({money(cl['quoted_currency'], obs)}).")
    return out


def confidence(cov: dict, conflicts: list[str]) -> dict:
    """
    Confidence Formula:
    Confidence Score = sum(weight of verified/answered checks) - conflict_penalties
    Total available check weights sum to 100 across the 7 checks:
      - entity: 20, market: 20, explorer: 10, security: 20, liquidity: 10, domain: 10, webSafety: 10
    Confidence Level:
      - High: score >= 65
      - Medium: 35 <= score < 65
      - Low: score < 35
    """
    aw = cov["_aw"]  # Sum of weights for completed (verified/not_found) checks
    reasons = [f"{cov['available']} of {cov['total']} verification checks returned an answer."]
    
    score = aw
    if cov["unavailable"]:
        reasons.append("Unavailable: " + "; ".join(f"{u['label']} ({u['source']})" for u in cov["unavailable"]) + ".")
    if cov["not_applicable"]:
        reasons.append(f"{len(cov['not_applicable'])} check(s) not run because the needed input was not provided (" + ", ".join(n["label"] for n in cov["not_applicable"]) + ").")
    if cov["_apw"] == 0:
        reasons.append("No external checks could be run: provide a token name, contract address or website to enable them.")

    if conflicts:
        penalty = min(20, 10 * len(conflicts))
        score -= penalty
        reasons.append(f"{len(conflicts)} conflict(s) between data points reduce confidence (-{penalty} pts).")

    score = max(0, min(100, score))
    level = "High" if score >= 65 else "Medium" if score >= 35 else "Low"
    return {"score": score, "level": level, "reasons": reasons}


def assess(claims: dict, checks: dict) -> dict:
    findings = [f for f in (r(claims, checks) for r in RULES) if f]
    raw = sum(f["points"] for f in findings)
    score = min(100, max(0, raw))
    cov = coverage(checks)
    conflicts = detect_conflicts(claims, checks)
    conf = confidence(cov, conflicts)

    ent_check = checks.get("entity")
    ent_data = (ent_check.get("data") or {}) if _ok(ent_check) else {}
    is_verified_entity = bool(ent_data.get("entity_verified") and ent_data.get("official_domain_match"))
    is_impersonation = bool(ent_data.get("impersonation_detected"))
    mkt_check = checks.get("market")
    mkt_verified = bool(_ok(mkt_check) and mkt_check.get("status") == "verified")
    exp_check = checks.get("explorer")
    exp_verified = bool(_ok(exp_check) and (exp_check.get("data") or {}).get("source_verified") is True)
    sec_check = checks.get("security")
    sec_verified = bool(_ok(sec_check) and (sec_check.get("data") or {}).get("honeypot") is False)
    
    has_positive_verification = is_verified_entity or mkt_verified or exp_verified or sec_verified
    has_critical_exploit = any(f["rule_id"] in ("HONEYPOT", "SECRETS_REQUESTED", "MALICIOUS_SITE", "BRAND_IMPERSONATION") and f["points"] > 0 for f in findings)

    # 3 distinct outcomes: verified-legit / suspicious / could-not-verify
    if is_verified_entity and not has_critical_exploit:
        outcome = "verified-legit"
        outcome_label = "Verified Legitimate"
        score = min(score, 15)  # Verified official company domain
        key, label = "low", "Low Risk"
        insufficient = False
    elif is_impersonation or has_critical_exploit or score >= 25:
        outcome = "suspicious"
        outcome_label = "Suspicious" if score < 50 else "Suspicious / High Risk"
        key, label = next((k, l) for t, k, l in LEVELS if score >= t)
        insufficient = False
    elif not has_positive_verification:
        outcome = "could-not-verify"
        outcome_label = "Could Not Verify (Inconclusive)"
        score = min(score, 20)  # Capped: never assume max risk on weak/missing evidence
        key, label = "insufficient", "Could Not Verify"
        insufficient = True
    else:
        outcome = "verified-legit"
        outcome_label = "Low Risk / Likely Safe"
        key, label = "low", "Low Risk"
        insufficient = False

    findings.sort(key=lambda f: -f["points"])
    cov_clean = {k: v for k, v in cov.items() if not k.startswith("_")}
    return {
        "findings": findings,
        "risk": {
            "score": score,
            "raw_points": raw,
            "level": label,
            "level_key": key,
            "insufficient_evidence": insufficient,
            "outcome": outcome,
            "outcome_label": outcome_label,
        },
        "confidence": conf,
        "coverage": cov_clean,
        "conflicts": conflicts
    }
