"""Verification script for the full evaluation QUARTET:
1. Nova specimen: unverified entity, asset NYLP, not-listed finding, no guaranteed finding, inconclusive verdict.
2. Metabot specimen: no price finding (fabricated price silenced).
3. P2P Bitcoin specimen: price-bait finding present (25 pts, Moderate Risk).
4. Nova specimen + user token 'botchain': discrepancy note generated, real asset NYLP kept for market lookup, no verified status, inconclusive verdict.
"""
import json
import sys
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding="utf-8")

def analyze(payload: dict) -> dict:
    url = "http://127.0.0.1:8000/api/analyze"
    if "mode" not in payload:
        payload["mode"] = "live"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))

def main():
    print("=" * 70)
    print("EVALUATION QUARTET VERIFICATION")
    print("=" * 70)

    # 1. NOVA SPECIMEN (PLAIN)
    print("\n[SPECIMEN 1: NOVA YIELD POOL (PLAIN)]")
    nova_text = (
        "NOVA YIELD POOL — Community Round. "
        "Expected yield: around 1.5–2% monthly, variable, depends on pool performance. "
        "Not a guarantee. All contributions are convertible into the NYLP token at launch. "
        "Contribution range: 50 to 2,000 USDT. "
        "Coordination happens in the Telegram group."
    )
    r_nova = analyze({"text": nova_text})
    claims_nova = r_nova.get("claims", {})
    risk_nova = r_nova.get("risk", {})
    findings_nova = r_nova.get("findings", [])
    summary_nova = r_nova.get("summary", {})

    print(f"Asset Extracted: {claims_nova.get('asset_name')} (symbol: {claims_nova.get('asset_symbol')})")
    print(f"Quoted / Payment Currency: {claims_nova.get('quoted_currency')}")
    print(f"Guaranteed Language Flag: {claims_nova.get('guaranteed_language')}")
    print(f"Risk Score: {risk_nova.get('score')} | Level: {risk_nova.get('level')} | Key: {risk_nova.get('level_key')}")
    print(f"Outcome: {risk_nova.get('outcome')} ('{risk_nova.get('outcome_label')}')")
    print(f"Insufficient Evidence: {risk_nova.get('insufficient_evidence')}")
    print(f"Findings ({len(findings_nova)}): {[f.get('rule_id') for f in findings_nova]}")
    for f in findings_nova:
        print(f"  -> {f.get('rule_id')}: {f.get('title')} (+{f.get('points')})")
    print(f"Summary (Method: {summary_nova.get('method')}):\n{summary_nova.get('text')}")

    assert claims_nova.get("asset_symbol") == "NYLP", f"Expected NYLP asset, got {claims_nova.get('asset_symbol')}"
    assert claims_nova.get("guaranteed_language") is False, "Expected guaranteed_language False"
    assert risk_nova.get("outcome") == "could-not-verify", f"Expected could-not-verify, got {risk_nova.get('outcome')}"
    assert risk_nova.get("level") == "Could Not Verify", f"Expected 'Could Not Verify', got {risk_nova.get('level')}"
    assert any(f.get("rule_id") == "ASSET_NOT_FOUND" for f in findings_nova), "Expected ASSET_NOT_FOUND finding"
    assert not any(f.get("rule_id") == "GUARANTEED_RETURNS" for f in findings_nova), "GUARANTEED_RETURNS must not fire"
    print(">>> SPECIMEN 1 PASSED!")

    # 2. METABOT SPECIMEN
    print("\n[SPECIMEN 2: METABOT PACKAGE TABLE]")
    metabot_text = (
        "Metabot AI Trading Packages:\n"
        "Bronze package costs $1,000 with 10% monthly yield.\n"
        "Silver package costs $5,000 with 20% monthly yield.\n"
        "Gold package costs $10,000 with 30% monthly yield.\n"
        "Invite your friends to earn 15% referral commission!"
    )
    r_metabot = analyze({"text": metabot_text})
    findings_meta = r_metabot.get("findings", [])
    price_findings_meta = [f for f in findings_meta if "PRICE" in f.get("rule_id", "")]
    print(f"Findings: {[f.get('rule_id') for f in findings_meta]}")
    print(f"Price Findings Count: {len(price_findings_meta)}")
    assert len(price_findings_meta) == 0, f"Metabot must have NO price findings, got {price_findings_meta}"
    print(">>> SPECIMEN 2 PASSED!")

    # 3. P2P BITCOIN BAIT PRICE SPECIMEN
    print("\n[SPECIMEN 3: P2P BITCOIN BAIT PRICE]")
    p2p_text = "My friend is selling her Bitcoin for ₹30,000."
    r_p2p = analyze({"text": p2p_text})
    risk_p2p = r_p2p.get("risk", {})
    findings_p2p = r_p2p.get("findings", [])
    price_bait_finding = next((f for f in findings_p2p if f.get("rule_id") == "PRICE_BAIT_UNSTATED_QUANTITY"), None)
    print(f"Risk Score: {risk_p2p.get('score')} | Level: {risk_p2p.get('level')}")
    print(f"Price Bait Finding Present: {price_bait_finding is not None}")
    if price_bait_finding:
        print(f"  -> Title: {price_bait_finding.get('title')} (+{price_bait_finding.get('points')})")
        print(f"     Observed: {price_bait_finding.get('observed')}")
    assert price_bait_finding is not None, "PRICE_BAIT_UNSTATED_QUANTITY finding must fire"
    assert risk_p2p.get("score") == 25, f"Expected score 25, got {risk_p2p.get('score')}"
    assert risk_p2p.get("level") == "Moderate Risk", f"Expected Moderate Risk, got {risk_p2p.get('level')}"
    print(">>> SPECIMEN 3 PASSED!")

    # 4. NOVA SPECIMEN + USER TOKEN "BOTCHAIN"
    print("\n[SPECIMEN 4: NOVA YIELD POOL + TOKEN 'BOTCHAIN']")
    r_nova_bot = analyze({"text": nova_text, "token_name": "botchain"})
    claims_bot = r_nova_bot.get("claims", {})
    risk_bot = r_nova_bot.get("risk", {})
    checks_bot = r_nova_bot.get("checks", [])
    findings_bot = r_nova_bot.get("findings", [])
    summary_bot = r_nova_bot.get("summary", {})
    extraction_bot = r_nova_bot.get("extraction", {})

    print(f"Discrepancy Note in Claims: {claims_bot.get('discrepancy_note')}")
    print(f"Extraction Notes: {extraction_bot.get('notes')}")
    print(f"Real Asset Retained: {claims_bot.get('asset_name')} (symbol: {claims_bot.get('asset_symbol')})")
    print(f"User Token: {claims_bot.get('user_token')}")
    print(f"Risk Score: {risk_bot.get('score')} | Level: {risk_bot.get('level')}")
    print(f"Outcome: {risk_bot.get('outcome')} ('{risk_bot.get('outcome_label')}')")
    print(f"Insufficient Evidence: {risk_bot.get('insufficient_evidence')}")

    mkt_check_bot = next((c for c in checks_bot if c.get("check_id") == "market"), {})
    print(f"Market Check Status: {mkt_check_bot.get('status')} | Source: {mkt_check_bot.get('source')}")

    print(f"Summary Text:\n{summary_bot.get('text')}")

    assert claims_bot.get("discrepancy_note") is not None, "discrepancy_note must be set"
    assert "botchain" in claims_bot.get("discrepancy_note").lower(), "discrepancy note must mention user token"
    assert "nylp" in claims_bot.get("discrepancy_note").lower(), "discrepancy note must mention extracted token"
    assert claims_bot.get("asset_symbol") == "NYLP", "Real asset NYLP must be retained"
    assert risk_bot.get("outcome") == "could-not-verify", f"Expected could-not-verify, got {risk_bot.get('outcome')}"
    assert risk_bot.get("outcome_label") != "Likely Safe", "Outcome label must never be 'Likely Safe'"
    assert risk_bot.get("level") == "Could Not Verify", f"Expected 'Could Not Verify', got {risk_bot.get('level')}"
    assert summary_bot.get("text") and len(summary_bot.get("text")) > 50, "Summary must be present"
    print(">>> SPECIMEN 4 PASSED!")

    print("\n" + "=" * 70)
    print("ALL 4 SPECIMENS IN EVALUATION QUARTET VERIFIED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    main()
