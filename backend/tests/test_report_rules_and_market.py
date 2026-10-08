"""Unit tests verifying:
1. No rule fires without non-empty matched evidence string (e.g. empty "" in text bug fixed).
2. Market 3-state model (LISTED, NOT-LISTED, LOOKUP-FAILED):
   - LISTED (verified): 0 points for ASSET_NOT_FOUND.
   - NOT-LISTED (not_found): 12 points for ASSET_NOT_FOUND with non-empty evidence.
   - LOOKUP-FAILED (unavailable): 0 points for ASSET_NOT_FOUND, reason reported.
"""
from __future__ import annotations
import unittest
from app.extraction import heuristic_extract
from app.scoring import assess, r_guar, r_ref, r_urg, r_secret, r_not_found, r_returns
from app.sources.common import result


class TestReportRulesAndMarket(unittest.TestCase):
    def test_guaranteed_rule_never_fires_with_empty_phrase(self):
        # Case 1: Empty phrases dictionary or empty string
        claims = {"guaranteed_language": True, "phrases": {"guaranteed_language": ""}}
        self.assertIsNone(r_guar(claims, {}))

        claims2 = {"guaranteed_language": True, "phrases": {}}
        self.assertIsNone(r_guar(claims2, {}))

        claims3 = {"guaranteed_language": False, "phrases": {}}
        self.assertIsNone(r_guar(claims3, {}))

        # Case 2: Legitimate offer without guaranteed language
        extracted = heuristic_extract("Official Google Cloud offer: Get $300 in free cloud credits when you sign up. Satisfaction guaranteed.")
        # "Satisfaction guaranteed" is a retail guarantee and filtered out
        self.assertFalse(extracted.get("guaranteed_language"))
        self.assertIsNone(r_guar(extracted, {}))

        # Case 3: Legitimate trigger with actual non-empty phrase
        scam_claims = {"guaranteed_language": True, "phrases": {"guaranteed_language": "Guaranteed 100% safe return"}}
        finding = r_guar(scam_claims, {})
        self.assertIsNotNone(finding)
        self.assertEqual(finding["rule_id"], "GUARANTEED_RETURNS")
        self.assertEqual(finding["points"], 25)
        self.assertIn("Guaranteed 100% safe return", finding["observed"])
        self.assertTrue(bool(finding["evidence"].get("matched_text")))

    def test_referral_rule_never_fires_with_empty_phrase(self):
        claims = {"referral": True, "phrases": {"referral": ""}}
        self.assertIsNone(r_ref(claims, {}))

        claims2 = {"referral": True, "phrases": {"referral": "   "}}
        self.assertIsNone(r_ref(claims2, {}))

        claims3 = {"referral": True, "phrases": {"referral": "Refer 3 friends to earn 10%"}}
        finding = r_ref(claims3, {})
        self.assertIsNotNone(finding)
        self.assertEqual(finding["points"], 12)
        self.assertIn("Refer 3 friends", finding["observed"])

    def test_urgency_rule_never_fires_with_empty_phrase(self):
        claims = {"urgency": True, "phrases": {"urgency": ""}}
        self.assertIsNone(r_urg(claims, {}))

        claims2 = {"limited_time": True, "phrases": {"limited_time": "   "}}
        self.assertIsNone(r_urg(claims2, {}))

        claims3 = {"urgency": True, "phrases": {"urgency": "Hurry, only 2 slots left!"}}
        finding = r_urg(claims3, {})
        self.assertIsNotNone(finding)
        self.assertEqual(finding["points"], 10)
        self.assertIn("only 2 slots left", finding["observed"])

    def test_secret_rule_never_fires_with_empty_phrase(self):
        claims = {"requests_secrets": True, "phrases": {"requests_secrets": ""}}
        self.assertIsNone(r_secret(claims, {}))

        claims2 = {"requests_secrets": True, "phrases": {"requests_secrets": "send me your seed phrase"}}
        finding = r_secret(claims2, {})
        self.assertIsNotNone(finding)
        self.assertEqual(finding["points"], 40)
        self.assertIn("seed phrase", finding["observed"])

    def test_market_3_state_model(self):
        # 1. LISTED (status == "verified") -> 0 points
        ck_listed = {
            "market": result("market", "CoinGecko", "verified", "Bitcoin found. USD 65000.",
                             data={"id": "bitcoin", "prices": {"usd": 65000.0, "inr": 5400000.0}})
        }
        cl_listed = {"asset_name": "Bitcoin", "claimed_price": 65000.0, "quoted_currency": "USD", "phrases": {}}
        finding_listed = r_not_found(cl_listed, ck_listed)
        self.assertIsNone(finding_listed)
        res_listed = assess(cl_listed, ck_listed)
        self.assertEqual(res_listed["risk"]["score"], 0)
        self.assertNotIn("ASSET_NOT_FOUND", [f["rule_id"] for f in res_listed["findings"]])

        # 2. NOT-LISTED (status == "not_found") -> 12 points with non-empty evidence
        ck_not_found = {
            "market": result("market", "CoinGecko", "not_found", "The asset is not listed on CoinGecko.",
                             data={"queried": "UnknownScamToken", "provider": "CoinGecko"})
        }
        cl_not_found = {"asset_name": "UnknownScamToken", "phrases": {}}
        finding_not_found = r_not_found(cl_not_found, ck_not_found)
        self.assertIsNotNone(finding_not_found)
        self.assertEqual(finding_not_found["rule_id"], "ASSET_NOT_FOUND")
        self.assertEqual(finding_not_found["points"], 12)
        self.assertEqual(finding_not_found["status"], "not_found")
        self.assertIn("UnknownScamToken", finding_not_found["observed"])
        self.assertEqual(finding_not_found["evidence"]["status"], "NOT-LISTED")
        self.assertEqual(finding_not_found["evidence"]["queried_asset"], "UnknownScamToken")

        res_not_found = assess(cl_not_found, ck_not_found)
        self.assertEqual(res_not_found["risk"]["score"], 12)

        # 3. LOOKUP-FAILED (status == "unavailable") -> 0 points (never scored as not listed)
        ck_failed = {
            "market": result("market", "CoinGecko", "unavailable", "Verification unavailable.",
                             reason="Rate limit reached for api.coingecko.com (HTTP 429).")
        }
        cl_failed = {"asset_name": "Bitcoin", "phrases": {}}
        finding_failed = r_not_found(cl_failed, ck_failed)
        self.assertIsNone(finding_failed)  # 0 points!

        res_failed = assess(cl_failed, ck_failed)
        self.assertEqual(res_failed["risk"]["score"], 0)  # Rate-limited / failed lookup adds 0 points!
        self.assertNotIn("ASSET_NOT_FOUND", [f["rule_id"] for f in res_failed["findings"]])
        self.assertEqual(len(res_failed["coverage"]["unavailable"]), 1)
        self.assertIn("Rate limit", res_failed["coverage"]["unavailable"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
