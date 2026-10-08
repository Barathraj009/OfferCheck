"""STEP 1 - claim extraction.
A deterministic heuristic extractor always runs (works offline, English). An optional LLM pass (llm.py)
can fill gaps for unstructured / regional-language text. The LLM never scores anything."""
from __future__ import annotations
import re
from .validators import URL_IN_TEXT

KNOWN_ASSETS = {  # coingecko id -> (name, symbol, regex)
    "bitcoin": ("Bitcoin", "BTC", r"\bbitcoin\b|\bbtc\b"),
    "ethereum": ("Ethereum", "ETH", r"\bethereum\b|\bether\b|\beth\b"),
    "tether": ("Tether", "USDT", r"\btether\b|\busdt\b"),
    "usd-coin": ("USD Coin", "USDC", r"\busd\s?coin\b|\busdc\b"),
    "binancecoin": ("BNB", "BNB", r"\bbnb\b|\bbinance coin\b"),
    "solana": ("Solana", "SOL", r"\bsolana\b|\bsol\b"),
    "ripple": ("XRP", "XRP", r"\bxrp\b|\bripple\b"),
    "dogecoin": ("Dogecoin", "DOGE", r"\bdogecoin\b|\bdoge\b"),
    "cardano": ("Cardano", "ADA", r"\bcardano\b"),
    "litecoin": ("Litecoin", "LTC", r"\blitecoin\b|\bltc\b"),
    "tron": ("TRON", "TRX", r"\btron\b|\btrx\b"),
    "shiba-inu": ("Shiba Inu", "SHIB", r"\bshiba inu\b|\bshib\b"),
}
MULT = {"lakh": 1e5, "lakhs": 1e5, "lac": 1e5, "lacs": 1e5, "crore": 1e7, "crores": 1e7, "cr": 1e7,
        "k": 1e3, "thousand": 1e3, "m": 1e6, "mn": 1e6, "million": 1e6, "billion": 1e9}
CUR = {"₹": "INR", "rs": "INR", "rs.": "INR", "inr": "INR", "rupee": "INR", "rupees": "INR", "$": "USD", "usd": "USD",
       "dollar": "USD", "dollars": "USD", "€": "EUR", "eur": "EUR", "euro": "EUR", "euros": "EUR",
       "£": "GBP", "gbp": "GBP", "pound": "GBP", "pounds": "GBP"}
_M = r"(?:lakhs?|lacs?|crores?|cr|k|mn|million|thousand|billion|m)"
PRICE_PRE = re.compile(r"(?<![A-Za-z])(?P<cur>₹|rs\.?|inr|usd|eur|gbp|[$€£])\s*(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<mult>" + _M + r"\b)?", re.I)
PRICE_POST = re.compile(r"(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<mult>" + _M + r"\b)?\s*(?P<cur>rupees|inr|usd|dollars|euros?|eur|gbp|pounds)\b", re.I)
PRICE_LAKH = re.compile(r"(?<![A-Za-z0-9])(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<mult>lakhs?|lacs?|crores?|cr)\b", re.I)
PRICE_FOR = re.compile(r"(?:\b(?:for|at|only|pay|cost|worth|price(?:\s+is|[:\s]+)?)\s+|@\s*)(?:(?P<cur>₹|rs\.?|inr|usd|eur|gbp|[$€£])\s*)?(?P<num>\d[\d,]*(?:\.\d+)?)\s*(?P<mult>" + _M + r"\b)?(?:\s*(?P<post_cur>rupees|inr|usd|dollars|euros?|eur|gbp|pounds))?\b", re.I)
MARKET_WORDS = ("market", "worth", "normally", "usually", "instead of", "actual", "real price", "trading at", "spot", "current price")
RETURN_WORDS = ("return", "profit", "roi", "interest", "gain", "growth", "yield", "earn", "income", "double", "triple")

