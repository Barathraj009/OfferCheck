# Free Provider Matrix

Every external dependency in OfferCheck, evaluated for **zero-cost operation**.
Probed live from this machine (2026-10) unless marked otherwise.

| Requirement | Current provider | Free? | Requires key? | Local alternative | Best fallback | Recommended choice |
| ----------- | ---------------- | ----- | ------------- | ----------------- | ------------- | ------------------ |
| LLM: claim extraction | Ollama (local) → Anthropic → heuristic | Yes (Ollama/models free; Anthropic paid) | No (Ollama) / Yes (Anthropic) | Ollama + open-weight model (`llama3.2:1b` present; `qwen3:4b` recommended) | Deterministic heuristic extractor (always available) | **Ollama local-first**, Anthropic optional, heuristic guaranteed |
| LLM: explanation rewrite | Ollama (local) → Anthropic → template | Same as above | Same | Same | Deterministic template summary (always available) | **Same chain** |
| OCR (screenshot text) | Tesseract + Pillow preprocessing | Yes, open source (Apache-2.0) | No | Tesseract on the server | Manual text entry in the UI | **Local Tesseract**, manual entry fallback |
| Speech-to-text | Browser Web Speech API (Chrome/Edge) | Yes (browser feature) | No | whisper.cpp / faster-whisper (optional, not bundled) | Manual text entry | **Browser speech** + editable transcript; local Whisper documented as optional |
| Market price / listing | CoinGecko free tier | Yes | No (free Demo key optional) | None (needs internet) | DexScreener (contract) → Binance ticker (symbol) → FX via Frankfurter | **CoinGecko primary**, DexScreener/Binance fallback |
| FX conversion (USD→INR/EUR/GBP) | Frankfurter (ECB reference rates) | Yes | No | — | Report USD only, labelled | **Frankfurter**, cached 6 h, labelled as ECB reference rate |
| Contract source verification | Sourcify v2 (keyless) → Etherscan V2 (free key) → public RPC | Yes | **No** (Sourcify) / optional free key (Etherscan) | Public RPC endpoints (bytecode existence) | "Unavailable" with reason | **Sourcify v2 primary** (zero-key), Etherscan optional enrichment |
| Contract existence (bytecode) | Public RPC `eth_getCode` (PublicNode, 1rpc.io, chain official) | Yes | No | — | "Unavailable" | **Public RPC**, 2–3 endpoints per chain, circuit-broken |
| Token security (honeypot, mint, tax…) | GoPlus Token Security | Yes | No | — | "Unavailable" (never guessed) | **GoPlus** (keyless), unchanged |
| Liquidity / DEX pairs | DexScreener chain-scoped `token-pairs/v1` | Yes | No | — | Distinguish `not_found` vs unavailable vs low | **DexScreener**, unchanged |
| Domain registration / age | RDAP (rdap.org bootstrap) | Yes | No | DNS A/AAAA lookup (stdlib) | DNS "resolves / does not resolve" evidence (no age) | **RDAP primary**, **DNS fallback** |
| Website safety / malicious URL | Google Safe Browsing (free key) → OpenPhish community feed | Yes | Optional free key (GSB) / **No** (OpenPhish) | — | Honest "not checked against threat lists" | **GSB if configured, else OpenPhish feed** |
| Blockchain explorer metadata (creator, tx) | Etherscan V2 multichain | Free key tier | Yes (free key) | — | Omitted (never claimed) | Optional enrichment only |
| Translation / regional explanation | LLM (local) | Yes | No | Ollama | English-only template text (stated in UI) | **Local LLM** when present |
| Database / storage | None (in-memory cache, browser session) | Yes | No | SQLite/file if ever needed | — | **None** — reports are not stored |
| Hosting | Local machine (uvicorn + Vite build) | Yes | No | Static `dist` behind any free host | — | **Local**; any static host works |

## Evaluation notes (why these were chosen)

- **Sourcify v2** (`GET /v2/contract/{chainId}/{address}`): keyless, returns `match` /
  `creationMatch` / `runtimeMatch` / `verifiedAt`. Verified live for USDT (chain 1);
  404 for unverified addresses. The legacy v1 API is retired (July 2026) — this project
  uses only v2. Makes contract verification **live with zero keys**.
- **Public RPC**: `eth_getCode` confirms a contract exists / has bytecode without any key.
  Endpoints vary in reliability by region (PublicNode/1rpc/official chain RPCs); two or
  three are tried per chain behind a circuit breaker. Confirmed working for ETH, BSC,
  Polygon, Arbitrum, Base.
- **OpenPhish community feed** (`openphish.com/feed.txt`): free, keyless, plain-text list
  of currently active phishing URLs (≈300+ entries, updated hourly). Confirmed fetching.
  Used only when Google Safe Browsing is not configured. URLhaus now requires an API key
  (401), PhishTank rate-limited our probe (429), AlienVault OTX timed out — all rejected.
- **DexScreener**: keyless, chain-scoped pair query (already fixed to `token-pairs/v1`),
  used as market-price fallback when CoinGecko errors or does not list a contract.
- **Binance public ticker** (`/api/v3/ticker/price`): keyless, confirmed live; rescues
  price checks for major symbols when CoinGecko is rate-limited. USD-only → converted
  with Frankfurter.
- **Frankfurter** (ECB rates): keyless FX for USD→INR/EUR/GBP; confirmed live (1 USD ≈ 96.4 INR
  at probe time). Data is the latest ECB reference rate (up to ~1 business day old) and is
  labelled as such in the report.
- **Ollama**: runs on this machine (installed, `llama3.2:1b` present). CPU-only here
  (~4 tokens/s → ~40 s per extraction), so `LLM_TIMEOUT_SECONDS` defaults to 120.
  Models are **never downloaded automatically**; `doctor.py` recommends one.
- **Rejected**: paid OCR/cloud vision, paid speech APIs, Etherscan-as-requirement,
  Google Safe Browsing as a requirement, any hosted database, CoinGecko as the single
  price source, URLhaus/PhishTank/OTX (keyed, rate-limited or unreachable from here).
- **Privacy**: URLs are never fetched; only hostnames are looked up. No offer text is
  sent to any service except the optional LLM (local Ollama by default — nothing leaves
  the machine). No seed phrases or private keys are ever accepted.

## Fallback chains (as implemented)

```text
LLM           Ollama (local)  →  Anthropic (optional key)  →  heuristic/template (always)
OCR           Tesseract (local, preprocessed)  →  manual text entry
Voice         Browser Web Speech API (editable transcript)  →  manual text entry
Market        CoinGecko  →  DexScreener (by contract)  →  Binance ticker (by symbol)  →  unavailable
FX            Frankfurter (only used by DexScreener/Binance paths)
Contract      Sourcify v2  →  Etherscan V2 (optional free key)  →  public RPC (bytecode)  →  unavailable
Security      GoPlus  →  unavailable
Liquidity     DexScreener  →  unavailable
Domain age    RDAP  →  DNS resolution evidence  →  unavailable
Website       Google Safe Browsing (optional key)  →  OpenPhish feed  →  unavailable
```

Every chain failure **reduces confidence; it never fabricates a result**.
