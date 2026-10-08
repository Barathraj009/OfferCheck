import { Dispatch, FormEvent, SetStateAction, useState, useRef } from "react";
import type { FieldError, FormState, Health } from "../types";
import { getHealth } from "../api";

const LANGS = [
  { label: "English", speech: "en-IN", ocr: "eng", code: "en" },
  { label: "Hindi", speech: "hi-IN", ocr: "hin", code: "hi" },
  { label: "Tamil", speech: "ta-IN", ocr: "tam", code: "ta" },
];

const SOURCE_LABEL: Record<string, string> = {
  etherscan: "Etherscan (optional API key)",
  safe_browsing: "Google Safe Browsing (optional)",
  llm: "AI claim reading (free local Ollama)",
};

interface Props {
  form: FormState;
  setForm: Dispatch<SetStateAction<FormState>>;
  health: Health | null;
  healthErr: string | null;
  error: FieldError | null;
  onSubmit: (f: FormState) => void;
}

export default function Check({ form, setForm, error, onSubmit }: Props) {
  // Primary text: first cell is the main input, additional cells are extra
  const [textCells, setTextCells] = useState<string[]>([form.text || ""]);
  const [localErr, setLocalErr] = useState<string | null>(null);
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [voiceText, setVoiceText] = useState("");
  const [showVoice, setShowVoice] = useState(false);
  const [website, setWebsite] = useState(form.website || "");
  const [tokenCont, setTokenCont] = useState(form.tokenCont || "");
  const rec = useRef<any>(null);
  const lang = LANGS.find((l) => l.code === form.lang) || LANGS[0];

  // ---- Text cell management ----
  const updateCell = (i: number, value: string) => {
    const next = [...textCells];
    next[i] = value.trim();
    setTextCells(next);
  };

  const addTextCell = () => {
    if (textCells.length >= 10) return;
    setTextCells([...textCells, ""]);
  };

  const removeTextCell = (i: number) => {
    if (textCells.length <= 1) return;
    const next = textCells.filter((_, idx) => idx !== i);
    setTextCells(next);
    // also clear form.text if we're removing the main cell
    if (i === 0) setForm((f) => ({ ...f, text: next.join("\n\n") }));
  };

  // ---- Voice input ----
  const toggleVoice = async () => {
    setVoiceBusy(!voiceBusy);
    if (voiceBusy) { rec.current?.stop(); return; }

    // Use Whisper STT backend: capture microphone audio, send to /api/whisper-transcribe
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, sampleRate: 16000 },
      });
      rec.current = stream;

      const mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/wav" });
      const chunks: Blob[] = [];
      mediaRecorder.ondataavailable = (e) => chunks.push(e.data);
      mediaRecorder.onstop = async () => {
        setVoiceBusy(true);
        setShowVoice(true);
        // Send recorded audio to Whisper backend
        const formData = new FormData();
        formData.append("file", chunks[0], "recording.wav");
        const resp = await fetch("/api/whisper-transcribe", {
          method: "POST",
          body: formData,
        });
        if (!resp.ok) throw new Error("Whisper transcription failed");
        const data = await resp.json();
        setVoiceText(data.text || "");
        setVoiceBusy(false);
        setShowVoice(false);
      };
      mediaRecorder.start();

      // Auto-stop after 10 seconds
      const timeoutId = setTimeout(() => {
        mediaRecorder.stop();
        clearTimeout(timeoutId);
      }, 10000);
      return;
    } catch (err) {
      // Fall back to browser SpeechRecognition if mic fails
      const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
      if (!SR) { setVoiceBusy(false); setLocalErr("Voice not supported - no microphone"); return; }
      const r = new SR();
      r.lang = lang.speech;
      r.continuous = true;
      r.interimResults = false;
      r.onresult = (e: any) => {
        let t = "";
        for (let i = e.resultIndex; i < e.results.length; i++)
          if (e.results[i].isFinal) t += e.results[i][0].transcript + " ";
        setVoiceText(t);
      };
      r.onend = () => { setVoiceBusy(false); };
      r.start();
    }
  };

  const checkWhisperAvailability = async (): Promise<boolean> => {
    try {
      const resp = await fetch("/api/whisper/health", {
        method: "GET",
        headers: { "ngrok-skip-browser-warning": "1" },
        timeout: 5000,
      });
      return resp.ok;
    } catch {
      return false;
    }
  };

