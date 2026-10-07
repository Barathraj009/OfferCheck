# Zero-cost setup

OfferCheck runs completely on free/local resources. **No API key is required for any
verification check.** Keys listed in `.env.example` are optional extras that add redundancy or
raise rate limits; the app never stops working when they are absent.

## Minimum setup (0 rupees, 0 keys)

```bash
# Backend
cd backend
python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
.venv\Scripts\uvicorn app.main:app --reload --port 8000

# Frontend (dev)
cd frontend && npm install && npm run dev        # http://localhost:5173

# Or single server: cd frontend && npm run build, then restart uvicorn
# (it serves frontend/dist at http://localhost:8000)
```

Verify the machine: `cd backend && python doctor.py` (add `--probe` to test each free source
over the network). Status lines read `READY` / `OPTIONAL` / `MISSING`.

## What runs free, out of the box

| Check | Free source(s) used | Fallback chain |
|---|---|---|
| Contract verification | **Sourcify** (keyless) | Etherscan (optional key) → public RPC bytecode check |
| Token security scan | **GoPlus** (keyless) | reports unavailable if unreachable |
| Liquidity & trading | **DexScreener** (keyless, chain-scoped) | — |
| Market price | **CoinGecko** (keyless) | DexScreener by contract → Binance ticker → FX via Frankfurter/ECB |
| Domain age | **RDAP** (keyless) | DNS resolution (existence only — never invents an age) |
| Website safety | **Google Safe Browsing** (optional key) | **OpenPhish** community feed (keyless) |
| AI claim reading + explanation | **Local Ollama model** (free) | Anthropic API (optional key) → pure rule-based/template output |
| Screenshot OCR | local Tesseract | without it: clear message, type the text instead |

All lookups are cached (10 min default), de-duplicated, circuit-broken (a failing host is
skipped for 60 s after 3 failures) and individually time-limited — one dead source never blocks
the report. Missing data lowers **confidence**; it is never shown as "safe" and never as a
guilty verdict.

## Optional local AI (recommended for messy/regional-language offers)

```bash
# 1. Install Ollama (https://ollama.com) — MIT licensed, free
# 2. Pull a small model (~1.3 GB; CPU-friendly):
ollama pull llama3.2:1b
# 3. That's it. LLM_PROVIDER=auto (default) picks it up automatically.
```

- The app **never downloads models by itself**. If no model is installed, extraction stays
  rule-based and explanations use the template — with no error.
- A CPU takes ~40–90 s for one live analysis (extraction + explanation); the frontend waits up
  to 180 s. Results are cached for repeated inputs.
- `LLM_PROVIDER=ollama` forces local-only (never falls back to a paid API);
  `LLM_PROVIDER=none` disables the LLM entirely.
- The LLM only extracts claims and rewrites the explanation. **It never sets the score** —
  scoring is deterministic code (unit-tested).

## Optional keys (enhancement only, all have free tiers)

| Variable | Adds when set | Without it |
|---|---|---|
| `ETHERSCAN_API_KEY` | one more contract-verification layer | Sourcify + public RPCs verify |
| `GOOGLE_SAFE_BROWSING_API_KEY` | Google's URL threat lists | OpenPhish phishing feed |
| `COINGECKO_API_KEY` | higher CoinGecko rate limits | keyless CoinGecko + DexScreener/Binance fallbacks |
| `ANTHROPIC_API_KEY` | hosted LLM if no local model | local Ollama, then template summary |

Copy `.env.example` to `backend/.env` to use any of them. Keys stay server-side.

## Honest limits

- "Not found in this source" means the source answered with no record — **not** proof of fraud.
- Unavailable checks are shown as unavailable and lower confidence; they are never guessed.
- OCR needs the Tesseract binary installed (`winget install UB-Mannheim.TesseractOCR`); voice
  input uses the browser's own speech service (Chrome/Edge).
- Free APIs are rate-limited; if one is throttled the report still completes and says so.
