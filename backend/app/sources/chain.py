"""Contract verification, GoPlus security and DexScreener liquidity adapters.

Contract verification is layered for zero-cost operation:
  1. Sourcify v2 (keyless) - exact/partial source match from a public repository
  2. Etherscan V2 (optional free key) - source + creation info when configured
  3. Public RPC eth_getCode (keyless) - proves whether contract bytecode exists at all
A provider that cannot answer raises SourceError and the next one is tried.
Sourcify 404 only means "not in Sourcify" - it is never reported as "source unverified";
source_verified stays None unless a provider actually establishes it."""
from __future__ import annotations
import time
from ..validators import CHAINS
from .base import run_chain
from .common import SourceError, cached, request_json, result


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _b(v):
    """GoPlus flags are "0"/"1" strings; None means the field was absent (unknown)."""
    return None if v in (None, "") else str(v) == "1"


# Keyless public RPC endpoints per chain, tried in order (availability varies by region).
RPC_URLS = {
    "ethereum": ["https://ethereum-rpc.publicnode.com", "https://1rpc.io/eth"],
    "bsc": ["https://bsc-rpc.publicnode.com", "https://bsc-dataseed.binance.org"],
    "polygon": ["https://polygon-bor-rpc.publicnode.com", "https://polygon-rpc.com"],
    "arbitrum": ["https://arb1.arbitrum.io/rpc", "https://1rpc.io/arb"],
    "base": ["https://mainnet.base.org", "https://base-rpc.publicnode.com"],
}


async def _rpc_code(chain_key: str, addr: str, s) -> tuple[bool, int]:
    """eth_getCode across 2 public endpoints. Returns (has_bytecode, byte_length).
    Raises SourceError when no endpoint answers."""
    body = {"jsonrpc": "2.0", "id": 1, "method": "eth_getCode", "params": [addr, "latest"]}
    errs = []
    for url in RPC_URLS[chain_key]:
        try:
            d = await request_json("POST", url, json=body, timeout=max(4.0, s.http_timeout))
        except SourceError as e:
            errs.append(e.reason)
            continue
        if not isinstance(d, dict) or "result" not in d:
            errs.append("malformed RPC response")
            continue
        code = d.get("result") or "0x"
        if not isinstance(code, str) or not code.startswith("0x"):
            errs.append("malformed RPC response")
            continue
        has = len(code) > 3  # "0x" or "0x0" = no code (EOA / empty account)
        return has, (len(code) - 2) // 2
    raise SourceError("No public blockchain RPC endpoint responded.", "network" if errs else "error")


async def _sourcify(claims: dict, s) -> dict:
    """Layer 1 - Sourcify v2 (keyless). Confirms source verification when it has the contract."""
    chain, addr = CHAINS[claims["chain"]], claims["contract_address"]
    key = f"sourcify:{chain['id']}:{addr}"
    try:
        d = await cached(key, s.cache_ttl, lambda: request_json(
            "GET", f"https://sourcify.dev/server/v2/contract/{chain['id']}/{addr}", timeout=s.http_timeout))
    except SourceError as e:
        if e.kind == "not_found":
            raise SourceError("This contract is not in Sourcify's public repository.", "not_found")
        raise
    match = d.get("match") or d.get("runtimeMatch")
    if match not in ("exact_match", "match"):
        raise SourceError("Sourcify has no verification match for this contract.", "not_found")
    data = {"source_verified": True, "provider": "Sourcify", "match_type": match,
            "verified_at": d.get("verifiedAt"), "contract_exists": True,
            "contract_name": None, "compiler": None, "is_proxy": None, "creator": None, "creation_tx": None}
    label = "exact match" if match == "exact_match" else "partial match"
    return result("explorer", "Sourcify", "verified", f"Contract source verified on Sourcify ({label}).", data=data)