const insertVoiceText = () => {
    const t = voiceText.trim();
    if (!t) return;
    // Insert into the first (main) cell
    setTextCells((prev) => {
      const next = [...prev];
      next[0] = (next[0] ? next[0] + " " : "") + t;
      return next;
    });
    setVoiceText("");
    setVoiceBusy(false);
    setShowVoice(false);
  };

  function submit(e: FormEvent) {
    e.preventDefault();
    // Combine all text cells
    const combined = textCells.map((c) => c.trim()).filter(Boolean).join("\n\n");
    // Also include website and token/contract if provided
    const websiteClean = website.trim();
    const tokenClean = tokenCont.trim();
    
    // Build the full input string for submission
    const parts: string[] = [];
    if (combined) parts.push(combined);
    if (websiteClean) parts.push("WEBSITE: " + websiteClean);
    if (tokenClean) parts.push("TOKEN/CONTRACT: " + tokenClean);
    
    const fullInput = parts.join("\n\n");
    if (!combined && !websiteClean && !tokenClean) {
      setLocalErr("Enter at least one offer message"); return;
    }
    setLocalErr(null);
    // Pass the full text to onSubmit - the backend will parse it
    setForm({ ...form, text: fullInput });
    onSubmit({ ...form, text: fullInput });
  }

  const generalErr = localErr ?? (error && !error.field ? error.message : undefined);

  return (
    <main id="main" tabIndex={-1} className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="text-3xl font-bold md:text-4xl">Verify Before You Trust</h1>
      <p className="mt-2 text-muted">Give OfferCheck whatever you have. We'll figure out what needs to be checked.</p>
      <form onSubmit={submit} noValidate className="mt-6 space-y-6">
        <section aria-labelledby="s1" className="space-y-4">
          <h2 id="s1" className="text-xl font-semibold">What offer did you receive?</h2>
          {textCells.map((c, i) => (
            <div key={i} className="space-y-2">
              <textarea
                rows={4}
                className="field"
                value={c}
                onChange={(e) => updateCell(i, e.target.value)}
                placeholder="Paste the offer message, promoter reply, or additional text"
                aria-invalid={i === 0 && !!localErr}
                aria-describedby={i === 0 && !!localErr ? "text-err text-hint" : "text-hint"}
              />
              {textCells.length > 1 && (
                <button type="button" className="btn-ghost" onClick={() => removeTextCell(i)}>
                  Remove
                </button>
              )}
            </div>
          ))}
          {textCells.length < 10 && (
            <button type="button" className="btn-ghost" onClick={addTextCell}>
              + Add another text
            </button>
          )}
        </section>

        <section aria-labelledby="s2" className="space-y-2">
          <h2 id="s2" className="text-xl font-semibold">Optional details (not required)</h2>
          <div className="grid gap-2">
            <button type="button" className="btn-ghost" onClick={toggleVoice}>
              {voiceBusy ? "Listening…" : "🎙 Speak"}
            </button>
            {voiceBusy && (
              <p className="text-xs text-muted mt-1">Speak the offer, then click Cancel</p>
            )}
            {showVoice && (
              <button type="button" className="btn-ghost" onClick={() => setShowVoice(false)}>
                Cancel
              </button>
            )}
          </div>

          <div className="mt-3">
            <label className="text-xs text-muted">Website (optional)</label>
            <input
              type="url"
              className="field w-full"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
              placeholder="https://example.com/offer"
              aria-invalid={!!localErr}
            />
            <label className="text-xs text-muted mt-1">Token / Contract (optional)</label>
            <input
              type="text"
              className="field w-full"
              value={tokenCont}
              onChange={(e) => setTokenCont(e.target.value)}
              placeholder="Token symbol or contract address (e.g. BTC, ETH, 0x...)"
              aria-invalid={!!localErr}
            />
          </div>
        </section>

        {generalErr && (
          <p role="alert" className="rounded-md border border-signal/40 bg-signal-tint p-3 text-signal">
            {generalErr}
          </p>
        )}

        <button type="submit" className="btn-primary w-full text-lg sm:w-auto">
          CHECK OFFER
        </button>
      </form>
    </main>
  );
}