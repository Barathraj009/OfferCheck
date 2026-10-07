"""Plain-language output built from verified findings. Deterministic template first; optional LLM rewrite in analysis.py."""
from __future__ import annotations

CHECKLIST = [
    "Is the asset listed on a reputable market-data source such as CoinGecko or CoinMarketCap?",
    "Is the contract address exactly the one published by the official project (copy it from their official site, not from a chat message)?",
    "Is the contract source code verified on the block explorer?",
    "Can the token actually be sold? Try a very small test amount only if you understand the risks.",
    "Is there meaningful liquidity, and do trades happen in both directions (buys and sells)?",
    "Who controls the contract, and can they mint tokens, pause trading or change balances?",
    "Is there a credible, independent audit from a known firm that you can confirm on the firm's own site?",
    "Does the promised return make economic sense? Who is actually paying it?",
    "Is the seller rushing you or creating deadlines?",
    "Is the referral structure the main way you are expected to 'earn'?",
    "Is the website trustworthy: how old is it, and does it match the official project's address?",
]
NEVER_SHARE = "Never share your wallet seed phrase, private key, OTP, password, or recovery phrase with anyone."
DISCLAIMERS = [
    "This is a risk assessment and verification aid - not financial, legal, or investment advice.",
    "The score counts detected risk indicators in the available evidence. It is not a legal determination of fraud against any person or business.",
    "Scores reflect only the evidence that could be checked. Unavailable checks lower confidence.",
    "A legitimate new token may not yet be indexed by data providers; 'not found' is not proof of fraud.",
    "No automated system can guarantee fraud detection. Verify important claims independently before sending money.",
    "This tool does not accuse any person or business of wrongdoing.",
]
PHRASE = {
    "PRICE_BELOW_MARKET": "the price differs sharply from the observed market price", "ASSET_NOT_FOUND": "the asset could not be verified on a market-data source",
    "CONTRACT_UNVERIFIED": "the contract source code is not verified", "HONEYPOT": "selling the token may be blocked",
    "MINTABLE": "new tokens can be minted without limit", "OWNER_PRIVILEGES": "the owner has powerful admin capabilities",
    "SELL_TAX": "the sell tax is high", "LIQUIDITY": "liquidity is low or missing", "CONCENTRATION": "a few wallets hold much of the supply",
    "GUARANTEED_RETURNS": "the offer uses 'guaranteed' language", "UNREALISTIC_RETURNS": "the promised returns are unrealistically high",
    "REFERRAL_MODEL": "the offer pays for referrals", "URGENCY": "the seller applies time pressure",
    "SECRETS_REQUESTED": "secret credentials are mentioned", "NEW_DOMAIN": "the website was registered very recently",
    "MALICIOUS_SITE": "the website is on a danger list",
}


def template_summary(core: dict) -> str:
    r, c = core["risk"], core["confidence"]
    risky = [f for f in core["findings"] if f["points"] > 0][:4]
    if r["insufficient_evidence"]:
        return ("There was not enough verifiable information to assess this offer. No external checks could be completed and no warning signs were found in the text itself. "
                "That is NOT a sign of safety. Add a token name, contract address or website, or try again later. This is a risk assessment, not proof of anything.")
    parts = [f"This offer scored {r['score']} out of 100 ({r['level']}), with {c['level'].lower()} confidence."]
    if risky:
        parts.append("The main indicators found were: " + "; ".join(PHRASE.get(f["rule_id"], f["title"].lower()) for f in risky) + ".")
    else:
        parts.append("No warning indicators were found in the checks that could be completed.")
    cov = core["coverage"]
    if cov["unavailable"]:
        parts.append("Some checks could not be completed (" + ", ".join(u["label"].lower() for u in cov["unavailable"]) + "), so the picture is incomplete.")
    if r["score"] < 25 and c["level"] != "High":
        parts.append("A low score with limited verification does not mean the offer is safe.")
    parts.append("This is a risk assessment based on available evidence, not proof of fraud. Verify the items in the checklist before sending any money.")
    return " ".join(parts)


def compact_for_llm(core: dict) -> dict:
    """Only verified facts go to the LLM for explanation. No raw user text is included."""
    return {"risk_score": core["risk"]["score"], "risk_level": core["risk"]["level"], "confidence": core["confidence"]["level"],
            "confidence_reasons": core["confidence"]["reasons"],
            "findings": [{"title": f["title"], "points": f["points"], "observed": f["observed"], "source": f["source"], "status": f["status"]} for f in core["findings"]],
            "unavailable_checks": [u["label"] for u in core["coverage"]["unavailable"]], "conflicts": core["conflicts"]}
