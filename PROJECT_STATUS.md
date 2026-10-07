# PROJECT_STATUS.md — OfferCheck

**Last audited:** 2026-10-07 · **Status:** Phase 2 complete — fully zero-cost, all suites green

> **Milestone — OfferCheck Zero-Cost Baseline (v0.2.0)** — first release-ready checkpoint: zero-cost
> verification chain complete and green on this machine (unit 24/24 · integration 38/38 · live-LLM
> 39/39 · UI smoke 22/22 · `npm run build` clean). Known gap: screenshot OCR degrades honestly to
> 503 (Tesseract binary not installed — optional). See `CHANGELOG.md`.

Pipeline preserved: `Input → claim extraction → verification (6 checks) → rule-based scoring → confidence → explainable report`.
The LLM (optional, local-first) only extracts claims and rewrites explanations; it never sets the score.

---

## 1. Zero-cost capability matrix (verified on this machine, no keys present)

| Capability | Provider chain | Status |
|---|---|---|
| Contract verification | **Sourcify v2 (keyless)** → Etherscan (optional key) → public RPC bytecode (2 endpoints/chain) | **LIVE, keyless — verified: USDT → `verified`, source=Sourcify** |
| Token security scan | **GoPlus (keyless)** | LIVE, keyless — verified (USDT) |
| Liquidity & trading | **DexScreener chain-scoped (keyless)** | LIVE — verified ($32.7M PEPE) |
| Market price | **CoinGecko (keyless)** → DexScreener by contract → Binance ticker → FX via **Frankfurter/ECB** | LIVE — verified (BTC USD 83,056 observed) |
| Domain registration | **RDAP (keyless)** → DNS resolution fallback (existence only, never invents age) | LIVE — verified |
| Website safety | Google Safe Browsing (optional key) → **OpenPhish feed (keyless)** | **LIVE, keyless — verified: 130 feed sites, example.com clean** |
| AI claim extraction | **Local Ollama `llama3.2:1b`** → Anthropic (optional key) → heuristic | **LIVE — `OFFERCHECK_LIVE_LLM=1`: `method=heuristic+llm, provider=ollama, summary=llm`** |
| LLM explanation | same chain → fixed template | LIVE (template without model; local model verified) |
| Risk score / confidence / report | pure local code | LIVE, offline |
| Screenshot OCR | local Tesseract + grayscale/autocontrast/upscale preprocessing | Endpoint verified (503 honest degrade — binary not installed on this machine) |
| Voice input | Browser Web Speech API | Browser feature-detection verified |
| Demo mode (5 scenarios) | simulated, labelled | LIVE — A high / B very_high / C low / D insufficient / E high+conf Medium |

`GET /api/health` now reports `zero_cost_ready: true`, `llm_provider`, and the live Ollama status (model list — no secrets).

## 2. Bugs found and fixed

| # | Issue | Fix |
|---|---|---|
| 1 | Demo scenarios B/C failed (HTTP 422) when requested by id alone. | `analysis.py`: blank fields filled from the scenario. Test: `test_demo_scenario_by_id_alone`. |
| 2 | DexScreener generic endpoint crowded out the target chain (30 pairs across all chains) → false "no liquidity". | `chain.py`: chain-scoped `token-pairs/v1/{chain}/{addr}`. |
| 3 | Pydantic/body errors used FastAPI's `[{loc,msg}]` shape, not `{error:{field,message}}`. | `main.py`: `RequestValidationError` handler. |
| 4 | Rate-limit table could grow without bound. | `main.py`: prune stale IPs past 1000 entries. |
| 5 | Language hint promised explanations follow the language without a model. | `Check.tsx` + README wording: conditional on a model being available. |
| 6 | Integration fake PNG was not a valid image (Pillow correctly rejected it). | Real 1×1 PNG; accepts OCR result or clear 503. |
| 7 **(P2)** | `Settings` gained LLM fields but `get_settings()` didn't populate them → `TypeError` at startup. | `config.py`: `LLM_PROVIDER`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `LLM_TIMEOUT_SECONDS` wired (validated defaults). |
| 8 **(P2)** | `extract_claims_llm`/`summarize_llm` changed to return `(value, provider)` tuples; orchestrator still used old signature. | `analysis.py`: tuple handling + `extraction.llm_provider` surfaced to the report. |
| 9 **(P2)** | **Model-pick bug:** preference list matched by *base name*, so `llama3.2:1b`-only machine advertised missing `llama3.2:3b` → every LLM call would fail. | `llm.py`: `pick_model()` chooses from models actually installed (exact tag → family → first); configured missing model reports `null`. Regression test added. |
| 10 **(P2)** | `run_chain` only recorded *hard failures* in `fallback_from`, hiding that a rescued `not_found` came from an earlier provider. | `base.py`: every tried-but-unused provider (failure or soft answer) is recorded in order. |
| 11 **(P2)** | Liquidity "no pairs" contributed 20 points although it can mean a brand-new/unlisted token. | `scoring.py`: `LIQUIDITY` not-found weight 20 → **15** (test: `test_liquidity_not_found_weight_is_15`). |

