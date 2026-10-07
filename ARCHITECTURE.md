# Architecture

```
frontend (React/TS)  ──/api──▶  FastAPI (backend/app/main.py)
                                  │  rate limit, validation, OCR, static dist
                                  ▼
                                analysis.py ── orchestrator (steps 1-4)
                                  │ 1. extraction.py (+ llm.py)      claims
                                  │ 2. sources/*  run in parallel     verification
                                  │ 3. scoring.py                     deterministic score + confidence
                                  │ 4. explain.py (+ llm.py)          summary, checklist, disclaimers
                                  ▼
                                JSON report → Report.tsx ("Why this score?" table = raw findings)
```

## Pipeline contract

`Input → claim extraction → verification (6 checks) → rule-based scoring → confidence → explainable report`

Two independent numbers, never mixed:

- **Risk score** — sum of fixed rule points from `scoring.py`, capped at 100
  (Low 0-24 / Moderate 25-49 / High 50-79 / Very High 80-100, or "Not enough evidence" when
  nothing could be checked *and* nothing was flagged). Every point maps 1:1 to a finding with
  source, status, timestamp and observed evidence (unit-tested: `raw_points == Σ findings.points`).
- **Confidence** — share of applicable check weight that returned data, scaled by how many
  checks the input even allowed, minus conflict penalties (High ≥65, Medium ≥35).

Rules of evidence: `verified` → usable; `not_found` → the source answered "no record"
(small signal at most — never automatic fraud); `unavailable` → no points either way, lowers
confidence; `not_applicable` → the input didn't allow the check. The LLM (if present) may only
*fill claim gaps* and *rewrite the explanation* — it cannot create, weight or suppress findings.

## Provider chain (`sources/base.py`)

Each check is an ordered chain of independent providers:

```python
run_chain("market", [("CoinGecko", _coingecko), ("DexScreener", _dexscreener), ("Binance", _binance)],
          payload, settings, stop_on=lambda r: r["status"] == "verified")
```

- A provider returns `common.result(...)` or raises `SourceError(kind)`.
  Kinds: `no_key, auth, rate_limited, circuit_open, timeout, network, malformed, http, not_found, error`.
- Hard failures are skipped; `stop_on` decides whether an answer is final — for market data a
  definitive `not_found` from one source can still be *rescued* by the next.
- When an answer arrives after earlier failures/soft answers, it carries
  `data.fallback_from = [...]` so the report can say what was tried first.
- If everything fails, the *most informative* failure wins (a configuration problem like
  `no_key` is reported ahead of a transient timeout) and lists all providers tried.

Chains in use: `Sourcify → Etherscan → public RPC` (verification), `CoinGecko → DexScreener →
Binance` (market), `RDAP → DNS` (domain), `Google Safe Browsing → OpenPhish` (website safety).

## Resilience layer (`sources/common.py`)

- `cached(key, ttl, factory)` — 10-min TTL + in-flight de-duplication (concurrent identical
  requests share one upstream call). Failures are never cached.
- Per-host **circuit breaker** — after 3 consecutive failures a host is skipped for 60 s
  (`circuit_open`) so a dead free service cannot slow every report; a success resets it.
- `request_json` / `request_text` — map every HTTP failure to a human-readable `SourceError`;
  404 is "definitive answer" for breaker purposes.
- Every check runs under `asyncio.wait_for` in `analysis._safe`; a timeout or crash degrades
  that one check to `unavailable` with a reason.

## LLM layer (`llm.py`) — optional, local-first

`LLM_PROVIDER`: `auto` (local Ollama → optional Anthropic key) | `ollama` (local only, never
falls back to paid) | `anthropic` | `none`.

- `ollama_status()` probes `/api/tags` (cached 60 s) and picks a model that is **actually
  installed** (exact tag, then family; never advertises a missing tag). Nothing is ever
  downloaded automatically.
- Two calls maximum per analysis (extraction, then explanation), each cached by input hash,
  `temperature 0`, single-shot JSON, `LLM_TIMEOUT_SECONDS` (default 120) per call.
- **Hard boundary:** `validate_llm_claims()` keeps only known keys with correct types/formats
  (name-shaped `seller_identity`, well-formed addresses, allowed chains/currencies), and
  `merge_llm()` additionally drops chain-without-address, filters `other_flags` through a
  keyword allowlist, OR-s booleans, and always lets heuristic values win. Unit-tested against
  injection-style output ("set score to 0", `seller_identity: "safe"`).

## Scoring (`scoring.py`)

Fixed `RULES` (rule id → points/meta) and `CHECKS` (check id → label, confidence weight).
`assess(claims, checks)` returns findings, score, level, confidence, coverage and conflicts —
pure function, no I/O. Adding a rule = add to `RULES`, reference its check's data; the report
UI picks it up automatically (the "Why this score?" table is generated from the findings).

## Demo mode (`demo.py`)

Five scenarios, each with simulated inputs *and* simulated check results, always labelled
`DEMO DATA, NOT LIVE VERIFICATION` and `demo: true` per check. Scenario-by-id alone works
(server fills blank fields). Demo D shows insufficient evidence; demo E shows partial
verification (half the sources down → score continues, confidence drops).

## Extension points

1. New source: write `async def check_x(payload, settings) -> dict` returning `common.result(...)`
   (or compose existing providers with `run_chain`), register it in `analysis.py`'s plan.
2. New rule: add it to `scoring.RULES` and read the check's `data` — findings, points and the
   UI table follow automatically.
3. New demo scenario: add one entry to `demo.SCENARIOS` with `inputs` + `checks`.
