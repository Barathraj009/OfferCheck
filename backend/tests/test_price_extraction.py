"""Unit tests for price extraction across regex heuristics, LLM claim parsing, and validation."""
import unittest
from app.extraction import _prices, heuristic_extract, is_price_verbatim, merge_llm
from app.llm import _parse_numeric_claim, validate_llm_claims


class TestPriceExtraction(unittest.TestCase):

    def test_regex_prices(self):
        # 1. "for ₹30,000"
        p = _prices("My friend is selling her Bitcoin for ₹30,000.")
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["value"], 30000.0)
        self.assertEqual(p[0]["cur"], "INR")

        # 2. "1.5 lakh"
        p = _prices("Selling Bitcoin for 1.5 lakh")
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["value"], 150000.0)
        self.assertEqual(p[0]["cur"], "INR")

        # 3. "30k"
        p = _prices("Selling BTC for 30k")
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["value"], 30000.0)

        # 4. "$30,000"
        p = _prices("Bitcoin for $30,000")
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["value"], 30000.0)
        self.assertEqual(p[0]["cur"], "USD")

        # 5. "30000 INR"
        p = _prices("1 BTC for 30000 INR")
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["value"], 30000.0)
        self.assertEqual(p[0]["cur"], "INR")

        # 6. "0.5 ETH for 50,000 INR"
        p = _prices("Selling 0.5 ETH for 50,000 INR")
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["value"], 50000.0)
        self.assertEqual(p[0]["cur"], "INR")

        # 7. "@ ₹30,000"
        p = _prices("Bitcoin @ ₹30,000")
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["value"], 30000.0)
        self.assertEqual(p[0]["cur"], "INR")

    def test_heuristic_extract_claims(self):
        # Casual P2P input - quantity assumed = True, quantity = None, price_verbatim = True
        c1 = heuristic_extract("My friend is selling her Bitcoin for ₹30,000.")
        self.assertEqual(c1["asset_name"], "Bitcoin")
        self.assertEqual(c1["asset_symbol"], "BTC")
        self.assertEqual(c1["claimed_price"], 30000.0)
        self.assertEqual(c1["quoted_currency"], "INR")
        self.assertIsNone(c1["quantity"])
        self.assertTrue(c1["quantity_assumed"])
        self.assertTrue(c1["price_verbatim"])

        # Stated quantity: 1 BTC
        c2 = heuristic_extract("Selling 1 BTC for $30,000")
        self.assertEqual(c2["asset_symbol"], "BTC")
        self.assertEqual(c2["claimed_price"], 30000.0)
        self.assertEqual(c2["quoted_currency"], "USD")
        self.assertEqual(c2["quantity"], 1.0)
        self.assertFalse(c2["quantity_assumed"])
        self.assertTrue(c2["price_verbatim"])

        # Stated quantity: 0.5 ETH
        c3 = heuristic_extract("Selling 0.5 ETH for 50,000 INR")
        self.assertEqual(c3["asset_symbol"], "ETH")
        self.assertEqual(c3["claimed_price"], 50000.0)
        self.assertEqual(c3["quoted_currency"], "INR")
        self.assertEqual(c3["quantity"], 0.5)
        self.assertFalse(c3["quantity_assumed"])
        self.assertTrue(c3["price_verbatim"])

        # Stated price in lakh
        c4 = heuristic_extract("Selling Bitcoin for 1.5 lakh")
        self.assertEqual(c4["asset_name"], "Bitcoin")
        self.assertEqual(c4["claimed_price"], 150000.0)
        self.assertEqual(c4["quoted_currency"], "INR")
        self.assertIsNone(c4["quantity"])
        self.assertTrue(c4["quantity_assumed"])
        self.assertTrue(c4["price_verbatim"])

    def test_parse_numeric_claim(self):
        self.assertEqual(_parse_numeric_claim("for ₹30,000"), (30000.0, "INR"))
        self.assertEqual(_parse_numeric_claim("₹30,000"), (30000.0, "INR"))
        self.assertEqual(_parse_numeric_claim("1.5 lakh"), (150000.0, "INR"))
        self.assertEqual(_parse_numeric_claim("30k"), (30000.0, None))
        self.assertEqual(_parse_numeric_claim("$30,000"), (30000.0, "USD"))
        self.assertEqual(_parse_numeric_claim("30000 INR"), (30000.0, "INR"))
        self.assertEqual(_parse_numeric_claim("@ ₹30,000"), (30000.0, "INR"))
        self.assertEqual(_parse_numeric_claim(30000), (30000.0, None))
        self.assertEqual(_parse_numeric_claim(30000.0), (30000.0, None))
        self.assertEqual(_parse_numeric_claim(None), (None, None))
        self.assertEqual(_parse_numeric_claim("invalid_val"), (None, None))

    def test_validate_llm_claims(self):
        # Formatted string price with INR symbol
        raw = "My friend is selling her Bitcoin for ₹30,000."
        obj = {"asset_name": "Bitcoin", "asset_symbol": "BTC", "claimed_price": "₹30,000", "quantity": None}
        v = validate_llm_claims(obj, raw)
        self.assertEqual(v.get("asset_name"), "Bitcoin")
        self.assertEqual(v.get("asset_symbol"), "BTC")
        self.assertEqual(v.get("claimed_price"), 30000.0)
        self.assertEqual(v.get("quoted_currency"), "INR")
        self.assertTrue(v.get("price_verbatim"))
        self.assertNotIn("quantity", v)

        # Formatted string price with USD symbol
        obj2 = {"asset_name": "Bitcoin", "asset_symbol": "BTC", "claimed_price": "$30,000", "quantity": "1"}
        v2 = validate_llm_claims(obj2, "Selling 1 BTC for $30,000")
        self.assertEqual(v2.get("claimed_price"), 30000.0)
        self.assertEqual(v2.get("quoted_currency"), "USD")
        self.assertEqual(v2.get("quantity"), 1.0)
        self.assertTrue(v2.get("price_verbatim"))

        # Multiplier and percentage strings
        obj3 = {"promised_multiplier": "10x", "promised_return_pct": "50%"}
        v3 = validate_llm_claims(obj3, "Get 10x or 50% profit")
        self.assertEqual(v3.get("promised_multiplier"), 10.0)
        self.assertEqual(v3.get("promised_return_pct"), 50.0)

    def test_price_verbatim_tagging(self):
        # 1. "for ₹30,000" in text -> True (both "30,000" and "30000" matches)
        self.assertTrue(is_price_verbatim(30000.0, "My friend is selling her Bitcoin for ₹30,000."))
        self.assertTrue(is_price_verbatim(30000.0, "Selling Bitcoin for 30000 INR"))
        
        c_p2p = heuristic_extract("My friend is selling her Bitcoin for ₹30,000.")
        self.assertEqual(c_p2p["claimed_price"], 30000.0)
        self.assertTrue(c_p2p["price_verbatim"])

        # 2. "1.5 lakh" -> 150000.0 in text -> True (verbatim words match)
        self.assertTrue(is_price_verbatim(150000.0, "Selling Bitcoin for 1.5 lakh"))
        c_lakh = heuristic_extract("Selling Bitcoin for 1.5 lakh")
        self.assertEqual(c_lakh["claimed_price"], 150000.0)
        self.assertTrue(c_lakh["price_verbatim"])

        # 3. Metabot's package-table "1,000" rows -> fabricated 1000000 must yield False
        raw_metabot = "Metabot AI Trading Packages: Bronze package costs $1,000. Silver package costs $5,000. Gold costs $10,000."
        self.assertFalse(is_price_verbatim(1000000.0, raw_metabot))

        # Model validation on fabricated price
        v_fab = validate_llm_claims({"asset_name": "Metabot", "claimed_price": 1000000.0}, raw_text=raw_metabot)
        self.assertEqual(v_fab.get("claimed_price"), 1000000.0)
        self.assertFalse(v_fab.get("price_verbatim"))

        # Merge LLM on fabricated price when heuristic found no price
        base_no_price = heuristic_extract("Metabot investment platform with daily payouts")
        merged_metabot = merge_llm(base_no_price, {"claimed_price": 1000000.0}, raw_text="Metabot investment platform with daily payouts")
        self.assertEqual(merged_metabot.get("claimed_price"), 1000000.0)
        self.assertFalse(merged_metabot.get("price_verbatim"))

        # 4. No price present -> False
        self.assertFalse(is_price_verbatim(None, "Any random text"))
        self.assertFalse(is_price_verbatim(30000.0, ""))
        c_none = heuristic_extract("Send me your private key")
        self.assertFalse(c_none.get("price_verbatim"))

    def test_market_missing_price_notice(self):
        import asyncio
        from unittest.mock import patch, AsyncMock
        from app.sources.market import _coingecko, _dexscreener, _binance

        dummy_settings = type("S", (), {"http_timeout": 5.0, "cache_ttl": 60, "coingecko_api_key": None})()

        # 1. CoinGecko with missing claimed_price vs present claimed_price
        with patch("app.sources.market._price_by_id", new_callable=AsyncMock) as mock_cg_price:
            mock_cg_price.return_value = {"usd": 80000.0, "inr": 6800000.0, "usd_market_cap": 1e12, "usd_24h_vol": 1e10}
            
            # Missing claimed_price
            cl_no_price = {"asset_name": "Bitcoin", "asset_id": "bitcoin", "claimed_price": None}
            res1 = asyncio.run(_coingecko(cl_no_price, dummy_settings))
            self.assertEqual(res1["status"], "verified")
            self.assertIn("Offer price not detected — add it to run the price check.", res1["summary"])

            # Present claimed_price
            cl_with_price = {"asset_name": "Bitcoin", "asset_id": "bitcoin", "claimed_price": 30000.0}
            res2 = asyncio.run(_coingecko(cl_with_price, dummy_settings))
            self.assertEqual(res2["status"], "verified")
            self.assertNotIn("Offer price not detected", res2["summary"])

        # 2. DexScreener with missing claimed_price vs present claimed_price
        with patch("app.sources.market.fetch_dex_pairs", new_callable=AsyncMock) as mock_dex, \
             patch("app.sources.market._prices_from_usd", new_callable=AsyncMock) as mock_fx:
            mock_dex.return_value = [{"priceUsd": "1.50", "baseToken": {"name": "Token", "symbol": "TOK"}, "liquidity": {"usd": 10000}}]
            mock_fx.return_value = {"usd": 1.5, "inr": 125.0}

            cl_dex_no_price = {"contract_address": "0x1111111111111111111111111111111111111111", "chain": "ethereum", "claimed_price": None}
            res_dex1 = asyncio.run(_dexscreener(cl_dex_no_price, dummy_settings))
            self.assertIn("Offer price not detected — add it to run the price check.", res_dex1["summary"])

            cl_dex_with_price = {"contract_address": "0x1111111111111111111111111111111111111111", "chain": "ethereum", "claimed_price": 1.5}
            res_dex2 = asyncio.run(_dexscreener(cl_dex_with_price, dummy_settings))
            self.assertNotIn("Offer price not detected", res_dex2["summary"])

        # 3. Binance with missing claimed_price vs present claimed_price
        with patch("app.sources.market.cached", new_callable=AsyncMock) as mock_bn_cache, \
             patch("app.sources.market._prices_from_usd", new_callable=AsyncMock) as mock_bn_fx:
            mock_bn_cache.return_value = {"price": "80000.00"}
            mock_bn_fx.return_value = {"usd": 80000.0, "inr": 6800000.0}

            cl_bn_no_price = {"asset_symbol": "BTC", "claimed_price": None}
            res_bn1 = asyncio.run(_binance(cl_bn_no_price, dummy_settings))
            self.assertIn("Offer price not detected — add it to run the price check.", res_bn1["summary"])

            cl_bn_with_price = {"asset_symbol": "BTC", "claimed_price": 30000.0}
            res_bn2 = asyncio.run(_binance(cl_bn_with_price, dummy_settings))
            self.assertNotIn("Offer price not detected", res_bn2["summary"])


    def test_acceptance_pair_price_bait(self):
        from app.scoring import assess, r_price

        # Pair 1: "My friend is selling her Bitcoin for ₹30,000."
        # Must produce the price-bait finding (PRICE_BAIT_UNSTATED_QUANTITY) and Moderate Risk
        p2p_claims = heuristic_extract("My friend is selling her Bitcoin for ₹30,000.")
        self.assertEqual(p2p_claims["claimed_price"], 30000.0)
        self.assertEqual(p2p_claims["quoted_currency"], "INR")
        self.assertTrue(p2p_claims["quantity_assumed"])
        self.assertTrue(p2p_claims["price_verbatim"])

        checks_p2p = {
            "market": {
                "check_id": "market",
                "status": "verified",
                "source": "CoinGecko",
                "timestamp": "2026-10-09T00:00:00Z",
                "data": {
                    "asset_id": "bitcoin",
                    "symbol": "BTC",
                    "prices": {"usd": 80000.0, "inr": 7900000.0},
                    "source": "CoinGecko"
                }
            }
        }

        finding = r_price(p2p_claims, checks_p2p)
        self.assertIsNotNone(finding)
        self.assertEqual(finding["rule_id"], "PRICE_BAIT_UNSTATED_QUANTITY")
        self.assertEqual(finding["title"], "Implausible discount (quantity unstated)")
        self.assertEqual(finding["points"], 25)
        self.assertIn("Offer is ~99.6% below market", finding["observed"])
        self.assertIn("either a bait price or a tiny fraction of 1 BTC; verify exactly what quantity you receive.", finding["observed"])
        self.assertTrue(finding["evidence"]["price_verbatim"])
        self.assertTrue(finding["evidence"]["quantity_assumed"])

        res_p2p = assess(p2p_claims, checks_p2p)
        self.assertEqual(res_p2p["risk"]["score"], 25)
        self.assertEqual(res_p2p["risk"]["level_key"], "moderate")
        self.assertEqual(res_p2p["risk"]["level"], "Moderate Risk")
        self.assertEqual(res_p2p["risk"]["outcome"], "suspicious")

        # Pair 2: Metabot input with package table / fabricated price -> NO price finding
        metabot_claims = {
            "asset_name": "Metabot",
            "asset_symbol": "META",
            "claimed_price": 1000000.0,
            "quoted_currency": "usd",
            "quantity_assumed": True,
            "price_verbatim": False
        }
        checks_metabot = {
            "market": {
                "check_id": "market",
                "status": "verified",
                "source": "CoinGecko",
                "timestamp": "2026-10-09T00:00:00Z",
                "data": {
                    "asset_id": "metabot",
                    "symbol": "META",
                    "prices": {"usd": 50000000.0},
                    "source": "CoinGecko"
                }
            }
        }
        finding_metabot = r_price(metabot_claims, checks_metabot)
        self.assertIsNone(finding_metabot)

    def test_confidence_derives_from_weights(self):
        from app.scoring import coverage, confidence

        # 1 of 7 checks verified (market check only with weight 20)
        checks_1 = {
            "market": {"check_id": "market", "status": "verified", "source": "CoinGecko", "data": {}}
        }
        cov = coverage(checks_1)
        self.assertEqual(cov["available"], 1)
        self.assertEqual(cov["_aw"], 20)
        conf = confidence(cov, [])
        self.assertEqual(conf["score"], 20)
        self.assertEqual(conf["level"], "Low")

        # Multiple checks: market (20) + entity (20) + security (20) + domain (10) = 70 -> High
        checks_4 = {
            "market": {"check_id": "market", "status": "verified", "source": "CoinGecko", "data": {}},
            "entity": {"check_id": "entity", "status": "verified", "source": "Wikipedia", "data": {}},
            "security": {"check_id": "security", "status": "verified", "source": "GoPlus", "data": {}},
            "domain": {"check_id": "domain", "status": "verified", "source": "RDAP", "data": {}},
        }
        cov4 = coverage(checks_4)
        self.assertEqual(cov4["available"], 4)
        self.assertEqual(cov4["_aw"], 70)
        conf4 = confidence(cov4, [])
        self.assertEqual(conf4["score"], 70)
        self.assertEqual(conf4["level"], "High")


if __name__ == "__main__":
    unittest.main()