async def _etherscan(claims: dict, s) -> dict:
    """Layer 2 - Etherscan V2 multichain (optional free key): source + creation details."""
    chain = CHAINS[claims["chain"]]
    src = chain["explorer"]
    if not s.etherscan_api_key:
        raise SourceError("No ETHERSCAN_API_KEY configured.", "no_key")
    base = {"chainid": chain["id"], "module": "contract", "apikey": s.etherscan_api_key}
    addr = claims["contract_address"]
    key = f"scan:{chain['id']}:{addr}"

    async def fetch():
        a = await request_json("GET", "https://api.etherscan.io/v2/api", params={**base, "action": "getsourcecode", "address": addr}, timeout=s.http_timeout)
        b = None
        try:
            b = await request_json("GET", "https://api.etherscan.io/v2/api", params={**base, "action": "getcontractcreation", "contractaddresses": addr}, timeout=s.http_timeout)
        except SourceError:
            pass  # creation info is a bonus; do not fail the whole check
        return a, b

    a, b = await cached(key, s.cache_ttl, fetch)
    if str(a.get("status")) != "1" or not isinstance(a.get("result"), list) or not a["result"]:
        raise SourceError(f"{src} replied: {str(a.get('result') or a.get('message'))[:140]}", "http")
    r0 = a["result"][0]
    verified = bool((r0.get("SourceCode") or "").strip())
    creation = (b or {}).get("result") if b and isinstance(b.get("result"), list) and b["result"] else None
    data = {"source_verified": verified, "provider": src, "contract_name": r0.get("ContractName") or None,
            "compiler": r0.get("CompilerVersion") or None, "is_proxy": r0.get("Proxy") == "1",
            "creator": creation[0].get("contractCreator") if creation else None,
            "creation_tx": creation[0].get("txHash") if creation else None, "match_type": None,
            "verified_at": None, "contract_exists": None}
    if verified:
        return result("explorer", src, "verified", "Contract source is verified.", data=data)
    # Unverified on the explorer: distinguish "hidden code" from "no code at all" (an EOA
    # address has no contract, so claiming hidden source code would be a false signal).
    try:
        has, nbytes = await _rpc_code(claims["chain"], addr, s)
    except SourceError:
        has, nbytes = None, None
    if has is False:
        return result("explorer", src, "verified",
                      "This address has no contract on-chain (it is a plain wallet address, not a token contract).",
                      data={**data, "source_verified": None, "contract_exists": False, "bytecode_bytes": 0})
    return result("explorer", src, "verified", "Contract source is NOT verified.", data=data)


async def _rpc_exists(claims: dict, s) -> dict:
    """Layer 3 - public RPC: only establishes whether bytecode exists. Never infers
    source-verification status, creator or deployment facts from bytecode alone."""
    chain, addr = CHAINS[claims["chain"]], claims["contract_address"]
    has, nbytes = await _rpc_code(claims["chain"], addr, s)
    data = {"source_verified": None, "provider": "Public RPC", "contract_exists": has,
            "bytecode_bytes": nbytes if has else 0, "contract_name": None, "compiler": None,
            "is_proxy": None, "creator": None, "creation_tx": None, "match_type": None, "verified_at": None}
    if not has:
        return result("explorer", "Public RPC", "verified",
                      "No contract bytecode at this address on " + chain["label"] + " (it is a wallet/EOA address, not a token contract).", data=data)
    return result("explorer", "Public RPC", "verified",
                  f"Contract bytecode exists on {chain['label']} ({nbytes:,} bytes). Source-code verification status could not be established with the free sources available.",
                  data=data)


async def check_explorer(claims: dict, s) -> dict:
    return await run_chain("explorer", [("Sourcify", _sourcify), (CHAINS[claims["chain"]]["explorer"], _etherscan),
                                        ("Public RPC", _rpc_exists)], claims, s)