## 3. Zero-cost work delivered (Phase 2)

| Area | What |
|---|---|
| Provider chain | New `sources/base.py` `run_chain(...)`: ordered providers, per-provider timeout, failure-kind priority (`no_key` beats transient), `stop_on` rescue semantics, `fallback_from` provenance. |
| Resilience | `common.py`: per-host **circuit breaker** (3 fails → 60 s skip), `request_text` for plain-text feeds, 404 treated as definitive for the breaker. |
| Contract verification | `chain.py`: Sourcify v2 (keyless, v1 retired) → Etherscan (optional key; RPC bytecode check distinguishes EOA vs hidden code) → 2 public RPCs/chain. 404 → `source_verified: None` (never "scam"). |
| Market | `market.py`: CoinGecko → DexScreener-by-contract (shared cache key with the liquidity check = one upstream call) → Binance by symbol; FX conversion via Frankfurter/ECB labelled `fx_converted`. |
| Website safety | `web.py`: GSB (optional) → OpenPhish feed (keyless, registrable-domain match; "no match ≠ safe" wording). |
| Domain | `web.py`: RDAP → DNS fallback (reports resolves/addresses; age stays `null`, never guessed). |
| LLM | Local-first chain, installed-model detection, `LLM_PROVIDER=ollama` never falls back to paid, 120 s/call, output validated (`validate_llm_claims`) + merge guards (chain needs an address, flag allowlist, heuristic wins, name-shaped seller identity). |
| UI | "Why this score?" Rule→Evidence→Points→Why table; "What was checked?" section (+ fallback provenance); honest source/voice copy; analyze timeout 180 s; health fields typed. |
| Health/doctor | `/api/health`: `zero_cost_ready`, `llm_provider`, Ollama status. New `backend/doctor.py` (READY/OPTIONAL/MISSING, `--probe`). |
| Scoring honesty | "Contract verification" label, liquidity 15, legal-determination disclaimer added. |
| OCR | Grayscale + autocontrast + ≤3× upscale preprocessing before Tesseract. |
| Docs | `ZERO_COST_SETUP.md`, `ARCHITECTURE.md`, `DEPENDENCY_LICENSES.md`, `FREE_PROVIDER_MATRIX.md`, README rewritten, `.env.example` documents all-optional model settings. |

**Rejected providers (probed live, unusable keyless):** URLhaus (401), PhishTank (429), AlienVault OTX (timeout). Sourcify v1 retired 2026-07-07 → v2 used.

## 4. Test results (this machine)

| Test | Result |
|---|---|
| Backend unit (`python -m unittest discover -s tests -v`) | **24/24 passed** (offline, stdlib) |
| HTTP integration (`python tests/integration_http.py`) | **38/38 passed** (incl. live Sourcify/OpenPhish/CoinGecko/GoPlus/DexScreener) |
| HTTP integration + local LLM (`OFFERCHECK_LIVE_LLM=1 ...`) | **39/39 passed** — real Ollama extraction + explanation |
| Frontend typecheck + production build (`npm run build`) | **passed** |
| UI smoke (`node scripts/ui-smoke.mjs`, built dist on :8000) | **22/22 passed**, zero uncaught JS errors, no 390 px overflow |
| `python doctor.py` | READY: Python, deps, Ollama+model; OPTIONAL: 4 keys; MISSING: Tesseract binary only |
| Demo end-to-end | A High/77 (conf 56) · B Very High/100 (conf 90) · C Low/0 (conf 78) · **D Not enough evidence (0/6)** · **E High/55, conf Medium 50, 3/6 available** |
| Live: contract verification without any key | verified, source=**Sourcify** |
| Live: website safety without any key | verified, source=**OpenPhish** (130 sites) |
| Live: market/price rule | verified — offer USD 30,000 vs observed USD 83,056/BTC |
| Live: GoPlus security + DexScreener liquidity | verified, non-demo ($32.7M) |
| Live: local Ollama | `heuristic+llm` + `summary=llm`, provider `ollama` |
| Rate limit, error shape, OCR 503, static serving, invalid input (×6) | passed |

