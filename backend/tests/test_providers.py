"""Provider-chain, circuit-breaker and LLM-output guard tests.
Run:  cd backend && python -m unittest discover -s tests -v   (offline: no network, no keys)"""
import asyncio, os, sys, time, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.extraction import heuristic_extract, merge_llm
from app.llm import validate_llm_claims
from app.scoring import CHECKS, assess
from app.sources.base import run_chain
from app.sources.common import SourceError, _cb, _cb_check, _cb_record, result

run = asyncio.run


async def _ok(p, s):
    return result("market", "Good", "verified", "ok", data={"v": 1})


async def _rate_limited(p, s):
    raise SourceError("Too many requests.", "rate_limited")


async def _no_key(p, s):
    raise SourceError("No API key configured.", "no_key")


async def _soft_not_found(p, s):
    return result("market", "Soft", "not_found", "no listing here")


async def _second_ok(p, s):
    return result("market", "Second", "verified", "found it", data={"v": 2})


class ProviderChain(unittest.TestCase):
    def test_fallback_annotation(self):
        """A degraded-but-answered check must say which providers were skipped first."""
        r = run(run_chain("t", [("A", _rate_limited), ("B", _ok)], {}, type("S", (), {"http_timeout": 8.0})()))
        self.assertEqual(r["status"], "verified")
        self.assertEqual(r["data"]["fallback_from"], ["A"])

    def test_stop_on_rescues_soft_not_found(self):
        """Market semantics: 'not found' from provider 1 is not final if provider 2 answers."""
        s = type("S", (), {"http_timeout": 8.0})()
        r = run(run_chain("t", [("A", _soft_not_found), ("B", _second_ok)], {}, s,
                          stop_on=lambda out: out["status"] == "verified"))
        self.assertEqual(r["source"], "Second")
        self.assertEqual(r["data"]["fallback_from"], ["A"])
        soft = run(run_chain("t", [("A", _soft_not_found), ("B", _rate_limited)], {}, s,
                             stop_on=lambda out: out["status"] == "verified"))
        self.assertEqual(soft["status"], "not_found")  # soft answer returned when nothing better came

    def test_all_fail_raises_most_informative(self):
        s = type("S", (), {"http_timeout": 8.0})()
        with self.assertRaises(SourceError) as cm:
            run(run_chain("t", [("A", _rate_limited), ("B", _no_key)], {}, s))
        self.assertEqual(cm.exception.kind, "no_key")  # configuration issue beats transient failure
        self.assertIn("A", cm.exception.reason)
        self.assertIn("B", cm.exception.reason)

    def test_broken_provider_never_crashes_chain(self):
        async def boom(p, s):
            raise RuntimeError("bug in provider")
        s = type("S", (), {"http_timeout": 8.0})()
        r = run(run_chain("t", [("boom", boom), ("B", _ok)], {}, s))
        self.assertEqual(r["status"], "verified")
        self.assertEqual(r["data"]["fallback_from"], ["boom"])


class CircuitBreaker(unittest.TestCase):
    def test_opens_after_repeated_failures_and_resets(self):
        host = "cb-test-host.example"
        _cb.pop(host, None)
        for _ in range(3):
            _cb_record(host, False)
        with self.assertRaises(SourceError) as cm:
            _cb_check(host)
        self.assertEqual(cm.exception.kind, "circuit_open")
        _cb_record(host, True)  # a success closes it again
        _cb_check(host)  # must not raise


class LLMGuards(unittest.TestCase):
    def test_validate_rejects_injection_like_output(self):
        out = validate_llm_claims({"seller_identity": "safe", "chain": "ethereum",
                                   "contract_address": "0x123", "other_flags": ["safe", "WhatsApp"],
                                   "junk_key": "x", "claimed_price": "40 lakh"})
        self.assertNotIn("seller_identity", out)          # not name-shaped
        self.assertNotIn("contract_address", out)         # malformed
        self.assertNotIn("junk_key", out)                 # unknown key
        self.assertEqual(out.get("other_flags"), ["safe", "WhatsApp"])  # type-valid; wording filtered at merge

    def test_validate_keeps_real_claims(self):
        out = validate_llm_claims({"seller_identity": "Rahul Sharma", "chain": "bsc",
                                   "contract_address": "0x" + "ab" * 20, "quoted_currency": "inr",
                                   "claimed_price": "4000000"})
        self.assertEqual(out["seller_identity"], "Rahul Sharma")
        self.assertEqual(out["chain"], "bsc")
        self.assertEqual(out["quoted_currency"], "INR")

    def test_merge_fills_gaps_but_heuristics_win(self):
        base = heuristic_extract("Buy Bitcoin for ₹40 lakh. Guaranteed to double your money in 30 days.")
        merged = merge_llm(base, {"claimed_price": 500000.0, "quoted_currency": "INR",
                                  "guaranteed_language": False, "website_url": "https://x.example",
                                  "chain": "ethereum", "other_flags": ["safe", "continue on WhatsApp"]})
        self.assertEqual(merged["claimed_price"], 4000000.0)   # heuristic value kept
        self.assertTrue(merged["guaranteed_language"])          # booleans OR-ed, never cleared
        self.assertEqual(merged["website_url"], "https://x.example")  # empty gap filled
        self.assertIsNone(merged["chain"])                      # chain guess dropped: no address
        self.assertIn("continue on WhatsApp", merged["other_flags"])
        self.assertNotIn("safe", merged["other_flags"])         # free text filtered
        self.assertEqual(merged["extraction_method"], "heuristic+llm")

    def test_merge_keeps_chain_when_address_exists(self):
        base = heuristic_extract("Trade 0x" + "ab" * 20 + " on BNB Chain")
        merged = merge_llm(base, {"chain": "bsc", "contract_address": "0x" + "ab" * 20})
        self.assertEqual(merged["chain"], "bsc")


class OllamaModelPick(unittest.TestCase):
    def _status(self, settings):
        from unittest import mock
        from app.llm import ollama_status
        from app.sources.common import _cache

        async def fake(*a, **k):
            return {"models": [{"name": "llama3.2:1b"}, {"name": "nomic-embed-text:latest"}]}

        _cache._d.pop("ollama:status", None)
        try:
            with mock.patch("app.llm.request_json", fake):
                return asyncio.run(ollama_status(settings))
        finally:
            _cache._d.pop("ollama:status", None)

    def test_picks_actually_installed_tag(self):
        """MODEL_PREFERENCE lists llama3.2:3b first, but only llama3.2:1b is installed.
        The status must never advertise a model Ollama would reject."""
        from dataclasses import replace
        from app.config import get_settings
        st = self._status(get_settings())
        self.assertTrue(st["available"])
        self.assertEqual(st["model"], "llama3.2:1b")

    def test_configured_missing_model_reports_none(self):
        from dataclasses import replace
        from app.config import get_settings
        st = self._status(replace(get_settings(), ollama_model="llama3.2:3b"))
        self.assertTrue(st["available"])
        self.assertIsNone(st["model"])


class ScoringAudit(unittest.TestCase):
    def test_liquidity_not_found_weight_is_15(self):
        r = assess({"phrases": {}, "asset_name": "NewCoin"},
                   {"liquidity": result("liquidity", "DexScreener", "not_found", "x")})
        liq = next(f for f in r["findings"] if f["rule_id"] == "LIQUIDITY")
        self.assertEqual(liq["points"], 15)

    def test_check_label_is_contract_verification(self):
        self.assertEqual(CHECKS["explorer"][0], "Contract verification")


if __name__ == "__main__":
    unittest.main()
