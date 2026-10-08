"""End-to-end verification script for P2P bait price input."""
import json
import sys
import urllib.request
import urllib.error

sys.stdout.reconfigure(encoding="utf-8")

def main():
    url = "http://127.0.0.1:8000/api/analyze"
    payload = {
        "text": "My friend is selling her Bitcoin for ₹30,000.",
        "mode": "live"
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.read().decode('utf-8')}")
        return
    except Exception as e:
        print(f"Connection error: {e}")
        return

    print("=" * 60)
    print("LIVE PIPELINE RESULT")
    print("=" * 60)
    print(f"Input text: '{payload['text']}'")
    print(f"Mode: {data.get('mode')}")
    print()

    claims = data.get("claims", {})
    print("--- 1. CLAIMS ---")
    print(f"Asset Name: {claims.get('asset_name')}")
    print(f"Asset Symbol: {claims.get('asset_symbol')}")
    print(f"Claimed Price: {claims.get('claimed_price')}")
    print(f"Quoted Currency: {claims.get('quoted_currency')}")
    print(f"Quantity: {claims.get('quantity')}")
    print(f"Quantity Assumed: {claims.get('quantity_assumed')}")
    print(f"Price Verbatim: {claims.get('price_verbatim')}")
    print()

    checks_raw = data.get("checks", [])
    if isinstance(checks_raw, list):
        checks = {c.get("check_id"): c for c in checks_raw}
    else:
        checks = checks_raw
    market = checks.get("market", {})
    print("--- 2. MARKET CHECK ---")
    print(f"Status: {market.get('status')}")
    print(f"Source: {market.get('source')}")
    market_data = market.get("data", {})
    print(f"Prices: {market_data.get('prices')}")
    print(f"Fx Used: {market_data.get('fx_used')}")
    print(f"Summary: {market.get('summary')}")
    print()

    risk = data.get("risk", {})
    conf = data.get("confidence", {})
    cov = data.get("coverage", {})
    print("--- 3. RISK & CONFIDENCE ---")
    print(f"Risk Score: {risk.get('score')} / 100 (raw: {risk.get('raw_points')})")
    print(f"Risk Level: {risk.get('level')} (key: {risk.get('level_key')})")
    print(f"Outcome: {risk.get('outcome')} ('{risk.get('outcome_label')}')")
    print(f"Confidence: {conf.get('level')} ({conf.get('score')}/100)")
    print(f"Coverage: {cov.get('available')}/{cov.get('total')} checks available")
    print(f"Confidence Reasons: {conf.get('reasons')}")
    print()

    findings = data.get("findings", [])
    print(f"--- 4. FINDINGS ({len(findings)}) ---")
    for idx, f in enumerate(findings, 1):
        print(f"[{idx}] Rule: {f.get('rule_id')} | Points: {f.get('points')} | Severity: {f.get('severity')}")
        print(f"    Title: {f.get('title')}")
        print(f"    Observed: {f.get('observed')}")
        print(f"    Evidence: {f.get('evidence')}")
        print(f"    Source: {f.get('source')}")
    print()

    summary = data.get("summary", {})
    print("--- 5. SUMMARY ---")
    print(f"Method: {summary.get('method')}")
    print(f"Text:\n{summary.get('text')}")
    print("=" * 60)

if __name__ == "__main__":
    main()
