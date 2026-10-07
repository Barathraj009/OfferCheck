"""Report persistence - the smallest sensible zero-cost layer: local SQLite via the
Python standard library. No database server, no cloud, no new dependency.

PRIVACY DECISION (documented in README/PROJECT_STATUS):
  * Stored: the derived REPORT only - extracted claims, short evidence snippets,
    check results, scores, confidence, timestamps. That is the minimum needed to
    reproduce what the user saw when they revisit the report.
  * NEVER stored: the raw offer text, uploaded screenshots (images are processed in
    memory and discarded), voice input, or anything secret (keys/credentials never
    appear in report payloads - the server builds reports from provider responses
    only, and the LLM/api keys stay in server env).
  * Report ids are 96-bit random tokens: unguessable, so knowing/listing them is the
    access mechanism (no accounts in this MVP). The table is pruned to a bounded
    size, and users can delete individual reports.
"""
from __future__ import annotations

import json
import re
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

# Set by tests to a temp location.
DB_PATH = Path(__file__).resolve().parents[1] / "data" / "reports.db"

MAX_REPORTS = 1000          # bounded storage: oldest reports are pruned
MAX_PAYLOAD_BYTES = 300_000  # one report is ~20-60KB; this is a generous ceiling
LIST_LIMIT = 50
ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,32}$")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    mode TEXT,
    is_demo INTEGER,
    risk_score INTEGER,
    risk_level TEXT,
    confidence_score INTEGER,
    confidence_level TEXT,
    headline TEXT,
    payload TEXT NOT NULL
)
"""


class InvalidReport(ValueError):
    """The submitted document is not a report we are willing to store."""


@contextmanager
def _db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _headline(report: dict) -> str:
    claims = report.get("claims") or {}
    name = claims.get("asset_name") or claims.get("asset_symbol")
    if name:
        return str(name)[:80]
    summary = (report.get("summary") or {}).get("text") or ""
    return (summary[:117] + "...") if len(summary) > 120 else (summary or "Report")


def save(report: dict) -> str:
    """Validate and persist a report; returns its unguessable id."""
    if not isinstance(report, dict):
        raise InvalidReport("not an object")
    risk = report.get("risk")
    summary = report.get("summary")
    if not isinstance(risk, dict) or not isinstance(risk.get("score"), int) or not isinstance(risk.get("level"), str):
        raise InvalidReport("missing risk score/level")
    if not isinstance(report.get("generated_at"), str) or not report.get("generated_at"):
        raise InvalidReport("missing generation timestamp")
    if not isinstance(report.get("checks"), list) or not isinstance(report.get("findings"), list):
        raise InvalidReport("missing checks/findings")
    if not isinstance(summary, dict) or not isinstance(summary.get("text"), str):
        raise InvalidReport("missing summary")
    payload = json.dumps(report, ensure_ascii=False)
    if len(payload.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise InvalidReport("too large")
    rid = secrets.token_urlsafe(12)
    conf = report.get("confidence") or {}
    with _db() as conn:
        conn.execute(
            "INSERT INTO reports (id, created_at, mode, is_demo, risk_score, risk_level,"
            " confidence_score, confidence_level, headline, payload) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (rid, _now(), str(report.get("mode", ""))[:10], int(bool(report.get("is_demo"))),
             risk["score"], risk["level"][:40], int(conf.get("score") or 0), str(conf.get("level") or "")[:20],
             _headline(report), payload))
        # bounded storage: keep only the newest MAX_REPORTS
        conn.execute("DELETE FROM reports WHERE seq NOT IN"
                     " (SELECT seq FROM reports ORDER BY seq DESC LIMIT ?)", (MAX_REPORTS,))
    return rid


def get(rid: str) -> dict | None:
    """Full report by id, or None (missing or malformed id)."""
    if not ID_RE.fullmatch(rid or ""):
        return None
    with _db() as conn:
        row = conn.execute("SELECT payload FROM reports WHERE id = ?", (rid,)).fetchone()
    if not row:
        return None
    try:
        data = json.loads(row["payload"])
    except ValueError:
        return None
    if isinstance(data, dict):
        data["report_id"] = rid
    return data


def list_reports() -> list[dict]:
    """Newest-first summaries for the history page (no payloads)."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, created_at, mode, is_demo, risk_score, risk_level,"
            " confidence_score, confidence_level, headline FROM reports"
            " ORDER BY seq DESC LIMIT ?", (LIST_LIMIT,)).fetchall()
    return [{"id": r["id"], "created_at": r["created_at"], "mode": r["mode"],
             "is_demo": bool(r["is_demo"]), "risk_score": r["risk_score"], "risk_level": r["risk_level"],
             "confidence_score": r["confidence_score"], "confidence_level": r["confidence_level"],
             "headline": r["headline"]} for r in rows]


def delete(rid: str) -> bool:
    if not ID_RE.fullmatch(rid or ""):
        return False
    with _db() as conn:
        cur = conn.execute("DELETE FROM reports WHERE id = ?", (rid,))
        return cur.rowcount > 0
