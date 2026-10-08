"""Market data with a zero-cost provider chain:
  CoinGecko (keyless / free key) -> DexScreener (by contract, keyless) -> Binance ticker (by symbol, keyless).
The first provider that answers 'verified' wins; a definitive 'not found' from one source is kept as
the answer only if no later provider can rescue it (e.g. a token listed on DEXs but not on CoinGecko).
FX conversion (USD-only sources -> INR/EUR/GBP) uses Frankfurter (ECB reference rates) and is labelled."""
from __future__ import annotations
import re
from ..validators import CHAINS
from .base import run_chain
from .chain import fetch_dex_pairs
from .common import SourceError, cached, request_json, result

SRC = "CoinGecko"
BASE = "https://api.coingecko.com/api/v3"
VS = "usd,inr,eur,gbp"
FX_CURS = ("inr", "eur", "gbp")


def _headers(s):
    return {"x-cg-demo-api-key": s.coingecko_api_key} if s.coingecko_api_key else {}


async def _get(s, path, params=None):
    key = f"cg:{path}:{sorted((params or {}).items())}"
    return await cached(key, s.cache_ttl, lambda: request_json("GET", BASE + path, params=params, headers=_headers(s), timeout=s.http_timeout))


async def _fx_usd(s) -> dict:
    """USD -> INR/EUR/GBP reference rates (Frankfurter / ECB). Cached 6h. Raises on failure."""
    async def go():
        d = await request_json("GET", "https://api.frankfurter.app/latest", params={"from": "USD", "to": "INR,EUR,GBP"}, timeout=s.http_timeout)
        r = (d or {}).get("rates") or {}
        if not r.get("INR"):
            raise SourceError("FX service returned no rates.", "malformed")
        return {"usd": 1.0, "inr": float(r["INR"]), "eur": float(r.get("EUR") or 0) or None, "gbp": float(r.get("GBP") or 0) or None}
    return await cached("fx:usd", 21600, go)


async def _prices_from_usd(s, usd: float) -> dict:
    """Convert a USD price to the reporting currencies. Returns {'usd': x, ...} with only
    currencies that could actually be obtained - never invents a conversion."""
    try:
        fx = await _fx_usd(s)
        return {k: (round(usd * v, 6) if v else None) for k, v in fx.items()}
    except SourceError:
        return {"usd": usd}  # FX unavailable: report USD only (the price rule then simply
        # cannot compare non-USD offers - it does NOT guess a rate)


async def _coingecko(claims: dict, s) -> dict:
    addr, chain, name, sym, aid = claims.get("contract_address"), claims.get("chain"), claims.get("asset_name"), claims.get("asset_symbol"), claims.get("asset_id")
    if addr and chain in CHAINS:  # most precise: look up by contract
        try:
            d = await _get(s, f"/coins/{CHAINS[chain]['cg']}/contract/{addr}", {"localization": "false", "tickers": "false", "community_data": "false", "developer_data": "false"})
            md = d.get("market_data") or {}
            prices = {k: md.get("current_price", {}).get(k) for k in VS.split(",")}
            usd_val = _f(prices.get("usd"))
            fx_used = False
            if usd_val and any(prices.get(c) is None for c in FX_CURS):
                try:
                    fx_prices = await _prices_from_usd(s, usd_val)
                    for c, v in fx_prices.items():
                        if prices.get(c) is None and v is not None:
                            prices[c] = v
                            fx_used = True
                except Exception:
                    pass
            coin = {"id": d.get("id"), "name": d.get("name"), "symbol": (d.get("symbol") or "").upper(),
                    "prices": prices,
                    "market_cap_usd": (md.get("market_cap") or {}).get("usd"), "volume_24h_usd": (md.get("total_volume") or {}).get("usd"),
                    "provider": "CoinGecko", "fx_converted": fx_used}
            summary = f"{coin['name']} found. USD {coin['prices'].get('usd')}, INR {coin['prices'].get('inr')}."
            if claims.get("claimed_price") is None:
                summary += " Offer price not detected — add it to run the price check."
            return result("market", SRC, "verified", summary, data=coin)
        except SourceError as e:
            if e.kind != "not_found":
                raise
            if not (name or aid):
                return result("market", SRC, "not_found", "The contract is not listed on CoinGecko.", data={"queried": addr, "provider": "CoinGecko"})
    if not (name or aid):
        raise SourceError("No asset name or contract address to look up.", "error")
    cid = aid
    if not cid:
        sr = await _get(s, "/search", {"query": name})
        q = (name or "").lower()
        match = next((c for c in (sr or {}).get("coins", []) if c.get("name", "").lower() == q or c.get("symbol", "").lower() == q or (sym and c.get("symbol", "").lower() == sym.lower())), None)
        if not match:
            return result("market", SRC, "not_found", "No exact match on CoinGecko.", data={"queried": name, "provider": "CoinGecko"})
        cid = match["id"]
    p = await _price_by_id(s, cid)
    if not p:
        return result("market", SRC, "not_found", "No price data returned.", data={"queried": cid, "provider": "CoinGecko"})
    prices = {k: p.get(k) for k in VS.split(",")}
    usd_val = _f(prices.get("usd"))
    fx_used = False
    if usd_val and any(prices.get(c) is None for c in FX_CURS):
        try:
            fx_prices = await _prices_from_usd(s, usd_val)
            for c, v in fx_prices.items():
                if prices.get(c) is None and v is not None:
                    prices[c] = v
                    fx_used = True
        except Exception:
            pass
    coin = {"id": cid, "name": name, "symbol": sym, "prices": prices,
            "market_cap_usd": p.get("usd_market_cap"), "volume_24h_usd": p.get("usd_24h_vol"),
            "provider": "CoinGecko", "fx_converted": fx_used}
    summary = f"{coin['name'] or coin['id']} found. USD {coin['prices'].get('usd')}, INR {coin['prices'].get('inr')}."
    if claims.get("claimed_price") is None:
        summary += " Offer price not detected — add it to run the price check."
    return result("market", SRC, "verified", summary, data=coin)


