"""Unit tests for app.store - local SQLite report persistence."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from app import store


def sample_report(**over) -> dict:
    r = {
        "generated_at": "2026-10-07T12:00:00+00:00",
        "mode": "demo",
        "is_demo": True,
        "risk": {"score": 64, "level": "High", "level_key": "high", "raw_points": 64,
                 "insufficient_evidence": False},
        "confidence": {"score": 72, "level": "Medium", "reasons": ["x"]},
        "claims": {"asset_name": "TestCoin", "other_flags": []},
        "summary": {"text": "This looks risky.", "method": "template"},
        "checks": [{"check_id": "etherscan", "status": "verified"}],
        "findings": [{"rule_id": "guaranteed_returns", "points": 30}],
        "coverage": {"available": 5, "total": 7},
        "conflicts": [], "checklist": ["verify"], "disclaimers": ["not advice"],
        "never_share": "seed phrase", "extraction": {"method": "heuristic", "notes": []},
    }
    r.update(over)
    return r


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ocstore-"))
        self._old = store.DB_PATH
        store.DB_PATH = self.tmp / "reports.db"

    def tearDown(self):
        store.DB_PATH = self._old
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_save_get_roundtrip(self):
        rid = store.save(sample_report())
        self.assertRegex(rid, r"^[A-Za-z0-9_-]{10,32}$")
        got = store.get(rid)
        self.assertEqual(got["risk"]["score"], 64)
        self.assertEqual(got["summary"]["text"], "This looks risky.")
        self.assertEqual(got["report_id"], rid)

    def test_missing_report_returns_none(self):
        self.assertIsNone(store.get("doesnotexist123"))
        self.assertIsNone(store.get("short"))
        self.assertIsNone(store.get("../etc/passwd"))
        self.assertIsNone(store.get("a b c d e f g h i j k l"))

    def test_incomplete_report_rejected(self):
        for bad in ({}, {"generated_at": "x"}, sample_report(risk={"score": "high"}), []):
            with self.assertRaises(store.InvalidReport):
                store.save(bad)

    def test_oversized_report_rejected(self):
        big = sample_report()
        big["findings"] = [{"observed": "y" * 60000}] * 6
        with self.assertRaises(store.InvalidReport):
            store.save(big)

    def test_list_summaries(self):
        a = store.save(sample_report())
        b = store.save(sample_report(is_demo=False, mode="live"))
        items = store.list_reports()
        self.assertEqual({i["id"] for i in items}, {a, b})
        for i in items:
            self.assertEqual(set(i), {"id", "created_at", "mode", "is_demo", "risk_score",
                                      "risk_level", "confidence_score", "confidence_level", "headline"})
            self.assertNotIn("payload", i)
        headline = next(i for i in items if i["id"] == a)["headline"]
        self.assertEqual(headline, "TestCoin")

    def test_delete(self):
        rid = store.save(sample_report())
        self.assertTrue(store.delete(rid))
        self.assertIsNone(store.get(rid))
        self.assertFalse(store.delete(rid))
        self.assertFalse(store.delete("bad id!!"))

    def test_prune_keeps_bounded_count(self):
        old = store.MAX_REPORTS
        store.MAX_REPORTS = 3
        try:
            ids = [store.save(sample_report()) for _ in range(5)]
            self.assertEqual(len(store.list_reports()), 3)
            self.assertIsNotNone(store.get(ids[-1]))
            self.assertIsNone(store.get(ids[0]))
        finally:
            store.MAX_REPORTS = old

    def test_payload_is_json_object(self):
        rid = store.save(sample_report())
        with store._db() as conn:
            payload = conn.execute("SELECT payload FROM reports WHERE id=?", (rid,)).fetchone()["payload"]
        self.assertIsInstance(json.loads(payload), dict)


if __name__ == "__main__":
    unittest.main()