FLAGS = {
    "guaranteed_language": ("guaranteed", "guarantee", "risk-free", "risk free", "assured return", "100% safe", "zero risk", "sure profit"),
    "referral": ("refer ", "referral", "commission", "invite friends", "invite your friends", "bring friends", "downline", "recruit", "your team", "friends and family"),
    "urgency": ("hurry", "last chance", "only today", "today only", "act now", "expires", "slots left", "only 2 slots", "pay within", "immediately", "right now", "before the price", "hours left", "need cash", "urgent", "don't miss", "dont miss", "limited slots"),
    "limited_time": ("limited time", "limited offer", "limited slots", "limited period", "offer ends", "hours left", "ends today", "last day", "only a few"),
    "requests_secrets": ("seed phrase", "private key", "recovery phrase", "secret phrase", "share your otp", "send otp", "your password", "12 words", "24 words"),
}
OTHER = {
    "Asks you to continue on Telegram/WhatsApp": ("telegram", "whatsapp", "t.me/"),
    "Asks for direct payment (UPI, bank transfer, gift card or similar)": ("upi", "gpay", "phonepe", "paytm", "bank transfer", "western union", "gift card"),
    "Claims endorsement by a celebrity or official body": ("elon", "endorsed by", "sebi approved", "rbi approved", "government approved"),
}
CHAIN_HINTS = [("bsc", r"\bbnb chain\b|\bbsc\b|binance smart chain|\bbep-?20\b"), ("ethereum", r"\bethereum network\b|\berc-?20\b|\bon ethereum\b|\bether?chain\b"),
               ("polygon", r"\bpolygon\b|\bmatic\b"), ("arbitrum", r"\barbitrum\b"), ("base", r"\bbase chain\b|\bon base\b"), ("solana", r"\bon solana\b|\bspl token\b")]


def empty_claims() -> dict:
    return {"asset_name": None, "asset_symbol": None, "asset_id": None, "contract_address": None, "chain": None,
            "claimed_price": None, "quoted_currency": None, "price_is_per_unit": False, "quantity": None,
            "quantity_assumed": False, "price_verbatim": False, "claimed_market_price": None, "promised_return_pct": None,
            "promised_multiplier": None, "return_period_days": None, "guaranteed_language": False,
            "referral": False, "urgency": False, "limited_time": False, "requests_secrets": False,
            "seller_identity": None, "entity_name": None, "website_url": None, "other_flags": [], "phrases": {}, "extraction_method": "heuristic"}


def is_price_verbatim(claimed_price: float | None, text: str) -> bool:
    """True only if the parsed amount appears in the raw input text in plain, formatted, or word form."""
    if claimed_price is None or not text or claimed_price <= 0:
        return False
    # 1. Check if _prices parsed this exact numeric value from the text
    for p in _prices(text):
        if abs(p["value"] - claimed_price) < 1e-5:
            return True

    # 2. Check direct numeric appearances in text (plain, standard comma, Indian comma)
    if isinstance(claimed_price, (int, float)) and float(claimed_price).is_integer():
        ival = int(claimed_price)
        s_plain = str(ival)
        s_comma = f"{ival:,}"
        
        # Indian grouping (e.g. 150000 -> "1,50,000", 1000000 -> "10,00,000")
        s_ind = ""
        s_str = str(ival)
        if len(s_str) > 3:
            last3 = s_str[-3:]
            rem = s_str[:-3]
            pairs = []
            while len(rem) > 2:
                pairs.insert(0, rem[-2:])
                rem = rem[:-2]
            if rem:
                pairs.insert(0, rem)
            s_ind = ",".join(pairs) + "," + last3

        patterns = [re.escape(s_plain), re.escape(s_comma)]
        if s_ind and s_ind not in patterns:
            patterns.append(re.escape(s_ind))

        rx = re.compile(r"(?<![\d.])(?:" + "|".join(patterns) + r")(?!\d)")
        if rx.search(text):
            return True
    else:
        s_float = f"{claimed_price:g}"
        rx = re.compile(r"(?<![\d.])" + re.escape(s_float) + r"(?!\d)")
        if rx.search(text):
            return True

    return False