async def check_security(claims: dict, s) -> dict:
    chain, addr = CHAINS[claims["chain"]], claims["contract_address"]
    d = await cached(f"gp:{chain['id']}:{addr}", s.cache_ttl, lambda: request_json("GET", f"https://api.gopluslabs.io/api/v1/token_security/{chain['id']}", params={"contract_addresses": addr}, timeout=s.http_timeout))
    if d.get("code") not in (1, "1"):
        raise SourceError(f"GoPlus replied: {str(d.get('message'))[:120]}", "http")
    t = (d.get("result") or {}).get(addr.lower())
    if not t:
        return result("security", "GoPlus Security", "not_found", "GoPlus has no security data for this contract.")
    holders = [h for h in (t.get("holders") or []) if not (_b(h.get("is_contract")) or _b(h.get("is_locked")))]
    pcts = [(_f(h.get("percent")) or 0) * 100 for h in holders]
    sell, buy = _f(t.get("sell_tax")), _f(t.get("buy_tax"))
    data = {"honeypot": _b(t.get("is_honeypot")), "cannot_sell_all": _b(t.get("cannot_sell_all")), "mintable": _b(t.get("is_mintable")),
            "takeback_ownership": _b(t.get("can_take_back_ownership")), "owner_change_balance": _b(t.get("owner_change_balance")),
            "hidden_owner": _b(t.get("hidden_owner")), "selfdestruct": _b(t.get("selfdestruct")),
            "transfer_pausable": _b(t.get("transfer_pausable")), "blacklist": _b(t.get("is_blacklisted")),
            "open_source": _b(t.get("is_open_source")), "sell_tax_pct": sell * 100 if sell is not None else None,
            "buy_tax_pct": buy * 100 if buy is not None else None, "holder_count": t.get("holder_count"),
            "top_holder_pct": max(pcts) if pcts else None, "top10_pct": sum(sorted(pcts, reverse=True)[:10]) if pcts else None}
    return result("security", "GoPlus Security", "verified", "Security scan completed.", data=data)


async def fetch_dex_pairs(chain_key: str, addr: str, s) -> list[dict]:
    """Chain-scoped DexScreener pairs, cached under one shared key so the market and
    liquidity checks in the same analysis issue a single upstream request."""
    from ..validators import CHAINS as _CH
    chain = _CH[chain_key]

    async def fetch():
        # Chain-scoped endpoint: the generic one caps at 30 pairs across ALL chains,
        # so other chains' clones of the same address can crowd out the ones we need.
        d = await request_json("GET", f"https://api.dexscreener.com/token-pairs/v1/{chain['dex']}/{addr}", timeout=s.http_timeout)
        return [p for p in d if isinstance(p, dict) and p.get("chainId") == chain["dex"]] if isinstance(d, list) else []

    return await cached(f"dex:{chain['dex']}:{addr}", s.cache_ttl, fetch)


async def check_liquidity(claims: dict, s) -> dict:
    chain, addr = CHAINS[claims["chain"]], claims["contract_address"]
    pairs = await fetch_dex_pairs(claims["chain"], addr, s)
    if not pairs:
        return result("liquidity", "DexScreener", "not_found", "No trading pairs found on this network.")
    liq = sum((p.get("liquidity") or {}).get("usd") or 0 for p in pairs)
    vol = sum((p.get("volume") or {}).get("h24") or 0 for p in pairs)
    created = [p["pairCreatedAt"] for p in pairs if p.get("pairCreatedAt")]
    tx = [(p.get("txns") or {}).get("h24") or {} for p in pairs]
    data = {"pair_count": len(pairs), "total_liquidity_usd": liq, "volume_24h_usd": vol,
            "oldest_pair_age_days": int((time.time() * 1000 - min(created)) / 86_400_000) if created else None,
            "buys_24h": sum(x.get("buys", 0) for x in tx), "sells_24h": sum(x.get("sells", 0) for x in tx)}
    return result("liquidity", "DexScreener", "verified", f"{len(pairs)} pair(s), ${liq:,.0f} liquidity.", data=data)
