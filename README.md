# OfferCheck - AI-Powered Crypto Scam Verification and Risk Assessment Platform

Helps ordinary people **verify a cryptocurrency offer before sending money**. The user submits an offer (text, screenshot, website, token name, contract address, or voice). The system extracts the claims, checks them against market, blockchain, security, liquidity and website sources, scores risk with **deterministic rules**, calculates **confidence separately**, and explains the result in plain language.

It is a risk assessment and verification aid - **not** financial, legal or investment advice, and it never accuses anyone of a crime.

**Pipeline:** `Input -> claim extraction -> verification (6 checks) -> rule-based scoring -> confidence -> explainable report`
The LLM (optional, local-first) only extracts claims and rewrites verified findings. It never sets the score.

**Fully zero-cost:** every verification check works with **no API keys** (Sourcify, public RPCs, GoPlus, DexScreener, RDAP, OpenPhish, CoinGecko, Binance, Frankfurter + a free local Ollama model for the AI parts). See `ZERO_COST_SETUP.md`; run `python doctor.py` to check your machine.

## What is live vs demo

| Feature | Status |
|---|---|
| Text offer -> claim extraction (rule-based, English) | Live, offline, no key |
| Claim extraction for messy / regional-language text | Live **with a free local Ollama model** (or optional `ANTHROPIC_API_KEY`); else rule-based only |
| Rule-based risk score, confidence, report, checklist | Live, offline |
| Contract verification (Sourcify v2 → public RPC bytecode) | Live **keyless**; `ETHERSCAN_API_KEY` adds one more layer |
| GoPlus contract security, DexScreener liquidity, RDAP domain age | Live (keyless) |
| Market price (CoinGecko → DexScreener → Binance; FX via Frankfurter) | Live (keyless) |
| Website safety (OpenPhish phishing feed) | Live **keyless**; `GOOGLE_SAFE_BROWSING_API_KEY` adds Google's lists |
| AI explanation of findings | Live with local Ollama / optional Anthropic key; otherwise a fixed template |
| Screenshot OCR | Live, needs Tesseract installed on the server (preprocessed: grayscale, autocontrast, upscale) |
| Voice input | Browser Web Speech API (Chrome/Edge); 10 Indian languages selectable |
| **Demo mode** (5 sample scenarios) | **Simulated data, always labelled "DEMO DATA, NOT LIVE VERIFICATION"** |

Demo mode with *your own* input runs claim extraction and text rules, but every external check shows "Unavailable" because demo mode has no live data. Mock data is never presented as real.

## Tech stack
Python 3.11+, FastAPI, httpx, Pillow + pytesseract (OCR) | React 18, TypeScript, Vite, Tailwind CSS 3. Optional: Ollama (local LLM). Licenses: `DEPENDENCY_LICENSES.md`.

## Setup

```bash
# Backend (terminal 1)
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (terminal 2)
cd frontend
npm install
npm run dev                                              # http://localhost:5173  (proxies /api to :8000)

# Check this machine (READY / OPTIONAL / MISSING per capability)
cd backend && python doctor.py            # add --probe to test the free sources over the network
```

Optional single-server deploy: `cd frontend && npm run build`, then restart uvicorn - it serves `frontend/dist` at `/`.