def _num(s: str, mult: str | None) -> float:
    v = float(s.replace(",", ""))
    return v * MULT[mult.lower()] if mult else v


def _snippet(text: str, kw: str, width: int = 70) -> str:
    i = text.lower().find(kw)
    return text[max(0, i - 25): i + width].replace("\n", " ").strip() if i >= 0 else ""


def _prices(text: str) -> list[dict]:
    found = []
    # 1. PRE & POST explicit currency
    for rx in (PRICE_PRE, PRICE_POST):
        for m in rx.finditer(text):
            try:
                val = _num(m.group("num"), m.group("mult"))
            except (ValueError, KeyError):
                continue
            cur = CUR.get(m.group("cur").lower().strip())
            if cur and val > 0:
                found.append({"start": m.start(), "end": m.end(), "value": val, "cur": cur})
    # 2. Indian units (lakh / crore)
    for m in PRICE_LAKH.finditer(text):
        try:
            val = _num(m.group("num"), m.group("mult"))
        except (ValueError, KeyError):
            continue
        if val > 0:
            found.append({"start": m.start(), "end": m.end(), "value": val, "cur": "INR"})
    # 3. Contextual for/at/@/price keywords
    has_inr_hint = bool(re.search(r"₹|rs\b|inr\b|rupee", text, re.I))
    for m in PRICE_FOR.finditer(text):
        try:
            val = _num(m.group("num"), m.group("mult"))
        except (ValueError, KeyError):
            continue
        raw_cur = m.group("cur") or m.group("post_cur")
        cur = CUR.get(raw_cur.lower().strip()) if raw_cur else None
        if not cur:
            mult = (m.group("mult") or "").lower()
            if mult in ("lakh", "lakhs", "lac", "lacs", "crore", "crores", "cr") or has_inr_hint:
                cur = "INR"
            else:
                cur = "USD"
        if val > 0:
            found.append({"start": m.start(), "end": m.end(), "value": val, "cur": cur})
    found.sort(key=lambda p: p["start"])
    out = []
    for p in found:  # drop overlaps
        if not out or p["start"] >= out[-1]["end"]:
            out.append(p)
    return out


def _period_days(text: str, near: int) -> float | None:
    unit = {"hour": 1 / 24, "day": 1, "week": 7, "month": 30, "year": 365}
    best = None
    for m in re.finditer(r"(?:in|within|after|every|per|for)\s+(\d+(?:\.\d+)?)\s*(hour|day|week|month|year)s?\b", text, re.I):
        if abs(m.start() - near) <= 80 and (best is None or abs(m.start() - near) < best[0]):
            best = (abs(m.start() - near), float(m.group(1)) * unit[m.group(2).lower()])
    if best:
        return best[1]
    m = re.search(r"\b(daily|weekly|monthly)\b", text, re.I)
    return {"daily": 1, "weekly": 7, "monthly": 30}[m.group(1).lower()] if m and abs(m.start() - near) <= 80 else None


