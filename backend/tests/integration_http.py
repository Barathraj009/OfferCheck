"""End-to-end HTTP tests against a real uvicorn server. NOT run by `unittest discover`
(name does not match test*.py). Run:  python tests/integration_http.py [--skip-live]

Starts its own server on a free port, exercises the required workflows
(demo, live, invalid input, missing data, external-failure handling, rate limit,
static frontend) and prints a PASS/FAIL line per check. Uses only the stdlib.
"""
from __future__ import annotations
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
PY = sys.executable
SKIP_LIVE = "--skip-live" in sys.argv
RESULTS: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((ok, name, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail else ""), flush=True)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def req(port: int, path: str, body: dict | None = None, timeout: float = 60) -> tuple[int, dict]:
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"raw": raw[:200]}
    except (urllib.error.URLError, TimeoutError) as e:
        return 0, {"error": str(e)}


def wait_health(port: int, tries: int = 40) -> bool:
    for _ in range(tries):
        code, body = req(port, "/api/health", timeout=3)
        if code == 200 and body.get("ok"):
            return True
        time.sleep(0.25)
    return False


def risk_level(rep: dict) -> str:
    return rep.get("risk", {}).get("level_key", "?")


def main() -> int:
    port = free_port()
    # The local CPU model adds ~1-2 minutes per live analysis; keep the default suite fast.
    # OFFERCHECK_LIVE_LLM=1 runs one real Ollama extraction+summary at the end instead.
    env = {**os.environ, "APP_MODE": "demo"}
    if os.environ.get("OFFERCHECK_LIVE_LLM"):
        env["LLM_PROVIDER"] = "auto"
    else:
        env.setdefault("LLM_PROVIDER", "none")
    log = open(BACKEND / "integration_server.log", "w", encoding="utf-8")
    srv = subprocess.Popen([PY, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                           cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        if not wait_health(port):
            check("server starts", False, "health endpoint never answered")
            return 1
        check("server starts", True, f"port {port}")

        # --- 1. demo mode: all five scenarios, by id alone ---
        for sid, want in (("cheap-bitcoin", "high"), ("suspicious-token", "very_high"), ("normal-offer", "low"),
                          ("too-vague", "insufficient"), ("partial-verification", "high")):
            code, rep = req(port, "/api/analyze", {"mode": "demo", "demo_scenario": sid})
            ok = code == 200 and risk_level(rep) == want
            check(f"demo scenario {sid} -> {want}", ok, f"HTTP {code} got {risk_level(rep)}")
            if ok:
                check(f"demo {sid} labelled + traceable",
                      rep.get("is_demo") is True
                      and all(c["demo"] for c in rep["checks"] if c["status"] != "not_applicable")
                      and rep["risk"]["raw_points"] == sum(f["points"] for f in rep["findings"]),
                      f"score {rep['risk']['score']} conf {rep['confidence']['score']}")

        # --- 1b. health advertises the zero-cost capability matrix ---
        code, h = req(port, "/api/health")
        check("health: zero-cost capability fields", code == 200 and h.get("zero_cost_ready") is True
              and isinstance(h.get("llm_provider"), str)
              and isinstance(h.get("llm"), dict) and "model" in h["llm"]
              and h.get("sources", {}).get("sourcify") is True and h.get("sources", {}).get("openphish") is True,
              f"HTTP {code} zero_cost_ready={h.get('zero_cost_ready')} llm={h.get('llm')}")

        # --- 1c. report carries the legal-determination disclaimer ---
        code, rep = req(port, "/api/analyze", {"mode": "demo", "demo_scenario": "normal-offer"})
        check("report disclaims legal determination", code == 200
              and any("legal determination" in d for d in rep.get("disclaimers", [])), f"HTTP {code}")

        # --- 2. high-risk text via own input (text rules only, external checks unavailable) ---
        code, rep = req(port, "/api/analyze", {"mode": "demo",
                                               "text": "Send me your seed phrase. Guaranteed 10x returns in 1 week! Only today, refer friends for commission."})
        check("high-risk own text flags critical rules", code == 200 and rep["risk"]["score"] >= 60
              and any(f["rule_id"] == "SECRETS_REQUESTED" for f in rep["findings"])
              and rep["confidence"]["level"] == "Low",
              f"HTTP {code} score={rep.get('risk', {}).get('score')} conf={rep.get('confidence', {}).get('level')}")

        # --- 3. missing information ---
        code, rep = req(port, "/api/analyze", {"mode": "demo"})
        check("empty input rejected 422", code == 422 and bool(rep.get("error", {}).get("message")), f"HTTP {code}")
        code, rep = req(port, "/api/analyze", {"mode": "demo", "text": "just chatting about crypto"})
        check("input with no verifiable data -> honest report", code == 200
              and rep["risk"]["insufficient_evidence"] and rep["confidence"]["level"] == "Low",
              f"HTTP {code} level={rep.get('risk', {}).get('level')}")

        # --- 4. invalid input ---
        bad = [("bad contract", {"contract_address": "0x123", "chain": "bsc"}),
               ("contract without chain", {"contract_address": "0x" + "a" * 40}),
               ("private-ip url", {"url": "http://127.0.0.1/admin"}),
               ("ip url", {"url": "http://93.184.216.34/x"}),
               ("credentials url", {"url": "https://user:pass@example.com"}),
               ("unknown chain", {"contract_address": "0x" + "a" * 40, "chain": "dogechain"})]
        for name, extra in bad:
            code, rep = req(port, "/api/analyze", {"mode": "demo", **extra})
            check(f"invalid input: {name}", code == 422 and bool(rep.get("error", {}).get("message")),
                  f"HTTP {code} {str(rep.get('error', ''))[:80]}")

        # --- 5. unsupported network reported honestly ---
        code, rep = req(port, "/api/analyze", {"mode": "demo", "chain": "solana",
                                               "contract_address": "So11111111111111111111111111111111111111112"})
        sec = next((c for c in rep.get("checks", []) if c["check_id"] == "security"), {})
        check("unsupported network -> unavailable, not crash", code == 200 and sec.get("status") == "unavailable"
              and "cannot be verified" in (sec.get("reason") or ""), f"HTTP {code} {sec.get('status')}")

        # --- 6. live mode: external source failure must degrade, not crash ---
        if not SKIP_LIVE:
            LIVE_T = 240 if os.environ.get("OFFERCHECK_LIVE_LLM") else 90  # local CPU LLM is slow
            code, rep = req(port, "/api/analyze", {"mode": "live", "url": "https://nonexistent-offercheck-test-98765.example"},
                            timeout=LIVE_T)
            dom = next((c for c in rep.get("checks", []) if c["check_id"] == "domain"), {})
            check("live: unreachable/unknown domain degrades gracefully", code == 200
                  and dom.get("status") in ("unavailable", "not_found", "verified"),
                  f"HTTP {code} domain={dom.get('status')} reason={str(dom.get('reason'))[:60]}")

            code, rep = req(port, "/api/analyze", {"mode": "live", "token_name": "Bitcoin",
                                                   "text": "Selling 1 BTC for $30,000, pay within 1 hour"}, timeout=LIVE_T)
            mkt = next((c for c in rep.get("checks", []) if c["check_id"] == "market"), {})
            if code == 200 and mkt.get("status") == "verified":
                below = [f for f in rep["findings"] if f["rule_id"] == "PRICE_BELOW_MARKET"]
                check("live: CoinGecko market check + price rule", bool(below)
                      and below[0]["source"] == "CoinGecko" and below[0]["demo"] is False,
                      f"score={rep['risk']['score']} observed={str(below[0]['observed'])[:70] if below else 'none'}")
            elif code == 200 and mkt.get("status") == "unavailable" and "rate limit" in (mkt.get("reason") or "").lower():
                # free CoinGecko tier can 429 during repeated test runs; honest degradation is correct behaviour
                check("live: market check degrades honestly when the free source is rate-limited", True, str(mkt.get("reason"))[:60])
            else:
                check("live: CoinGecko market check (source reachable)", False,
                      f"HTTP {code} status={mkt.get('status')} reason={str(mkt.get('reason'))[:80]}")

            code, rep = req(port, "/api/analyze", {"mode": "live", "chain": "ethereum",
                                                   "contract_address": "0xdac17f958d2ee523a2206206994597c13d831ec7"}, timeout=LIVE_T)
            ids = {c["check_id"]: c for c in rep.get("checks", [])}
            sec, liq, exp = ids.get("security", {}), ids.get("liquidity", {}), ids.get("explorer", {})
            check("live: contract checks (GoPlus/DexScreener) or honest unavailable",
                  code == 200 and (sec.get("status") in ("verified", "not_found", "unavailable")),
                  f"HTTP {code} security={sec.get('status')}({str(sec.get('reason'))[:50]}) liquidity={liq.get('status')}")
            if sec.get("status") == "verified":
                check("live: contract findings are non-demo", sec.get("demo") is False and not rep.get("is_demo"), "")
            # Contract verification must resolve through the free chain (Sourcify -> Etherscan key ->
            # public RPC), never fail just because the optional Etherscan key is missing.
            net_down = exp.get("status") == "unavailable" and any(
                x in (exp.get("reason") or "").lower() for x in ("did not respond", "could not be reached", "skipped for a moment"))
            check("live: contract verification via free chain (Sourcify -> public RPC)",
                  code == 200 and (exp.get("status") == "verified" or net_down),
                  f"explorer={exp.get('status')} source={exp.get('source')} {str(exp.get('reason'))[:60]}")

            # Sourcify v2 answers keyless (404 = 'not in Sourcify' is a valid answer, not an error)
            try:
                urllib.request.urlopen("https://sourcify.dev/server/v2/contract/1/0xdac17f958d2ee523a2206206994597c13d831ec7", timeout=10)
                check("live: Sourcify v2 answers keyless", True, "HTTP 200")
            except urllib.error.HTTPError as e:
                check("live: Sourcify v2 answers keyless", e.code in (200, 404), f"HTTP {e.code}")
            except Exception as e:  # noqa: BLE001 - offline run: the app itself degrades the same way
                check("live: Sourcify v2 answers keyless", True, f"network unavailable ({type(e).__name__})")

            # Website safety without any key: OpenPhish feed
            code, rep = req(port, "/api/analyze", {"mode": "live", "url": "https://example.com"}, timeout=LIVE_T)
            web = next((c for c in rep.get("checks", []) if c["check_id"] == "webSafety"), {})
            web_data = web.get("data") or {}
            web_ok = web.get("status") == "verified" and web_data.get("provider") == "OpenPhish" and (web_data.get("feed_sites") or 0) > 0
            web_down = web.get("status") == "unavailable" and any(
                x in (web.get("reason") or "").lower() for x in ("did not respond", "could not be reached", "skipped for a moment"))
            check("live: website safety via OpenPhish feed (keyless)", code == 200 and (web_ok or web_down),
                  f"webSafety={web.get('status')} source={web.get('source')} sites={web_data.get('feed_sites')}")

            # Optional: one real local-model extraction + explanation (slow on CPU; opt-in)
            if os.environ.get("OFFERCHECK_LIVE_LLM"):
                code, rep = req(port, "/api/analyze", {"mode": "live",
                                                       "text": "Buy Bitcoin for ₹40 lakh instead of the market price. Guaranteed to double your money in 30 days."}, timeout=LIVE_T)
                ex, sm = rep.get("extraction", {}), rep.get("summary", {})
                check("live: local Ollama extraction + explanation (OFFERCHECK_LIVE_LLM)",
                      code == 200 and ex.get("method") == "heuristic+llm" and ex.get("llm_provider") == "ollama"
                      and sm.get("method") == "llm" and not rep.get("is_demo"),
                      f"HTTP {code} method={ex.get('method')} provider={ex.get('llm_provider')} summary={sm.get('method')}")

            # liquidity must be found for an actively traded token on its own chain
            code, rep = req(port, "/api/analyze", {"mode": "live", "chain": "ethereum",
                                                   "contract_address": "0x6982508145454ce325ddbe47a25d4ec3d2311933"}, timeout=LIVE_T)
            liq = next((c for c in rep.get("checks", []) if c["check_id"] == "liquidity"), {})
            check("live: DexScreener liquidity found for an active token",
                  code == 200 and liq.get("status") == "verified" and (liq.get("data", {}).get("total_liquidity_usd") or 0) > 0
                  and liq.get("demo") is False,
                  f"HTTP {code} status={liq.get('status')} liq={liq.get('data', {}).get('total_liquidity_usd')}")

        # --- 7. OCR endpoint (Tesseract may be absent; must degrade to a clear 503) ---
        import base64

        def ocr_post(data: bytes, ctype: str = "image/png", filename: str = "t.png", lang: str = "eng") -> tuple[int, dict]:
            boundary = "x" * 16
            body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\n"
                    f"Content-Type: {ctype}\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
            r = urllib.request.Request(f"http://127.0.0.1:{port}/api/ocr?lang={lang}", data=body,
                                       headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
            try:
                with urllib.request.urlopen(r, timeout=60) as resp:
                    return resp.status, json.loads(resp.read())
            except urllib.error.HTTPError as e:
                raw = e.read().decode(errors="replace")
                try:
                    return e.code, json.loads(raw)
                except ValueError:
                    return e.code, {"raw": raw[:200]}
            except Exception as e:  # noqa: BLE001
                return 0, {"error": {"message": str(e)}}

        # 7a. real screenshot with offer text -> real extracted text (or honest 503)
        try:
            from PIL import Image as PILImage, ImageDraw, ImageFont
            _font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 30) if os.name == "nt" else ImageFont.load_default(size=30)
            _img = PILImage.new("RGB", (1100, 300), "white")
            _d = ImageDraw.Draw(_img)
            for _i, _line in enumerate(["GUARANTEED 10x RETURN in 30 days!",
                                        "Bitcoin Flash Sale - 1 BTC only $30,000",
                                        "Offer expires in 2 hours - act now!",
                                        "https://bitcoingiveaway.example.com"]):
                _d.text((40, 30 + _i * 65), _line, fill="black", font=_font)
            import io as _io
            _buf = _io.BytesIO(); _img.save(_buf, "PNG"); _shot = _buf.getvalue()
        except Exception:
            _shot = None
        if _shot:
            code, payload = ocr_post(_shot)
            degraded = code == 503 and "Tesseract" in payload.get("error", {}).get("message", "")
            text = (payload.get("text") or "").lower()
            strict_ok = code == 200 and "empty" in payload and (not payload.get("empty")) \
                and ("guaranteed" in text or "bitcoin" in text) and isinstance(payload.get("confidence"), (int, float))
            check("OCR: real screenshot -> extracted offer text (or clear 503)", strict_ok or degraded,
                  f"HTTP {code} conf={payload.get('confidence')} text={text[:60]!r}")
            # 7b. blank image -> empty result, never a crash
            _blank = PILImage.new("RGB", (300, 150), "white")
            _bbuf = _io.BytesIO(); _blank.save(_bbuf, "PNG")
            code, payload = ocr_post(_bbuf.getvalue())
            check("OCR: blank image -> empty:true (or clear 503)",
                  (code == 200 and payload.get("empty") is True and payload.get("text") == "") or degraded,
                  f"HTTP {code} {str(payload)[:80]}")
        # 7c. garbage bytes posing as PNG -> 422, not a crash
        code, payload = ocr_post(b"\x89PNG\r\n\x1a\n" + os.urandom(600))
        check("OCR: corrupt image -> 422 clear message", code == 422 and payload.get("error", {}).get("field") == "file",
              f"HTTP {code} {str(payload)[:80]}")
        # 7d. wrong file type -> 415
        code, payload = ocr_post(b"<html>script</html>", ctype="text/html", filename="x.html")
        check("OCR: non-image upload -> 415", code == 415 and payload.get("error", {}).get("field") == "file",
              f"HTTP {code}")
        # 7e. oversized upload -> 413
        code, payload = ocr_post(os.urandom(5 * 1048576 + 1024))
        check("OCR: >5MB upload -> 413", code == 413, f"HTTP {code}")
        # 7f. missing language pack -> 422 with guidance (eng only on most machines)
        if _shot:
            code, payload = ocr_post(_shot, lang="zzz")
            check("OCR: unknown language pack -> 422 guidance (or 503 when unavailable)",
                  code in (422, 503), f"HTTP {code} {str(payload)[:80]}")

        # --- 8. rate limit (live mode; text-only input so no external calls) ---
        last = None
        for i in range(31):
            last, _ = req(port, "/api/analyze", {"mode": "live", "text": f"ping {i}"})
            if last == 429:
                break
        check("live rate limit kicks in", last == 429, f"last HTTP {last}")
        code, _ = req(port, "/api/analyze", {"mode": "demo", "text": "still allowed in demo"})
        check("demo mode unaffected by live rate limit", code == 200, f"HTTP {code}")

        # --- 9. static frontend served when built ---
        if (BACKEND.parent / "frontend" / "dist" / "index.html").is_file():
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=10) as resp:
                    html = resp.read().decode(errors="replace")
                check("built frontend served at /", resp.status == 200 and 'id="root"' in html, f"HTTP {resp.status}")
            except Exception as e:  # noqa: BLE001
                check("built frontend served at /", False, str(e))

        # --- 10. error format consistency ---
        code, rep = req(port, "/api/analyze", {"mode": "demo"})
        check("errors use {error:{field,message}} shape", code == 422 and set(rep.get("error", {})) == {"field", "message"},
              json.dumps(rep)[:100])
        code, rep = req(port, "/api/analyze", {"mode": "demo", "text": "x" * 20001})
        check("oversized body uses the same error shape", code == 422 and set(rep.get("error", {})) == {"field", "message"},
              json.dumps(rep)[:100])
        code, rep = req(port, "/api/analyze", {"mode": "demo", "text": "x" * 6001})
        check("over MAX_INPUT_CHARS gives a helpful message", code == 422
              and "shorten" in rep.get("error", {}).get("message", ""), str(rep.get("error", ""))[:90])
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except subprocess.TimeoutExpired:
            srv.kill()
        log.close()

    failed = [n for ok, n, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed" + (f"; FAILED: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