Optional local AI (free): install [Ollama](https://ollama.com) and `ollama pull llama3.2:1b`. The app never downloads models itself.

OCR: install Tesseract (`sudo apt install tesseract-ocr`, `brew install tesseract`, or `winget install UB-Mannheim.TesseractOCR`). For other languages add packs, e.g. `tesseract-ocr-hin`, `-tam`, `-tel`.

## Environment variables (`backend/.env`; see `.env.example` — everything is optional)
| Variable | Purpose |
|---|---|
| `APP_MODE` | `demo` (default) or `live`; users can switch in the UI |
| `LLM_PROVIDER` | `auto` (Groq → OpenRouter → Gemini → Ollama → deterministic), `groq`, `openrouter`, `gemini`, `ollama`, `none` |
| `GROQ_API_KEY`, `GROQ_MODEL` | Primary cloud AI (default: `llama-3.3-70b-versatile`; get free key at https://console.groq.com/keys) |
| `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` | Secondary cloud AI (default: `meta-llama/llama-3.3-70b-instruct:free`) |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Tertiary cloud AI (default: `gemini-2.5-flash`) |
| `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT_SECONDS` | Local offline AI (runs locally, zero-cost, no key needed; 20s timeout guard) |
| `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` | Optional legacy hosted LLM fallback |
| `COINGECKO_API_KEY` | Optional (free Demo key raises rate limits) |
| `ETHERSCAN_API_KEY` | Optional extra contract-verification layer (Sourcify + RPC work without it) |
| `GOOGLE_SAFE_BROWSING_API_KEY` | Optional website-safety layer (OpenPhish feed is used without it) |
| `HTTP_TIMEOUT_SECONDS`, `CACHE_TTL_SECONDS`, `MAX_INPUT_CHARS`, `MAX_UPLOAD_BYTES`, `RATE_LIMIT_PER_10MIN`, `ALLOWED_ORIGINS` | Tuning and safety limits |

Keys live only in the backend environment and never reach the browser.

## Demo mode
Run with no keys. On **Check an offer**, press a sample button:
- **A - Cheap Bitcoin**: ~41% below the (simulated) market price, urgency, referral, 4-day-old site -> High Risk, Medium confidence, partial coverage.
- **B - Suspicious token**: mintable, 35% sell tax, $3.2k liquidity, concentrated holders, new site, one source "rate limited" -> Very High Risk, High confidence.
- **C - Ordinary offer**: ETH at market rate, no pressure -> Low Risk.
- **D - Too little to verify**: a vague message with no asset/link/address -> "Not enough evidence", Low confidence (0 checks).
- **E - Partial verification**: half the sources down -> score continues from real evidence (High/55) while confidence drops to Medium (3/6 checks).

## Live mode
Choose **Live verification** (or `APP_MODE=live`). Try your own text, a contract address + network, and a website. Example: token `Bitcoin`, text `Selling 1 BTC for $30,000, pay within 1 hour`.

## Scoring (`backend/app/scoring.py`)
Each rule has fixed points, e.g. price >20% below market 28-40, honeypot 40, unlimited mint 35, dangerous owner powers 20-30, sell tax >10/30/50% -> 20/30/35, liquidity <$5k 25 / <$25k 15 / no pairs 15, guaranteed language 25, unrealistic return 15-25, referral 12, urgency 10, domain <7/<30 days 20/15, website flagged by threat feed 45, secret-credential request 40, asset not found 12, contract source unverified 12, concentration 15-20. Points are summed and capped at 100. Levels: 0-24 Low, 25-49 Moderate, 50-79 High, 80-100 Very High; "Not enough evidence" if nothing could be checked and nothing was flagged.
Confidence = share of applicable check weight that returned data, scaled by how many checks the input allowed, minus conflict penalties. High >= 65, Medium >= 35.
The report's **"Why this score?"** table shows Rule → Evidence → Points → Why for every point.

## Architecture
```
frontend (React)  --/api-->  FastAPI (app/main.py)
                               analysis.py  orchestrator (steps 1-4)
                                 extraction.py (+ llm.py optional)   claims
                                 sources/base.py                     provider chain (fallback, stop_on, provenance)
                                 sources/{market,chain,web}.py       verification adapters
                                 sources/common.py                   cache, de-dup, circuit breaker, timeouts
                                 demo.py                             labelled simulated fixtures (5 scenarios)
                                 scoring.py                          deterministic rules, confidence, coverage
                                 explain.py                          template summary, checklist, disclaimers
```
Details: `ARCHITECTURE.md`. Add a new source by composing providers with `run_chain`, registering it in `analysis.py`, and adding a rule in `scoring.py`.

## Tests
```bash
cd backend && python -m unittest discover -s tests -v    # 24 unit tests, stdlib only, no network
cd backend && python tests/integration_http.py           # 38 HTTP checks: demo + live keyless APIs + error paths
cd backend && OFFERCHECK_LIVE_LLM=1 python tests/integration_http.py   # + one real local-Ollama run (slow on CPU)
cd frontend && node scripts/ui-smoke.mjs                 # 22 browser checks (needs APP_URL running)
```
Unit tests cover demo end-to-end (A-E), score traceability, provider-chain fallback/`stop_on`/circuit breaker, LLM output guards (injection), model-pick regression, unavailable != safe, "not found" is not a scam verdict, confidence vs risk, validation, unsupported network, extraction, prompt-injection text, and scenario-by-id requests. The integration script adds HTTP-level checks (invalid input, rate limit, OCR degradation, static frontend, error shape) plus live Sourcify/OpenPhish/CoinGecko/GoPlus/DexScreener verification. The UI script drives the real pages in a browser: sample -> analyse -> report, "Why this score?" table, live mode, mobile width, JS-error monitoring.

Current status, what was fixed, and what remains: see `PROJECT_STATUS.md`. Provider evaluation notes: `FREE_PROVIDER_MATRIX.md`.

## Limitations
- Heuristic extraction is English-centred; messy/regional-language text needs the (free) local Ollama model.
- Contract networks: Ethereum, BNB Chain, Polygon, Arbitrum, Base. Solana/others are reported unsupported. EVM address checksum (EIP-55) is not verified.
- Domain registrable-name detection is heuristic; some TLDs publish no RDAP data (then DNS fallback answers "resolves / does not resolve" without inventing an age).
- Free public APIs are rate-limited; results are cached for 10 minutes and a failing host is circuit-broken for 60 s.
- Market comparison assumes 1 unit when no quantity is stated (and says so); FX conversions use ECB reference rates and are labelled.
- Reports are not stored (no database); the last report is kept in the browser tab's session only.
- On a CPU-only machine a live analysis with the LLM takes ~1-2 minutes (frontend waits up to 180 s).

## Security notes
Secrets only in server env; inputs sanitised and length-limited; addresses validated per network; URLs validated (http/https only, no IPs/localhost/credentials/odd ports) and **never fetched** - only their public hostname is looked up (SSRF-safe); uploads restricted to PNG/JPEG/WebP, size and pixel limits, verified with Pillow, preprocessed but never executed; offer text is delimited as untrusted data for the LLM and LLM output is schema-validated and cannot affect scoring (unit-tested against prompt injection); per-IP rate limit on live analysis and OCR; logs contain no offer text or secrets. The app never asks for seed phrases or private keys.
