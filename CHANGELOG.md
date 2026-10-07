# Changelog

All notable changes to OfferCheck are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are project milestones.

## [0.2.0] - 2026-10-07 — OfferCheck Zero-Cost Baseline

First release-ready checkpoint: every verification check works with **no API keys and no paid
services**, pushed to source control as the stable baseline for future work.

### Added

- **Provider-chain framework** (`app/sources/base.py`): ordered `run_chain` with `stop_on`,
  per-provider timing, and `fallback_from` provenance recorded in every check.
- **Resilience** (`app/sources/common.py`): circuit breaker, shared cached HTTP client, JSON
  scraping helper, and per-host rate-limit awareness.
- **LLM chain** (`app/sources/llm.py`): local Ollama → optional Anthropic key → none, with
  `validate_llm_claims` guards — the LLM extracts claims and rewrites explanations only; it never
  sets the score. `pick_model()` uses a model that is actually installed (never downloads).
- **Contract verification**: Sourcify v2 (keyless) → Etherscan (optional key) → public RPC
  bytecode comparison (2 endpoints per chain).
- **Market chain**: CoinGecko (keyless) → DexScreener by contract → Binance, plus Frankfurter/ECB
  FX. Shared DexScreener pair lookup across liquidity and price checks.
- **Web safety**: RDAP registration lookup with DNS-existence fallback; Google Safe Browsing
  (optional key) → OpenPhish feed (keyless) fallback.
- **Demo scenarios** A–E, including new D ("too vague" → insufficient data) and E
  ("partial verification" → high risk, medium confidence).
- **`GET /api/health`**: `zero_cost_ready`, `llm_provider`, live Ollama model list, per-source
  availability — no secrets exposed.
- **`backend/doctor.py`**: machine capability report (READY / OPTIONAL / MISSING, `--probe`).
- **Report UI**: "Why this score?" rule→evidence→points table, "What was checked?" source
  section, honest voice/screenshot capability copy, live-source labelling.
- **Docs**: `README.md` (repo-relative), `ZERO_COST_SETUP.md`, `ARCHITECTURE.md`,
  `DEPENDENCY_LICENSES.md`, `FREE_PROVIDER_MATRIX.md`, `.env.example` (all keys optional).

### Fixed

- `get_settings()` did not populate the new LLM fields → `TypeError` at startup.
- LLM function signatures (`(value, provider)` tuples) mismatched in the orchestrator.
- Model-pick advertised `llama3.2:3b` on machines that only have `llama3.2:1b` → every LLM call
  would have failed; now exact tag → family → first installed.
- `fallback_from` hid soft answers (e.g. `not_found`) from earlier providers.
- Liquidity "no pairs" weight 20 → 15 (a brand-new/unlisted token is not automatically fraud).
- Error responses now consistently use `{error: {field, message}}`; rate-limit table pruned.
- OCR screenshot preprocessing: grayscale + autocontrast + ≤3× upscale; missing Tesseract
  degrades honestly to `503` instead of failing the whole analysis.

### Verification (this machine, no API keys)

| Suite | Result |
|---|---|
| Unit (`python -m unittest discover -s tests`) | **24/24** |
| Integration (`python tests/integration_http.py`) | **38/38** |
| Integration + live Ollama (`OFFERCHECK_LIVE_LLM=1`) | **39/39** |
| Frontend build (`npm run build`) | clean |
| UI smoke (`node scripts/ui-smoke.mjs`, 22 checks) | **22/22**, 0 JS errors |
| Live keyless probes (Sourcify, OpenPhish, CoinGecko, GoPlus, DexScreener) | verified |

### Known limitations

- **Screenshot OCR** requires a local Tesseract binary (optional, never auto-downloaded);
  without it the endpoint returns an honest `503` and text input keeps working.
- Claim extraction for messy/regional-language text needs a local Ollama model (free) or an
  optional `ANTHROPIC_API_KEY`; otherwise the rule-based extractor is used.
- CPU-only machines: one LLM extraction call takes ~60s (documented; UI waits up to 180s).

## [0.1.0] - 2026-10-06 — Initial Phase 1/2 development

Core pipeline (input → claim extraction → 6 verification checks → deterministic scoring →
confidence → explainable report), demo mode, and the first free/local provider integrations.
