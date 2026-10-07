/* UI smoke test: drives headless Chrome over CDP with Node's built-in WebSocket (no deps).
 *
 * Usage:  node scripts/ui-smoke.mjs
 * Requires: backend on :8000 and `npm run dev` on :5173 (or built dist served by uvicorn).
 * Verifies: pages render, sample -> analyse -> report flow works, error states show,
 * no uncaught JS errors, no horizontal overflow at 390px, and writes screenshots to scripts/out/.
 */
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync, existsSync, rmSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "out");
const APP = process.env.APP_URL || "http://localhost:5173";
const PORT = 9333;
const CHROME = [
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
].find((p) => existsSync(p));

const results = [];
const check = (name, ok, detail = "") => {
  results.push([ok, name]);
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  [${detail}]` : ""}`);
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const profile = join(process.env.TEMP || "/tmp", "offercheck-ui-profile");
try { rmSync(profile, { recursive: true, force: true }); } catch { /* fresh profile */ }
mkdirSync(OUT, { recursive: true });

const chrome = spawn(CHROME, [
  "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
  `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, "--window-size=1280,900",
  "about:blank",
], { stdio: "ignore" });

const ws = await (async () => {
  for (let i = 0; i < 40; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const page = list.find((t) => t.type === "page");
      if (page) return new WebSocket(page.webSocketDebuggerUrl);
    } catch { /* not up yet */ }
    await sleep(250);
  }
  throw new Error("Chrome CDP did not come up");
})();

let seq = 0;
const pending = new Map();
const jsErrors = [];
ws.addEventListener("message", (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  if (m.method === "Runtime.exceptionThrown") {
    const d = m.params.exceptionDetails;
    jsErrors.push(d.exception?.description || d.text || "unknown exception");
  }
  if (m.method === "Log.entryAdded" && m.params.entry.level === "error") {
    const src = m.params.entry.source;
    if (src !== "network") jsErrors.push(`${src}: ${m.params.entry.text}`);
  }
});
await new Promise((r) => ws.addEventListener("open", r, { once: true }));
const send = (method, params = {}) => new Promise((resolve) => {
  const id = ++seq;
  pending.set(id, resolve);
  ws.send(JSON.stringify({ id, method, params }));
});
const evalJs = async (expression) => {
  const r = await send("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  return r.result?.result?.value;
};
const nav = async (url) => {
  await send("Page.navigate", { url });
  for (let i = 0; i < 60; i++) {
    const st = await evalJs("document.readyState");
    if (st === "complete") return;
    await sleep(250);
  }
  throw new Error("load timeout " + url);
};
const shot = async (name) => {
  const r = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(OUT, name), Buffer.from(r.result.data, "base64"));
};
const waitFor = async (expression, tries = 60) => {
  for (let i = 0; i < tries; i++) {
    if (await evalJs(expression)) return true;
    await sleep(250);
  }
  return false;
};

try {
  await send("Page.enable"); await send("Runtime.enable"); await send("Log.enable");

  // 1. Home renders
  await nav(APP + "/#/"); await sleep(800);
  check("home renders headline", (await evalJs("document.querySelector('h1')?.textContent || ''")).includes("Check the offer"));
  check("home shows disclaimers in footer", (await evalJs("document.body.innerText")).includes("not financial"));

  // 2. Check page + empty submit -> client-side validation message
  await nav(APP + "/#/check"); await sleep(1000);
  const scenariosShown = await waitFor("document.querySelectorAll('button[title]').length >= 3");
  check("sample scenario buttons load", scenariosShown);
  await evalJs("document.querySelector('form button[type=submit]')?.click()");
  await sleep(300);
  check("empty form shows a visible error", (await evalJs("document.body.innerText")).includes("Add something to check"));

  // 3. Sample load fills the form
  await evalJs("[...document.querySelectorAll('button')].find(b => b.textContent.includes('Demo B'))?.click()");
  await sleep(300);
  check("loading a sample fills the form", (await evalJs("document.querySelector('#text')?.value || ''")).includes("MoonRocket"));
  check("mode switched to demo", await evalJs("document.querySelector('input[name=mode][value=demo]')?.checked === true"));

  // 4. Full analyse flow with Demo B
  await evalJs("document.querySelector('form button[type=submit]')?.click()");
  const gotReport = await waitFor("location.hash === '#/report' && document.body.innerText.includes('Risk report')");
  check("analysing a sample reaches the report page", gotReport);
  await sleep(600);
  const body = await evalJs("document.body.innerText");
  check("report shows DEMO DATA banner", body.includes("DEMO DATA, NOT LIVE VERIFICATION"));
  check("report shows risk + confidence separately", body.includes("Very High Risk") && body.includes("Confidence in this assessment"));
  check("report lists findings with points", body.includes("+35 points") || body.includes("+40 points") || body.includes("+30 points"));
  check("report shows sources and unavailable status", body.includes("What was checked?") && body.includes("Unavailable"));
  check("report has checklist + never-share warning", body.includes("Never share") && body.includes("seed phrase"));
  await shot("report-desktop.png");

  // 5. Live mode end-to-end against real sources
  await nav(APP + "/#/check"); await sleep(800);
  await evalJs("[...document.querySelectorAll('input[name=mode]')].find(i => i.value === 'live')?.click()");
  await sleep(300);
  check("live mode warns about unconfigured sources", (await evalJs("document.body.innerText")).includes("Not configured on this server"));
  await evalJs(`(() => {
    const set = (id, v) => {
      const el = document.getElementById(id);
      const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, "value").set.call(el, v);
      el.dispatchEvent(new Event("input", { bubbles: true }));
    };
    set("token_name", "Bitcoin");
    set("text", "Selling 1 BTC for $30,000, pay within 1 hour");
  })()`);
  await sleep(300);
  await evalJs("document.querySelector('form button[type=submit]')?.click()");
  const gotLive = await waitFor("location.hash === '#/report' && document.body.innerText.includes('Live verification')", 480);
  check("live analysis reaches the report page", gotLive);
  await sleep(500);
  const liveBody = await evalJs("document.body.innerText");
  check("live report cites real sources, no DEMO banner", gotLive && liveBody.includes("CoinGecko") && !liveBody.includes("DEMO DATA, NOT LIVE"));
  check("live report explains confidence vs risk", liveBody.includes("Confidence in this assessment") && /High Risk|Moderate Risk|Low Risk/.test(liveBody));
  await shot("report-live.png");

  // 6. Mobile layout at 390x844
  await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
  await sleep(500);
  const overflow = await evalJs("document.documentElement.scrollWidth - window.innerWidth");
  check("no horizontal overflow at 390px", overflow <= 1, `scrollWidth-innerWidth=${overflow}`);
  await shot("report-mobile.png");
  await nav(APP + "/#/check"); await sleep(700);
  const overflow2 = await evalJs("document.documentElement.scrollWidth - window.innerWidth");
  check("check page fits 390px width", overflow2 <= 1, `overflow=${overflow2}`);
  await shot("check-mobile.png");
  await send("Emulation.clearDeviceMetricsOverride");

  // 6. Learn / About pages
  await nav(APP + "/#/learn"); await sleep(400);
  check("learn page renders topics", (await evalJs("document.querySelectorAll('article').length")) >= 5);
  await nav(APP + "/#/about"); await sleep(400);
  check("about page explains risk vs confidence", (await evalJs("document.body.innerText")).includes("Risk is not confidence"));

  // 7. Deep link to report with no stored report falls back to the form
  await evalJs("sessionStorage.clear()");
  await nav(APP + "/#/report");
  await evalJs("location.reload()");
  for (let i = 0; i < 40 && !(await evalJs("document.readyState === 'complete'")); i++) await sleep(250);
  await sleep(600);
  check("report route without a report falls back to form", await evalJs("!!document.querySelector('form')"));

  check("no uncaught JS errors during the run", jsErrors.length === 0, jsErrors.slice(0, 3).join(" | ").slice(0, 200));
} catch (e) {
  check("script completed", false, String(e).slice(0, 200));
} finally {
  ws.close();
  chrome.kill();
}

const failed = results.filter(([ok]) => !ok).length;
console.log(`\n${results.length - failed}/${results.length} UI checks passed`);
process.exit(failed ? 1 : 0);