def heuristic_extract(text: str) -> dict:
    c, low = empty_claims(), text.lower()
    # asset: an explicit "Name (SYM)" token beats a known coin that is merely mentioned (e.g. "on BNB Chain")
    known_syms = {v[1] for v in KNOWN_ASSETS.values()}
    tm = re.search(r"\b([A-Z][A-Za-z0-9]{2,20})\s*\(\$?([A-Z0-9]{2,8})\)", text)
    if tm and tm.group(2) not in known_syms:
        c.update(asset_name=tm.group(1), asset_symbol=tm.group(2))
    else:
        scan = re.sub(r"\b(bnb|binance|ethereum|polygon|solana|tron)\s+(chain|network|smart chain|mainnet)\b|\b(erc|bep)-?20\b", " ", low)
        hits = []
        for aid, (name, sym, rx) in KNOWN_ASSETS.items():
            m = re.search(rx, scan)
            if m:
                hits.append((m.start(), aid, name, sym))
        if hits:
            _, aid, name, sym = min(hits)
            c.update(asset_id=aid, asset_name=name, asset_symbol=sym)
        else:
            m = re.search(r"\b(?:token|coin)\s+(?:name|named|called|is)[:\s]+([A-Za-z0-9]{2,20})", text, re.I)
            if m:
                c["asset_name"] = m.group(1)
    # price & quantity
    market_p = offer_p = None
    for p in _prices(text):
        ctx = re.split(r"[.!?\n]", text[max(0, p["start"] - 40):p["start"]])[-1].lower()
        if any(w in ctx for w in MARKET_WORDS):
            market_p = market_p or p
        elif offer_p is None:
            offer_p = p
    if offer_p:
        c.update(claimed_price=offer_p["value"], quoted_currency=offer_p["cur"])
        c["price_is_per_unit"] = bool(re.match(r"\s*(per|each|/|apiece)\b", text[offer_p["end"]:offer_p["end"] + 12].lower()))
    if market_p:
        c["claimed_market_price"] = market_p["value"]
        c["quoted_currency"] = c["quoted_currency"] or market_p["cur"]
    syms = "|".join(rx for _, _, rx in KNOWN_ASSETS.values())
    q = re.search(r"(?<![\w.₹$])(\d[\d,]*(?:\.\d+)?)\s*(?:" + syms + r")", low)
    promo_words = ("bonus", "reward", "cashback", "credit", "credits", "voucher", "gift", "salary", "stipend", "worth", "off", "discount", "fee", "free", "claim", "airdrop")
    is_promo = any(re.search(r"\b" + w + r"\b", low) for w in promo_words)
    if q and not re.match(r"\s*x\b", low[q.end(1):q.end(1) + 3]):
        c["quantity"] = float(q.group(1).replace(",", ""))
    elif offer_p and c["asset_name"] and not c["price_is_per_unit"] and not is_promo:
        c["quantity_assumed"] = True  # "Bitcoin for 32 lakh" -> we assume 1 unit and say so
    # returns
    ret_pos = None
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*%", text):
        before, after = low[max(0, m.start() - 30):m.start()], low[m.end():m.end() + 25]
        if re.search(r"referral|commission|fee|tax|bonus|discount", after) or re.search(r"referral|commission|fee|tax", before[-14:]):
            continue
        if any(w in before + after for w in RETURN_WORDS):
            c["promised_return_pct"], ret_pos = float(m.group(1)), m.start()
            break
    m = re.search(r"\b(\d+(?:\.\d+)?)\s*x\b", low)
    if m and float(m.group(1)) >= 1.5:
        c["promised_multiplier"], ret_pos = float(m.group(1)), ret_pos or m.start()
    elif re.search(r"\bdouble\b", low) and re.search(r"money|investment|returns?|profit|funds", low):
        c["promised_multiplier"], ret_pos = 2.0, low.find("double")
    elif re.search(r"\btriple\b", low):
        c["promised_multiplier"], ret_pos = 3.0, low.find("triple")
    if ret_pos is not None:
        c["return_period_days"] = _period_days(text, ret_pos)
    # flags
    for flag, kws in FLAGS.items():
        for kw in kws:
            if kw in low:
                if flag == "guaranteed_language":
                    retail_guarantees = ("money-back", "money back", "satisfaction", "uptime", "sla", "delivery", "authentic", "authenticity", "price match", "quality")
                    snippet = _snippet(text, kw).lower()
                    if any(rg in snippet for rg in retail_guarantees):
                        continue
                c[flag] = True
                c["phrases"][flag] = _snippet(text, kw)
                break
    for label, kws in OTHER.items():
        if any(k in low for k in kws):
            c["other_flags"].append(label)
    # identifiers & entities
    m = re.search(r"\b0x[a-fA-F0-9]{40}\b", text)
    if m:
        c["contract_address"] = m.group(0)
    for chain, rx in CHAIN_HINTS:
        if re.search(rx, low):
            c["chain"] = chain
            break
    m = URL_IN_TEXT.search(text)
    if m:
        c["website_url"] = m.group(0).rstrip(".,;")
    m = re.search(r"\b(?:i am|i'm|this is|my name is)\s+([A-Z][\w.]*(?:\s+[A-Z][\w.]*){0,3})", text)
    if m:
        c["seller_identity"] = m.group(1)[:60]
    
    # entity / company detection
    known_corps = ("Google", "Apple", "Microsoft", "Amazon", "Meta", "Coinbase", "Binance", "Kraken", "Stripe", "PayPal", "Uniswap", "Aave", "Robinhood", "Revolut", "Fidelity")
    for ent in known_corps:
        if re.search(r"\b" + re.escape(ent.lower()) + r"\b", low):
            c["entity_name"] = ent
            break
    if not c["entity_name"]:
        em = re.search(r"\b(?:from|at|join|by|welcome to)\s+([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)\b", text)
        if em and em.group(1).lower() not in ("telegram", "whatsapp", "our", "the", "my", "this", "us"):
            c["entity_name"] = em.group(1)[:50]
    if not c["entity_name"]:
        fm = re.match(r"^\s*([A-Z][A-Za-z0-9]{2,25})\b", text)
        if fm and fm.group(1).lower() not in ("dear", "hello", "hi", "hey", "warning", "notice", "official", "welcome", "selling", "buying", "invest", "urgent"):
            c["entity_name"] = fm.group(1)
    c["price_verbatim"] = is_price_verbatim(c.get("claimed_price"), text)
    return c


