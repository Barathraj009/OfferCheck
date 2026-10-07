# Dependency & license inventory (OfferCheck)

All licenses below are **permissive** (MIT/BSD/Apache/PSF/MPL) — no copyleft obligations for
using, modifying or deploying this project. Verified from installed package metadata on this
machine (`importlib.metadata`), not guessed.

## Backend runtime (`backend/requirements.txt` + transitive)

| Package | License | Role |
|---|---|---|
| fastapi | MIT | Web framework |
| starlette (via fastapi) | BSD-3-Clause | ASGI base |
| uvicorn | BSD-3-Clause | ASGI server |
| httptools, uvloop, watchfiles, websockets, PyYAML (via `uvicorn[standard]`) | MIT / BSD-3-Clause | optional server accelerators |
| httpx | BSD-3-Clause | Async HTTP client for all source lookups |
| httpcore, anyio, idna, certifi, sniffio, h11 | BSD-3-Clause / MIT / MPL-2.0 | HTTP transport stack (certifi is MPL-2.0) |
| pydantic, pydantic-core, annotated-types, typing-extensions | MIT / PSF-2.0 | Request/response validation |
| python-multipart | Apache-2.0 | File uploads (OCR) |
| pillow | MIT-CMU | Image decoding, OCR preprocessing |
| pytesseract | Apache-2.0 | Python wrapper for the Tesseract OCR binary |
| python-dotenv | BSD-3-Clause | Optional `.env` loading |
| click, packaging | BSD-3-Clause / Apache-2.0 OR BSD-2-Clause | CLI/metadata utilities |

**External binaries (not Python packages):**
- **Tesseract OCR engine** (optional feature) — Apache-2.0, installed separately by the user
  (`winget install UB-Mannheim.TesseractOCR` / `apt install tesseract-ocr`). Not bundled.
- **Ollama** (optional local LLM runtime) — MIT, installed separately by the user. Not bundled;
  the app never auto-downloads models or binaries.

## Frontend (`frontend/package.json`)

| Package | License | Role |
|---|---|---|
| react, react-dom | MIT | UI runtime |
| @types/react, @types/react-dom | MIT | TypeScript types (dev) |
| typescript | Apache-2.0 | Type checking (dev) |
| vite, @vitejs/plugin-react | MIT | Build tooling (dev) |
| tailwindcss, postcss, autoprefixer | MIT | Styling (dev) |

Browsers used by the UI smoke test (Chrome/Edge) are pre-installed test tools, not project
dependencies.

## Third-party data services (used over HTTPS at runtime, no code bundled)

Sourcify, public JSON-RPC endpoints, Etherscan (optional), GoPlus, DexScreener, RDAP (rdap.org),
OpenPhish, Google Safe Browsing (optional), CoinGecko, Binance, Frankfurter/ECB, Ollama local API.
Each has its own terms of use; all are used keyless (or with the user's own free key) for
personal verification queries. See `FREE_PROVIDER_MATRIX.md`.

## Project code

Project source in this repository: provided as-is for the user's own use; no third-party code
was copied into `app/` or `src/`.
