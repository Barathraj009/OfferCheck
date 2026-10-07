"""DEMO DATA. Everything here is simulated for demonstration and is always flagged `demo: true`.
It is NEVER live verification. Values are invented round numbers, not real market/contract data."""
from __future__ import annotations
from .sources.common import result

SIM = "Simulated {} response (demo)"


def _r(cid, src, status, summary, data=None, reason=None):
    return result(cid, SIM.format(src), status, summary, data=data, reason=reason, demo=True)


SCENARIOS = {
    "cheap-bitcoin": {
        "title": "Demo A - 'Cheap Bitcoin' with urgency",
        "blurb": "A seller offers Bitcoin far below market and pressures you to pay fast.",
        "inputs": {"text": "Bitcoin for ₹32 lakh only. Market is ₹54 lakh but I need cash urgently. Pay within 2 hours - only 2 slots left. Refer a friend and get ₹10,000 commission.",
                   "url": "https://btc-flash-sale.example", "token_name": "", "contract_address": "", "chain": ""},
        "checks": {
            "market": lambda: _r("market", "CoinGecko", "verified", "Bitcoin found (demo prices).", {"id": "bitcoin", "name": "Bitcoin", "symbol": "BTC", "prices": {"usd": 65000, "inr": 5400000, "eur": 60000, "gbp": 51000}, "market_cap_usd": 1.28e12, "volume_24h_usd": 2.5e10}),
            "domain": lambda: _r("domain", "RDAP", "verified", "Registered 4 days ago.", {"domain": "btc-flash-sale.example", "registered": "demo-date", "age_days": 4}),
            "webSafety": lambda: _r("webSafety", "Safe Browsing", "unavailable", "Unavailable.", reason="Not simulated in this scenario - shows how a missing check lowers confidence."),
        }},
    "suspicious-token": {
        "title": "Demo B - New token with risky contract",
        "blurb": "A newly launched token promises 10x and shows several dangerous contract indicators.",
        "inputs": {"text": "NEW LAUNCH: MoonRocket (MRKT) token on BNB Chain. Guaranteed 10x returns in 2 weeks! Buy now before the price jumps, only 24 hours left. Invite friends and earn 5% referral commission on every purchase.",
                   "url": "https://moonrocket-token.example", "token_name": "MoonRocket", "contract_address": "0x" + "de" * 20, "chain": "bsc"},
        "checks": {
            "market": lambda: _r("market", "CoinGecko", "not_found", "No exact match.", {"queried": "MoonRocket"}),
            "explorer": lambda: _r("explorer", "BscScan", "unavailable", "Unavailable.", reason="Rate limited (simulated) - shows partial verification."),
            "security": lambda: _r("security", "GoPlus Security", "verified", "Security scan completed.", {"honeypot": False, "cannot_sell_all": False, "mintable": True, "takeback_ownership": False, "owner_change_balance": True, "hidden_owner": False, "selfdestruct": False, "transfer_pausable": False, "blacklist": False, "open_source": False, "sell_tax_pct": 35.0, "buy_tax_pct": 5.0, "holder_count": 212, "top_holder_pct": 42.0, "top10_pct": 81.0}),
            "liquidity": lambda: _r("liquidity", "DexScreener", "verified", "1 pair, $3,200 liquidity.", {"pair_count": 1, "total_liquidity_usd": 3200, "volume_24h_usd": 1800, "oldest_pair_age_days": 3, "buys_24h": 40, "sells_24h": 6}),
            "domain": lambda: _r("domain", "RDAP", "verified", "Registered 6 days ago.", {"domain": "moonrocket-token.example", "registered": "demo-date", "age_days": 6}),
            "webSafety": lambda: _r("webSafety", "Safe Browsing", "verified", "No match.", {"threats": []}),
        }},
    "normal-offer": {
        "title": "Demo C - Ordinary-looking offer",
        "blurb": "A sale of Ethereum at about the market rate with no pressure or promised profit.",
        "inputs": {"text": "Selling 0.5 ETH for ₹1,33,000. Pay through the exchange escrow, no rush, take your time to verify.",
                   "url": "https://trusted-exchange.example", "token_name": "", "contract_address": "", "chain": ""},
        "checks": {
            "market": lambda: _r("market", "CoinGecko", "verified", "Ethereum found (demo prices).", {"id": "ethereum", "name": "Ethereum", "symbol": "ETH", "prices": {"usd": 3200, "inr": 268000, "eur": 2950, "gbp": 2500}, "market_cap_usd": 3.8e11, "volume_24h_usd": 1.4e10}),
            "domain": lambda: _r("domain", "RDAP", "verified", "Registered 3,900 days ago.", {"domain": "trusted-exchange.example", "registered": "demo-date", "age_days": 3900}),
            "webSafety": lambda: _r("webSafety", "Safe Browsing", "verified", "No match.", {"threats": []}),
        }},
    "too-vague": {
        "title": "Demo D - Too little to verify",
        "blurb": "A vague message with no asset, address or link: shows an honest 'not enough evidence' report.",
        "inputs": {"text": "Hey! I have an amazing crypto deal for you. Message me on WhatsApp for the details.",
                   "url": "", "token_name": "", "contract_address": "", "chain": ""},
        "checks": {},  # nothing to check: every external check is not_applicable -> insufficient evidence
    },
    "partial-verification": {
        "title": "Demo E - Partial verification",
        "blurb": "Some sources answer, others are down: scoring continues on real evidence while confidence drops.",
        "inputs": {"text": "NEW LISTING: MoonVault (MVT) token on BNB Chain. 5x returns in 7 days - limited offer ends today, buy before it lists!",
                   "url": "https://moonvault-offer.example", "token_name": "MoonVault", "contract_address": "0x" + "ab" * 20, "chain": "bsc"},
        "checks": {
            "market": lambda: _r("market", "CoinGecko", "unavailable", "Unavailable.", reason="Rate limit reached (simulated) - the free market-data source is temporarily unavailable."),
            "explorer": lambda: _r("explorer", "BscScan", "unavailable", "Unavailable.", reason="The verification service did not respond in time (simulated)."),
            "security": lambda: _r("security", "GoPlus Security", "verified", "Security scan completed.", {"honeypot": False, "cannot_sell_all": False, "mintable": False, "takeback_ownership": False, "owner_change_balance": False, "hidden_owner": False, "selfdestruct": False, "transfer_pausable": False, "blacklist": False, "open_source": True, "sell_tax_pct": 5.0, "buy_tax_pct": 5.0, "holder_count": 890, "top_holder_pct": 25.0, "top10_pct": 55.0}),
            "liquidity": lambda: _r("liquidity", "DexScreener", "verified", "2 pairs, $60,000 liquidity.", {"pair_count": 2, "total_liquidity_usd": 60000, "volume_24h_usd": 12000, "oldest_pair_age_days": 14, "buys_24h": 90, "sells_24h": 40}),
            "domain": lambda: _r("domain", "RDAP", "verified", "Registered 12 days ago.", {"domain": "moonvault-offer.example", "registered": "demo-date", "age_days": 12}),
            "webSafety": lambda: _r("webSafety", "Threat feed", "unavailable", "Unavailable.", reason="The threat feed could not be loaded (simulated outage)."),
        }},
}


def list_scenarios() -> list[dict]:
    return [{"id": k, "title": v["title"], "blurb": v["blurb"], "inputs": v["inputs"]} for k, v in SCENARIOS.items()]


def demo_check(scenario: str | None, cid: str) -> dict:
    fx = SCENARIOS.get(scenario or "", {}).get("checks", {}).get(cid)
    if fx:
        return fx()
    why = "Demo mode has no live data for your own input. Choose a sample scenario, or switch to Live mode." if not scenario else "Not simulated in this demo scenario."
    return result(cid, "Demo mode", "unavailable", "Not verified.", reason=why, demo=True)
