import { Dispatch, FormEvent, ReactNode, SetStateAction, useEffect, useRef, useState } from "react";
import { ApiError, getScenarios, ocrImage } from "../api";
import type { FieldError, FormState, Health, Scenario } from "../types";

// speech = BCP-47 for the browser's speech recogniser; ocr = Tesseract language pack; code = explanation language
const LANGS = [
  { label: "English", speech: "en-IN", ocr: "eng", code: "en" }, { label: "हिन्दी (Hindi)", speech: "hi-IN", ocr: "hin", code: "hi" },
  { label: "தமிழ் (Tamil)", speech: "ta-IN", ocr: "tam", code: "ta" }, { label: "తెలుగు (Telugu)", speech: "te-IN", ocr: "tel", code: "te" },
  { label: "বাংলা (Bengali)", speech: "bn-IN", ocr: "ben", code: "bn" }, { label: "मराठी (Marathi)", speech: "mr-IN", ocr: "mar", code: "mr" },
  { label: "ગુજરાતી (Gujarati)", speech: "gu-IN", ocr: "guj", code: "gu" }, { label: "ಕನ್ನಡ (Kannada)", speech: "kn-IN", ocr: "kan", code: "kn" },
  { label: "മലയാളം (Malayalam)", speech: "ml-IN", ocr: "mal", code: "ml" }, { label: "ਪੰਜਾਬੀ (Punjabi)", speech: "pa-IN", ocr: "pan", code: "pa" },
];
const SOURCE_LABEL: Record<string, string> = {
  etherscan: "Etherscan layer (optional API key; Sourcify and public RPCs verify without it)",
  safe_browsing: "Google Safe Browsing (optional API key; the OpenPhish phishing feed is used without it)",
  llm: "AI claim reading & explanation (free with a local Ollama model, or an optional Anthropic key)",
};

interface Props {
  form: FormState;
  setForm: Dispatch<SetStateAction<FormState>>;
  health: Health | null;
  healthErr: string | null;
  error: FieldError | null;
  onSubmit: (f: FormState) => void;
}

function Field({ id, label, hint, error, children }: { id: string; label: string; hint?: string; error?: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="mb-1 block font-semibold">{label}</label>
      {hint && <p id={`${id}-hint`} className="mb-1 text-sm text-muted">{hint}</p>}
      {children}
      {error && <p id={`${id}-err`} role="alert" className="mt-1 text-sm font-medium text-signal">{error}</p>}
    </div>
  );
}

