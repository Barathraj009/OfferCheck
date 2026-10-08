"""Unit tests for price extraction across regex heuristics, LLM claim parsing, and validation."""
import unittest
from app.extraction import _prices, heuristic_extract
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
        # Casual P2P input - quantity assumed = True, quantity = None
        c1 = heuristic_extract("My friend is selling her Bitcoin for ₹30,000.")
        self.assertEqual(c1["asset_name"], "Bitcoin")
        self.assertEqual(c1["asset_symbol"], "BTC")
        self.assertEqual(c1["claimed_price"], 30000.0)
        self.assertEqual(c1["quoted_currency"], "INR")
        self.assertIsNone(c1["quantity"])
        self.assertTrue(c1["quantity_assumed"])

        # Stated quantity: 1 BTC
        c2 = heuristic_extract("Selling 1 BTC for $30,000")
        self.assertEqual(c2["asset_symbol"], "BTC")
        self.assertEqual(c2["claimed_price"], 30000.0)
        self.assertEqual(c2["quoted_currency"], "USD")
        self.assertEqual(c2["quantity"], 1.0)
        self.assertFalse(c2["quantity_assumed"])

        # Stated quantity: 0.5 ETH
        c3 = heuristic_extract("Selling 0.5 ETH for 50,000 INR")
        self.assertEqual(c3["asset_symbol"], "ETH")
        self.assertEqual(c3["claimed_price"], 50000.0)
        self.assertEqual(c3["quoted_currency"], "INR")
        self.assertEqual(c3["quantity"], 0.5)
        self.assertFalse(c3["quantity_assumed"])

        # Stated price in lakh
        c4 = heuristic_extract("Selling Bitcoin for 1.5 lakh")
        self.assertEqual(c4["asset_name"], "Bitcoin")
        self.assertEqual(c4["claimed_price"], 150000.0)
        self.assertEqual(c4["quoted_currency"], "INR")
        self.assertIsNone(c4["quantity"])
        self.assertTrue(c4["quantity_assumed"])

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
        self.assertNotIn("quantity", v)

        # Formatted string price with USD symbol
        obj2 = {"asset_name": "Bitcoin", "asset_symbol": "BTC", "claimed_price": "$30,000", "quantity": "1"}
        v2 = validate_llm_claims(obj2, "Selling 1 BTC for $30,000")
        self.assertEqual(v2.get("claimed_price"), 30000.0)
        self.assertEqual(v2.get("quoted_currency"), "USD")
        self.assertEqual(v2.get("quantity"), 1.0)

        # Multiplier and percentage strings
        obj3 = {"promised_multiplier": "10x", "promised_return_pct": "50%"}
        v3 = validate_llm_claims(obj3, "Get 10x or 50% profit")
        self.assertEqual(v3.get("promised_multiplier"), 10.0)
        self.assertEqual(v3.get("promised_return_pct"), 50.0)

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


if __name__ == "__main__":
    unittest.main()