_FLAG_OK = ("telegram", "whatsapp", "phone", "call", "upi", "gpay", "phonepe", "paytm", "payment", "pay",
            "bank", "transfer", "western union", "gift card", "crypto wallet", "celebrity", "endorse",
            "sebi", "rbi", "government", "kyc", "admin", "verify account", "impersonat")


def merge_llm(base: dict, llm: dict | None, raw_text: str = "") -> dict:
    """Fill gaps only. Heuristic values win; booleans are OR-ed. LLM output was already type-validated
    in llm.py. Extra guards so a small/local model (or prompt injection inside the offer) cannot
    inject fields the evidence does not support:
      - `chain` is only accepted when a contract address exists (a chain without an address is a guess)
      - `other_flags` must match known categories (free text from the model is dropped)
      - `seller_identity` was already restricted to name-shaped strings by validate_llm_claims"""
    if not llm:
        return base
    for k, v in llm.items():
        if k not in base or k in ("phrases", "extraction_method", "other_flags", "price_verbatim") or v in (None, "", False):
            continue
        if k == "chain" and not (base.get("contract_address") or llm.get("contract_address")):
            continue
        if isinstance(base[k], bool):
            base[k] = base[k] or bool(v)
        elif base[k] in (None, ""):
            base[k] = v
    for f in llm.get("other_flags") or []:
        fl = f.lower()
        if any(ok in fl for ok in _FLAG_OK) and f not in base["other_flags"] and len(base["other_flags"]) < 6:
            base["other_flags"].append(f)
    base["extraction_method"] = "heuristic+llm"
    if base.get("claimed_price") is not None:
        if raw_text:
            base["price_verbatim"] = is_price_verbatim(base["claimed_price"], raw_text)
        elif "price_verbatim" in llm:
            base["price_verbatim"] = bool(base.get("price_verbatim") or llm.get("price_verbatim"))
        else:
            base["price_verbatim"] = bool(base.get("price_verbatim", False))
    else:
        base["price_verbatim"] = False
    return base
