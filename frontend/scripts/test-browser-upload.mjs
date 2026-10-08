import { spawn } from "node:child_process";
import { existsSync, rmSync, mkdirSync, writeFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const APP = "http://127.0.0.1:5173";
const PORT = 9444;
const CHROME = [
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
].find((p) => existsSync(p));

const profile = join(process.env.TEMP || "/tmp", "offercheck-browser-test-profile");
try { rmSync(profile, { recursive: true, force: true }); } catch {}

const chrome = spawn(CHROME, [
  "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
  `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`, "--window-size=1280,900",
  "about:blank",
], { stdio: "ignore" });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const ws = await (async () => {
  for (let i = 0; i < 40; i++) {
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json/list`)).json();
      const page = list.find((t) => t.type === "page");
      if (page) return new WebSocket(page.webSocketDebuggerUrl);
    } catch {}
    await sleep(250);
  }
  throw new Error("Chrome CDP did not come up");
})();

let seq = 0;
const pending = new Map();
const networkResponses = [];

ws.addEventListener("message", (ev) => {
  const m = JSON.parse(ev.data);
  if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  if (m.method === "Network.responseReceived") {
    networkResponses.push(m.params.response);
  }
  if (m.method === "Runtime.consoleAPICalled") {
    console.log("[Browser Console]", m.params.type, m.params.args.map(a => a.value || a.description).join(" "));
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

try {
  await send("Page.enable");
  await send("Runtime.enable");
  await send("DOM.enable");
  await send("Network.enable");

  console.log("Navigating to:", APP + "/#/check");
  await send("Page.navigate", { url: APP + "/#/check" });
  await sleep(1500);

  const doc = await send("DOM.getDocument");
  const fileInput = await send("DOM.querySelector", {
    nodeId: doc.result.root.nodeId,
    selector: "#file-upload"
  });
  console.log("Found file input node:", fileInput.result.nodeId);

  const testPng = "G:\\Projects\\offercheck\\test_ocr.png";
  console.log("\n--- TEST A: Real PNG Screenshot Upload in Browser ---");
  await send("DOM.setFileInputFiles", {
    files: [testPng],
    nodeId: fileInput.result.nodeId
  });

  for (let i = 0; i < 40; i++) {
    await sleep(400);
    const textareas = await evalJs("Array.from(document.querySelectorAll('textarea')).map(t => t.value)");
    if (textareas && textareas.some(t => t.includes("GUARANTEED"))) {
      console.log("PASS PNG: Text extracted into textarea:", textareas[0]);
      break;
    }
  }

  // Clear text
  await evalJs("(() => { const t = document.querySelector('textarea'); t.value = ''; t.dispatchEvent(new Event('input', { bubbles: true })); })()");

  console.log("\n--- TEST B: Real PDF Document Upload in Browser ---");
  await send("DOM.setFileInputFiles", {
    files: ["G:\\Projects\\offercheck\\test_valid.pdf"],
    nodeId: fileInput.result.nodeId
  });

  for (let i = 0; i < 40; i++) {
    await sleep(400);
    const textareas = await evalJs("Array.from(document.querySelectorAll('textarea')).map(t => t.value)");
    if (textareas && textareas.some(t => t.includes("10,000 USDT") || t.includes("scam-claim"))) {
      console.log("PASS PDF: Text extracted into textarea:", textareas);
      break;
    }
  }

  console.log("\n--- TEST C: Form Submission with Extracted Text ---");
  await evalJs("document.querySelector('form button[type=submit]').click()");
  for (let i = 0; i < 40; i++) {
    await sleep(500);
    const hash = await evalJs("location.hash");
    if (hash === "#/report") {
      console.log("PASS SUBMIT: Successfully reached #/report page!");
      const reportHeader = await evalJs("document.querySelector('h1')?.innerText");
      console.log("Report Header:", reportHeader);
      break;
    }
  }

  console.log("\nNetwork responses captured:");
  for (const resp of networkResponses) {
    if (resp.url.includes("/api/")) {
      console.log(`-> ${resp.url} : Status ${resp.status} ${resp.statusText}`);
    }
  }

} catch (e) {
  console.error("Test failed with error:", e);
} finally {
  ws.close();
  chrome.kill();
}