## 5. Not tested / requiring configuration

| Item | Reason |
|---|---|
| Anthropic fallback path | No key on this machine (local Ollama path verified instead; code shares the same chain machinery). |
| Etherscan layer | No key; verified the chain continues Sourcify → RPC without it. Live keyed call untested. |
| Google Safe Browsing layer | No key; OpenPhish fallback verified live. Live keyed call untested. |
| Actual OCR extraction | Tesseract binary not installed; preprocessing code unexercised, honest 503 verified. |
| Voice input | Needs microphone + browser UI; feature detection/fallback verified in code. |
| Visual screenshot review | Screenshots captured by UI test; layout verified programmatically (DOM + zero overflow). |

## 6. Environment variables (all optional — demo mode needs none)

Copy `.env.example` to `backend/.env`. Full table in `README.md`; highlights:
`APP_MODE` · `LLM_PROVIDER` (`auto`/`ollama`/`anthropic`/`none`) · `OLLAMA_BASE_URL` · `OLLAMA_MODEL` · `LLM_TIMEOUT_SECONDS=120` · `ANTHROPIC_API_KEY` (optional) · `COINGECKO_API_KEY` (optional) · `ETHERSCAN_API_KEY` (optional extra layer) · `GOOGLE_SAFE_BROWSING_API_KEY` (optional extra layer) · tuning/limits.
Keys stay server-side; the browser only ever calls `/api/*`.

## 7. How to run

```bash
# Terminal 1 — backend
cd backend
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt     # Windows; Linux/macOS: source .venv/bin/activate
.venv\Scripts\uvicorn app.main:app --reload --port 8000
python doctor.py                                  # optional: capability check

# Terminal 2 — frontend (dev, proxies /api to :8000)
cd frontend && npm install && npm run dev         # http://localhost:5173
```

Single-server mode: `cd frontend && npm run build`, restart uvicorn — it serves `frontend/dist` at `/`.

```bash
# Tests
cd backend && python -m unittest discover -s tests -v
cd backend && python tests/integration_http.py
cd backend && OFFERCHECK_LIVE_LLM=1 python tests/integration_http.py   # slow: real local-model run
cd frontend && node scripts/ui-smoke.mjs           # with the server running
```

## 8. Known limitations

- Heuristic extraction is English-centred; messy/regional-language text needs the (free) local Ollama model.
- Supported contract networks: Ethereum, BNB Chain, Polygon, Arbitrum, Base; Solana/other are reported *unsupported*.
- Domain-age: some TLDs publish no RDAP → DNS fallback proves existence only (age stays unknown, never guessed).
- Free public APIs are rate-limited; results cached 10 minutes, failing hosts circuit-broken 60 s (failures never cached).
- Market comparison assumes 1 unit when none is stated and says so; FX = ECB reference rates, labelled.
- No database — reports live only in the browser tab's `sessionStorage`.
- CPU-only LLM: ~1–2 min per live analysis (frontend timeout 180 s); `LLM_PROVIDER=none` disables it.

## 9. Security notes (audited)

- No secrets in source; `.env` git-ignored; keys never reach the client; `/api/health` exposes no key values.
- URLs are **never fetched** — only the public hostname is looked up (SSRF-safe); IPs, localhost, credentials and odd ports rejected.
- Uploads: PNG/JPEG/WebP only, 5 MB + 25 MPixel caps, verified with Pillow, never executed; OCR language codes regex-validated.
- Inputs sanitised and length-limited; EVM/Solana address formats validated per network.
- LLM offer text delimited as untrusted data; output schema-validated + merge-guarded (chain needs an address, flags allowlisted, name-shaped identities only) and cannot influence scoring — unit-tested against prompt injection.
- Per-IP rate limit on live analysis and OCR (pruned table); circuit breaker prevents hammering failing services.
- Logs contain no offer text and no API keys. The app never asks for or stores seed phrases/private keys, and says so in the UI.
