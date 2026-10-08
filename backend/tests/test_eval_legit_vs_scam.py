"""Evaluation suite testing legitimate corporate offers vs scam campaigns vs inconclusive text."""
from __future__ import annotations
import asyncio
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.analysis import run_analysis
from app.config import get_settings

S = get_settings()

EVAL_CASES = [
    {
        "id": "legit-google-cloud",
        "category": "Legitimate",
        "title": "Google Cloud Promo",
        "input": {
            "text": "Official Google Cloud offer: Get $300 in free cloud credits when you sign up with your business email. Satisfaction guaranteed.",
            "url": "https://cloud.google.com",
            "mode": "live"
        },
        "expected_outcome": "verified-legit",
        "max_risk_score": 20
    },
    {
        "id": "legit-apple-cashback",
        "category": "Legitimate",
        "title": "Apple Store Promo",
        "input": {
            "text": "Apple Store Promotion: Get 5% instant cashback on all MacBook Pro purchases with Apple Card. Limited time offer ends Sunday.",
            "url": "https://apple.com/shop",
            "mode": "live"
        },
        "expected_outcome": "verified-legit",
        "max_risk_score": 20
    },
    {
        "id": "legit-coinbase-reward",
        "category": "Legitimate",
        "title": "Coinbase Learning Reward",
        "input": {
            "text": "Earn crypto while learning. Join Coinbase and earn $10 worth of Bitcoin after completing your first educational quest.",
            "url": "https://coinbase.com/learning-rewards",
            "mode": "live"
        },
        "expected_outcome": "verified-legit",
        "max_risk_score": 20
    },
    {
        "id": "legit-stripe-payments",
        "category": "Legitimate",
        "title": "Stripe Payments",
        "input": {
            "text": "Stripe Payments: Accept credit cards, debit cards, and mobile wallets globally with developer-friendly APIs.",
            "url": "https://stripe.com/payments",
            "mode": "live"
        },
        "expected_outcome": "verified-legit",
        "max_risk_score": 20
    },
    {
        "id": "scam-google-impersonation",
        "category": "Scam / Phishing",
        "title": "Google Brand Impersonation",
        "input": {
            "text": "Google Hiring Department: You are selected for Remote Assistant job! Earn $5,000/week. Visit our portal now.",
            "url": "https://google-career-portal.xyz/apply",
            "mode": "live"
        },
        "expected_outcome": "suspicious",
        "min_risk_score": 40
    },
    {
        "id": "scam-ponzi-guaranteed-100x",
        "category": "Scam / Ponzi",
        "title": "Guaranteed 100x Ponzi",
        "input": {
            "text": "Guaranteed 100x profit in 7 days! Invest 1 BTC now and receive 100 BTC back with zero risk. Hurry, only 2 slots left!",
            "url": "https://double-bitcoin-fast.xyz",
            "mode": "live"
        },
        "expected_outcome": "suspicious",
        "min_risk_score": 50
    },
    {
        "id": "scam-private-key-thief",
        "category": "Scam / Credential Theft",
        "title": "Seed Phrase / Key Theft",
        "input": {
            "text": "Coinbase Security Notice: Suspicious activity detected. To unlock your account, verify your 12 words seed phrase immediately.",
            "url": "https://coinbase-verify-login.net",
            "mode": "live"
        },
        "expected_outcome": "suspicious",
        "min_risk_score": 50
    },
    {
        "id": "inconclusive-vague",
        "category": "Inconclusive",
        "title": "Vague Unverified Message",
        "input": {
            "text": "Hey check out this new project I heard about from a colleague.",
            "url": "",
            "mode": "live"
        },
        "expected_outcome": "could-not-verify",
        "max_risk_score": 25
    }
]


class EvalLegitVsScam(unittest.TestCase):
    def test_eval_suite(self):
        async def run_single(case):
            res = await run_analysis(case["input"], S)
            risk = res["risk"]
            conf = res["confidence"]
            findings = [f["title"] for f in res["findings"] if f["points"] > 0]
            passed = risk.get("outcome") == case["expected_outcome"] and (
                risk["score"] <= case["max_risk_score"] if "max_risk_score" in case else risk["score"] >= case["min_risk_score"]
            )
            return {
                "id": case["id"],
                "category": case["category"],
                "title": case["title"],
                "outcome": risk.get("outcome"),
                "score": risk["score"],
                "level": risk["level"],
                "confidence": conf["level"],
                "expected": case["expected_outcome"],
                "passed": passed,
                "findings": findings
            }

        async def run_all():
            return await asyncio.gather(*[run_single(case) for case in EVAL_CASES])

        results = asyncio.run(run_all())
        import sys
        print("\n" + "=" * 105)
        print(f"{'Category':<22} | {'Test Case':<26} | {'Outcome':<18} | {'Score':<6} | {'Conf':<6} | {'Status':<6}")
        print("-" * 105)
        for r in results:
            pass_str = "PASS" if r["passed"] else "FAIL"
            print(f"{r['category']:<22} | {r['title']:<26} | {r['outcome']:<18} | {r['score']:<6} | {r['confidence']:<6} | {pass_str:<6}")
        print("=" * 105 + "\n")
        sys.stdout.flush()
        for r in results:
            self.assertTrue(r["passed"], f"Test {r['title']} failed: got outcome={r['outcome']}, score={r['score']}, expected={r['expected']}")


if __name__ == "__main__":
    unittest.main()