async def _price_by_id(s, cid):
    d = await _get(s, "/simple/price", {"ids": cid, "vs_currencies": VS, "include_market_cap": "true", "include_24hr_vol": "true"})
    return (d or {}).get(cid)


async def _dexscreener(claims: dict, s) -> dict:
    """By contract address: price of the most liquid pair + DEX volume. Uses the shared
    DexScreener cache key, so if the liquidity check also runs there is ONE upstream call."""
    addr, chain = claims.get("contract_address"), claims.get("chain")
    if not addr or chain not in CHAINS:
        raise SourceError("No contract address on a supported network for a DEX lookup.", "error")
    pairs = await fetch_dex_pairs(chain, addr, s)
    if not pairs:
        raise SourceError("No trading pairs found on DexScreener for this contract.", "not_found")
    best = max(pairs, key=lambda p: (p.get("liquidity") or {}).get("usd") or 0)
    usd = _f(best.get("priceUsd"))
    if usd is None:
        raise SourceError("DexScreener returned no price for these pairs.", "malformed")
    tok = best.get("baseToken") or {}
    prices = await _prices_from_usd(s, usd)
    data = {"id": None, "name": tok.get("name") or claims.get("asset_name"), "symbol": (tok.get("symbol") or "").upper() or claims.get("asset_symbol"),
            "prices": prices, "market_cap_usd": None, "volume_24h_usd": sum((p.get("volume") or {}).get("h24") or 0 for p in pairs),
            "provider": "DexScreener", "fx_converted": len(prices) > 1,
            "fx_note": "Converted from USD using ECB reference rates (Frankfurter)." if len(prices) > 1 else None,
            "pair_count": len(pairs)}
    summary = f"{data['name']} priced from {len(pairs)} DEX pair(s): USD {usd}." + (" Converted to other currencies via ECB rates." if len(prices) > 1 else "")
    if claims.get("claimed_price") is None:
        summary += " Offer price not detected — add it to run the price check."
    return result("market", "DexScreener", "verified", summary, data=data)


async def _binance(claims: dict, s) -> dict:
    """By symbol only (majors actually listed on Binance). An unknown symbol is NOT a
    'not listed anywhere' answer - it just means Binance cannot help here."""
    sym = re.sub(r"[^A-Z0-9]", "", (claims.get("asset_symbol") or "").upper())
    if not sym:
        raise SourceError("No token symbol to query on the exchange.", "error")
    try:
        d = await cached(f"bn:{sym}", s.cache_ttl, lambda: request_json("GET", "https://api.binance.com/api/v3/ticker/price", params={"symbol": sym + "USDT"}, timeout=s.http_timeout))
    except SourceError as e:
        if e.kind in ("not_found", "http"):
            raise SourceError(f"{sym}USDT is not traded on this exchange.", "not_found")
        raise
    usd = _f((d or {}).get("price"))
    if usd is None:
        raise SourceError("The exchange returned no price.", "malformed")
    prices = await _prices_from_usd(s, usd)
    data = {"id": None, "name": claims.get("asset_name"), "symbol": sym, "prices": prices,
            "market_cap_usd": None, "volume_24h_usd": None, "provider": "Binance", "fx_converted": len(prices) > 1,
            "fx_note": "Converted from USD using ECB reference rates (Frankfurter)." if len(prices) > 1 else None}
    summary = f"{sym} priced at USD {usd} on the exchange." + (" Converted to other currencies via ECB rates." if len(prices) > 1 else "")
    if claims.get("claimed_price") is None:
        summary += " Offer price not detected — add it to run the price check."
    return result("market", "Binance", "verified", summary, data=data)


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


async def check_market(claims: dict, s) -> dict:
    if not (claims.get("contract_address") or claims.get("asset_name") or claims.get("asset_id")):
        return result("market", SRC, "not_applicable", "No asset name or contract provided.", reason="No asset name or contract address provided.")
    provs: list[tuple[str, object]] = [("CoinGecko", _coingecko)]
    if claims.get("contract_address") and claims.get("chain") in CHAINS:
        provs.append(("DexScreener", _dexscreener))
    if claims.get("asset_symbol"):
        provs.append(("Binance", _binance))
    return await run_chain("market", provs, claims, s, stop_on=lambda r: r["status"] == "verified")
