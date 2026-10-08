"""Tests for Nova eval specimen bugs:
1. Negation detection (e.g. 'Not a guarantee', 'no guaranteed returns')
2. Offered asset referent extraction vs payment currencies (NYLP vs USDT)
3. Generic entity name guard (prevent generic words like Nova from being marked verified)
4. LLM summary prose unwrap & hallucinated quote stripping
5. Verdict gate requiring positive verification for Low Risk
6. Return range parsing (lower bound) and word-boundary snippets
"""
import unittest
from app.extraction import _snippet, heuristic_extract
from app.llm import _clean_summary_prose
from app.scoring import assess, r_not_found, r_price, r_guar
from app.sources.entity import check_entity_and_web
from app.sources.market import check_market


NOVA_SPECIMEN_TEXT = (
    "NOVA YIELD POOL — Community Round. "
    "Expected yield: around 1.5–2% monthly, variable, depends on pool performance. "
    "Not a guarantee. All contributions are convertible into the NYLP token at launch. "
    "Contribution range: 50 to 2,000 USDT. "
    "Coordination happens in the Telegram group."
)


class TestNovaEvalSpecimen(unittest.TestCase):

    def test_1_negation_guaranteed_language(self):
        # 1. Nova specimen text has "Not a guarantee." -> guaranteed_language must be False
        c_nova = heuristic_extract(NOVA_SPECIMEN_TEXT)
        self.assertFalse(c_nova["guaranteed_language"])
        self.assertNotIn("guaranteed_language", c_nova["phrases"])

        # 2. "no guaranteed returns" -> False
        c_no = heuristic_extract("Special pool with variable yield, no guaranteed returns.")
        self.assertFalse(c_no["guaranteed_language"])
        self.assertNotIn("guaranteed_language", c_no["phrases"])

        # 3. "returns are not guaranteed" -> False
        c_not = heuristic_extract("Earn up to 10%, but returns are not guaranteed.")
        self.assertFalse(c_not["guaranteed_language"])
        self.assertNotIn("guaranteed_language", c_not["phrases"])

        # 4. Positive case: "guaranteed 10x returns" -> True
        c_pos = heuristic_extract("Guaranteed 10x returns in 30 days!")
        self.assertTrue(c_pos["guaranteed_language"])
        self.assertIn("guaranteed_language", c_pos["phrases"])

    def test_2_offered_asset_referent_vs_payment_currency(self):
        # In Nova text, asset is NYLP ("convertible into the NYLP token") and contribution is in USDT
        c = heuristic_extract(NOVA_SPECIMEN_TEXT)
        self.assertEqual(c["asset_symbol"], "NYLP")
        self.assertEqual(c["asset_name"], "NYLP")
        self.assertIsNone(c["asset_id"])
        self.assertEqual(c["quoted_currency"], "USDT")

        # Market check query targeting NYLP results in not_found
        checks = {
            "market": {
                "check_id": "market",
                "status": "not_found",
                "source": "CoinGecko",
                "summary": "No exact match on CoinGecko.",
                "data": {"queried": "NYLP", "provider": "CoinGecko"}
            }
        }
        finding = r_not_found(c, checks)
        self.assertIsNotNone(finding)
        self.assertEqual(finding["rule_id"], "ASSET_NOT_FOUND")
        self.assertEqual(finding["points"], 12)
        self.assertEqual(finding["evidence"]["queried_asset"], "NYLP")
        self.assertEqual(finding["evidence"]["status"], "NOT-LISTED")

    def test_3_entity_generic_name_guard(self):
        import asyncio
        dummy_settings = type("S", (), {"http_timeout": 5.0, "cache_ttl": 60})()

        # "NOVA YIELD POOL" or "Nova" must not be verified as corporate entity
        c_nova = {"entity_name": "NOVA YIELD POOL"}
        res = asyncio.run(check_entity_and_web(c_nova, None, dummy_settings))
        self.assertIn(res["status"], ("unverified", "not_found", "not_applicable"))
        self.assertFalse(res["data"].get("entity_verified", False))

        # Authorized entity (Coinbase) with official domain match
        c_cb = {"entity_name": "Coinbase"}
        site_cb = {"domain": "coinbase.com"}
        res_cb = asyncio.run(check_entity_and_web(c_cb, site_cb, dummy_settings))
        self.assertEqual(res_cb["status"], "verified")
        self.assertTrue(res_cb["data"]["entity_verified"])
        self.assertTrue(res_cb["data"]["official_domain_match"])

    def test_4_llm_summary_unwrapping_and_quote_guard(self):
        # 1. Unwrap JSON output into prose
        raw_json_output = '{"Risk Assessment": "The offer for NYLP tokens has limited market data and requires independent verification."}'
        report_core = {
            "findings": [{"rule_id": "ASSET_NOT_FOUND", "title": "Listing on a market-data source", "observed": "Asset NYLP not listed"}],
            "claims": {"asset_name": "NYLP"}
        }
        clean = _clean_summary_prose(raw_json_output, report_core)
        self.assertIsNotNone(clean)
        self.assertFalse(clean.startswith("{"))
        self.assertIn("The offer for NYLP tokens", clean)

        # 2. Quoted phrase that was not in findings (e.g. hallucinated "risk-free")
        raw_with_hallucination = 'The offer promises "risk-free" profits through NYLP yield pool.'
        clean_hallucination = _clean_summary_prose(raw_with_hallucination, report_core)
        self.assertIsNotNone(clean_hallucination)
        self.assertNotIn("risk-free", clean_hallucination)

    def test_5_verdict_gate_inconclusive(self):
        # 1. Nova specimen has ASSET_NOT_FOUND (12 pts) and 0 positive verifications -> "Could Not Verify"
        claims = heuristic_extract(NOVA_SPECIMEN_TEXT)
        checks = {
            "market": {
                "check_id": "market",
                "status": "not_found",
                "source": "CoinGecko",
                "data": {"queried": "NYLP", "provider": "CoinGecko"}
            },
            "entity": {
                "check_id": "entity",
                "status": "unverified",
                "source": "Entity Directory",
                "data": {"entity": "NOVA YIELD POOL", "entity_verified": False, "official_domain_match": False}
            }
        }
        res = assess(claims, checks)
        self.assertEqual(res["risk"]["score"], 12)
        self.assertEqual(res["risk"]["outcome"], "could-not-verify")
        self.assertEqual(res["risk"]["level"], "Could Not Verify")
        self.assertEqual(res["risk"]["level_key"], "insufficient")
        self.assertTrue(res["risk"]["insufficient_evidence"])

        # 2. Coinbase on official domain with 0 pts -> "Low Risk" (Verified Legitimate)
        cb_claims = {"entity_name": "Coinbase"}
        cb_checks = {
            "entity": {
                "check_id": "entity",
                "status": "verified",
                "source": "Authoritative Entity Registry",
                "data": {"entity": "Coinbase", "entity_verified": True, "official_domain_match": True}
            }
        }
        res_cb = assess(cb_claims, cb_checks)
        self.assertEqual(res_cb["risk"]["score"], 0)
        self.assertEqual(res_cb["risk"]["outcome"], "verified-legit")
        self.assertEqual(res_cb["risk"]["level"], "Low Risk")
        self.assertEqual(res_cb["risk"]["level_key"], "low")
        self.assertFalse(res_cb["risk"]["insufficient_evidence"])

    def test_6_cosmetics_range_returns_and_snippets(self):
        # "1.5–2% monthly" -> lower bound 1.5%, 30 days
        c = heuristic_extract(NOVA_SPECIMEN_TEXT)
        self.assertEqual(c["promised_return_pct"], 1.5)
        self.assertEqual(c["return_period_days"], 30.0)

        # Snippet boundary check
        snip = _snippet("The returns depend on pool performance.", "pool")
        self.assertFalse(snip.startswith("ool"))
        self.assertTrue(snip.startswith("The returns") or snip.startswith("depend") or snip.startswith("pool") or snip.startswith("on"))


if __name__ == "__main__":
    unittest.main()