export default function Check({ form, setForm, health, healthErr, error, onSubmit }: Props) {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [listening, setListening] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [ocrBusy, setOcrBusy] = useState(false);
  const [localErr, setLocalErr] = useState<string | null>(null);
  const rec = useRef<any>(null);
  const lang = LANGS.find((l) => l.code === form.lang) ?? LANGS[0];

  useEffect(() => { getScenarios().then(setScenarios).catch(() => setScenarios([])); }, []);
  useEffect(() => () => rec.current?.stop?.(), []);

  const set = (k: keyof FormState, v: string) => setForm((f) => ({ ...f, [k]: v, demo_scenario: null })); // editing clears the sample link
  const errFor = (f: string) => (error?.field === f ? error.message : undefined);

  function loadSample(s: Scenario) {
    setLocalErr(null);
    setForm((f) => ({ ...f, ...s.inputs, mode: "demo", demo_scenario: s.id }));
  }

  function toggleVoice() {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) { setNote("Voice input is not supported in this browser. Try Chrome or Edge, or type the offer instead."); return; }
    if (listening) { rec.current?.stop(); return; }
    const r = new SR();
    r.lang = lang.speech; r.continuous = true; r.interimResults = false;
    r.onresult = (e: any) => {
      let t = "";
      for (let i = e.resultIndex; i < e.results.length; i++) if (e.results[i].isFinal) t += e.results[i][0].transcript + " ";
      if (t) setForm((f) => ({ ...f, text: (f.text + " " + t).trim(), demo_scenario: null }));
    };
    r.onerror = (e: any) => setNote(e.error === "not-allowed" ? "Microphone permission was denied." : "Voice input stopped (" + e.error + "). You can type instead.");
    r.onend = () => setListening(false);
    rec.current = r; setNote("Listening… speak the offer, then press Stop. Speech is transcribed by your browser (it may use its online service). Check the text below before analysing - speech recognition can make mistakes."); setListening(true); r.start();
  }

  async function onFile(file: File | undefined) {
    if (!file) return;
    setOcrBusy(true); setNote(null);
    try {
      const { text, empty } = await ocrImage(file, lang.ocr);
      if (empty) setNote("No readable text was found in that image. Try a clearer screenshot or type the text.");
      else { setForm((f) => ({ ...f, text: (f.text ? f.text + "\n" : "") + text, demo_scenario: null })); setNote("Text was extracted from your image and added below. Please read it and correct any mistakes before analysing."); }
    } catch (e) { setNote((e as ApiError).message); }
    finally { setOcrBusy(false); }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!(form.text.trim() || form.url.trim() || form.token_name.trim() || form.contract_address.trim())) {
      setLocalErr("Add something to check: describe the offer, or enter a website, token name or contract address."); return;
    }
    setLocalErr(null); onSubmit(form);
  }

  const missing = health ? Object.entries(SOURCE_LABEL).filter(([k]) => !health.sources[k]).map(([, v]) => v) : [];
  const generalErr = localErr ?? (error && !error.field ? error.message : undefined) ?? (error?.field === "text" ? error.message : undefined);

  return (
    <main id="main" tabIndex={-1} className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="text-3xl font-bold md:text-4xl">Check an offer</h1>
      <p className="mt-2 text-muted">Give us whatever you have. More details mean more checks can run and confidence will be higher.</p>
      {healthErr && <p role="alert" className="mt-4 rounded-md border border-signal/40 bg-signal-tint p-3 text-signal">{healthErr}</p>}

      <section aria-labelledby="samples" className="mt-6 card p-4">
        <h2 id="samples" className="text-lg font-semibold">Try a sample</h2>
        <p className="text-sm text-muted">Sample scenarios use simulated data and are always labelled "DEMO DATA, NOT LIVE VERIFICATION".</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {scenarios.map((s) => (
            <button key={s.id} type="button" onClick={() => loadSample(s)} className={`btn-ghost text-left ${form.demo_scenario === s.id ? "ring-2 ring-brand" : ""}`} title={s.blurb}>{s.title}</button>
          ))}
          {scenarios.length === 0 && <span className="text-sm text-muted">Samples load when the backend is running.</span>}
        </div>
      </section>

      <form onSubmit={submit} noValidate className="mt-6 space-y-8">
        <fieldset className="card p-4">
          <legend className="px-1 text-lg font-semibold">Verification mode</legend>
          <div className="mt-1 grid gap-3 sm:grid-cols-2">
            {(["demo", "live"] as const).map((m) => (
              <label key={m} className={`flex cursor-pointer gap-3 rounded-md border p-3 ${form.mode === m ? "border-brand bg-brand-tint" : "border-rule"}`}>
                <input type="radio" name="mode" value={m} checked={form.mode === m} onChange={() => setForm((f) => ({ ...f, mode: m, demo_scenario: m === "live" ? null : f.demo_scenario }))} className="mt-1 h-4 w-4 accent-[#0B5D4E]" />
                <span><span className="block font-semibold">{m === "demo" ? "Demo mode" : "Live verification"}</span>
                  <span className="text-sm text-muted">{m === "demo" ? "Simulated sample data. No API calls." : "Real lookups from public data sources."}</span></span>
              </label>
            ))}
          </div>
          {form.mode === "live" && missing.length > 0 && (
            <p className="mt-3 text-sm text-muted">Not configured on this server (optional extras only - every check still runs with free sources): {missing.join("; ")}.</p>
          )}
        </fieldset>

        <section aria-labelledby="s1" className="space-y-4">
          <h2 id="s1" className="text-xl font-semibold">1. What was offered?</h2>
          <Field id="lang" label="Language of the offer" hint="Used for voice input and screenshot text. The written explanation follows it too when an AI model is available.">
            <select id="lang" className="field sm:max-w-xs" value={form.lang} onChange={(e) => setForm((f) => ({ ...f, lang: e.target.value }))}>
              {LANGS.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
            </select>
          </Field>
          <Field id="text" label="Offer text" hint="Paste the message, or use voice or a screenshot below." error={generalErr}>
            <textarea id="text" rows={6} maxLength={health?.max_input_chars ?? 6000} className="field" value={form.text} onChange={(e) => set("text", e.target.value)}
              placeholder="e.g. Buy Bitcoin for ₹40 lakh instead of the market price. Guaranteed to double your money in 30 days. Refer 3 friends and receive commission."
              aria-describedby={generalErr ? "text-err text-hint" : "text-hint"} aria-invalid={!!generalErr} />
          </Field>
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" onClick={toggleVoice} aria-pressed={listening} className={listening ? "btn bg-signal text-white" : "btn-ghost"}>{listening ? "Stop listening" : "Speak the offer"}</button>
            <label className={`btn-ghost cursor-pointer ${ocrBusy ? "opacity-60" : ""}`}>
              {ocrBusy ? "Reading image…" : "Upload a screenshot"}
              <input type="file" accept="image/png,image/jpeg,image/webp" className="sr-only" disabled={ocrBusy} onChange={(e) => { onFile(e.target.files?.[0]); e.target.value = ""; }} />
            </label>
            <span className="text-sm text-muted">PNG, JPG or WebP, up to 5 MB</span>
          </div>
          {note && <p role="status" className="rounded-md bg-brand-tint p-3 text-sm">{note}</p>}
        </section>

        <section aria-labelledby="s2" className="space-y-4">
          <h2 id="s2" className="text-xl font-semibold">2. Website (optional)</h2>
          <Field id="url" label="Website or offer page" hint="We never open the page. We only look up public records about its address." error={errFor("url")}>
            <input id="url" type="text" inputMode="url" autoComplete="off" className="field" value={form.url} onChange={(e) => set("url", e.target.value)} placeholder="https://example.com/offer" aria-invalid={!!errFor("url")} aria-describedby={errFor("url") ? "url-hint url-err" : "url-hint"} />
          </Field>
        </section>

        <section aria-labelledby="s3" className="space-y-4">
          <h2 id="s3" className="text-xl font-semibold">3. Token details (optional)</h2>
          <Field id="token_name" label="Token or coin name" error={errFor("token_name")}>
            <input id="token_name" type="text" className="field" maxLength={100} value={form.token_name} onChange={(e) => set("token_name", e.target.value)} placeholder="e.g. Bitcoin, or the new token's name" />
          </Field>
          <div className="grid gap-4 sm:grid-cols-[1fr_2fr]">
            <Field id="chain" label="Blockchain" error={errFor("chain")}>
              <select id="chain" className="field" value={form.chain} onChange={(e) => set("chain", e.target.value)} aria-invalid={!!errFor("chain")}>
                <option value="">Select network</option>
                {Object.entries(health?.chains ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                <option value="solana">Solana (cannot be verified yet)</option>
                <option value="other">Other (cannot be verified yet)</option>
              </select>
            </Field>
            <Field id="contract_address" label="Contract address" error={errFor("contract_address")}>
              <input id="contract_address" type="text" spellCheck={false} autoComplete="off" className="field font-mono text-sm" value={form.contract_address} onChange={(e) => set("contract_address", e.target.value)} placeholder="0x…" aria-invalid={!!errFor("contract_address")} />
            </Field>
          </div>
        </section>

        <p className="rounded-md border border-signal/40 bg-signal-tint p-3 text-sm font-medium text-signal">Never paste a seed phrase, private key, password or OTP anywhere in this form. We never need them.</p>
        <button type="submit" className="btn-primary w-full text-lg sm:w-auto">Analyse this offer</button>
      </form>
    </main>
  );
}
