import { Dispatch, FormEvent, SetStateAction, useState, useRef } from "react";
import type { FieldError, FormState, Health } from "../types";
import { ocrImage } from "../api";

const LANGS = [
  { label: "English", speech: "en-IN", ocr: "eng", code: "en" },
  { label: "Hindi", speech: "hi-IN", ocr: "hin", code: "hi" },
  { label: "Tamil", speech: "ta-IN", ocr: "tam", code: "ta" },
];

interface Props {
  form: FormState;
  setForm: Dispatch<SetStateAction<FormState>>;
  health: Health | null;
  healthErr: string | null;
  error: FieldError | null;
  onSubmit: (f: FormState) => void;
}

export default function Check({ form, setForm, healthErr, error, onSubmit }: Props) {
  const [textCells, setTextCells] = useState<string[]>([form.text || ""]);
  const [localErr, setLocalErr] = useState<string | null>(null);
  const [infoMsg, setInfoMsg] = useState<string | null>(null);

  // Voice state
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [voiceUploading, setVoiceUploading] = useState(false);
  const mediaRecRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // OCR/PDF upload state
  const [ocrBusy, setOcrBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Optional fields
  const [website, setWebsite] = useState(form.website || form.url || "");
  const [tokenCont, setTokenCont] = useState(form.tokenCont || form.contract_address || form.token_name || "");
  const lang = LANGS.find((l) => l.code === form.lang) || LANGS[0];

  // ---- Text cell management ----
  const updateCell = (i: number, value: string) => {
    const next = [...textCells];
    next[i] = value;
    setTextCells(next);
  };

  const addTextCell = (initialText: string = "") => {
    if (textCells.length >= 10) return;
    setTextCells([...textCells, initialText]);
  };

  const removeTextCell = (i: number) => {
    if (textCells.length <= 1) {
      setTextCells([""]);
      return;
    }
    const next = textCells.filter((_, idx) => idx !== i);
    setTextCells(next);
  };

  // ---- Voice input (faster-whisper STT) ----
  const toggleVoice = async () => {
    if (voiceBusy) {
      // Stop recording
      mediaRecRef.current?.stop();
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });

      audioChunksRef.current = [];
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunksRef.current.push(e.data);
      };

      mediaRecorder.onstop = async () => {
        // Stop audio tracks
        stream.getTracks().forEach((track) => track.stop());
        setVoiceBusy(false);
        setVoiceUploading(true);

        try {
          const blob = new Blob(audioChunksRef.current, { type: mediaRecorder.mimeType || "audio/webm" });
          const formData = new FormData();
          formData.append("file", blob, "recording.webm");

          const resp = await fetch("/api/whisper-transcribe", {
            method: "POST",
            body: formData,
          });

          if (!resp.ok) {
            let errorMsg = "";
            try {
              const errBody = await resp.json();
              errorMsg = errBody?.error?.message || errBody?.detail || "";
            } catch {
              // non-JSON response
            }
            if (resp.status === 503) {
              throw new Error(errorMsg || "Voice transcription (faster-whisper) is not available on this server. Please type the offer text directly.");
            }
            throw new Error(errorMsg || `Voice transcription server error (${resp.status}).`);
          }

          const data = await resp.json();
          const transcribed = (data.text || "").trim();
          if (transcribed) {
            // Append or insert into text cells
            setTextCells((prev) => {
              if (prev.length === 1 && !prev[0].trim()) {
                return [transcribed];
              }
              return [...prev, transcribed];
            });
            setInfoMsg("Voice message transcribed and added below. You can edit it before checking.");
          } else {
            setLocalErr("No clear speech detected in recording. Please try speaking closer to the mic.");
          }
        } catch (err: any) {
          setLocalErr(`Voice transcription failed: ${err.message || "Please type the offer text instead."}`);
        } finally {
          setVoiceUploading(false);
        }
      };

      mediaRecorder.start();
      setVoiceBusy(true);
      setLocalErr(null);

      // Auto-stop after 30 seconds
      setTimeout(() => {
        if (mediaRecorder.state === "recording") {
          mediaRecorder.stop();
        }
      }, 30000);
    } catch (err: any) {
      setVoiceBusy(false);
      setLocalErr("Microphone access denied or not supported in this browser.");
    }
  };

  // ---- Image / PDF OCR Extraction ----
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    setOcrBusy(true);
    setLocalErr(null);
    setInfoMsg(null);

    const validExtensions = [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".pdf", ".tiff", ".tif"];
    const validMimes = [
      "image/png", "image/jpeg", "image/webp", "image/bmp", "image/tiff",
      "application/pdf", "application/x-pdf"
    ];

    try {
      const extractedList: string[] = [];
      const fileErrors: string[] = [];

      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const lowerName = file.name.toLowerCase();
        const hasValidExt = validExtensions.some((ext) => lowerName.endsWith(ext));
        const hasValidMime = file.type ? validMimes.includes(file.type) : true;

        if (!hasValidExt && !hasValidMime) {
          fileErrors.push(`"${file.name}": Unsupported format. Please upload PNG, JPG, WebP, or PDF.`);
          continue;
        }

        if (file.size > 5 * 1024 * 1024) {
          fileErrors.push(`"${file.name}": File exceeds the 5 MB limit (${(file.size / (1024 * 1024)).toFixed(1)} MB).`);
          continue;
        }

        try {
          const res = await ocrImage(file, lang.ocr);
          if (res.text && res.text.trim()) {
            extractedList.push(res.text.trim());
          } else {
            fileErrors.push(`"${file.name}": No readable text was detected. Ensure the document or screenshot has clear, visible text.`);
          }
        } catch (err: any) {
          const msg = err?.message || "Failed to process file.";
          fileErrors.push(`"${file.name}": ${msg}`);
        }
      }

      if (extractedList.length > 0) {
        setTextCells((prev) => {
          const cleanPrev = prev.filter((p) => p.trim());
          return [...cleanPrev, ...extractedList];
        });
        if (fileErrors.length > 0) {
          setInfoMsg(`Extracted text from ${extractedList.length} file(s) and added below.`);
          setLocalErr(`Some files could not be processed:\n• ` + fileErrors.join("\n• "));
        } else {
          setInfoMsg(`Extracted text from ${extractedList.length} file(s) and added below. Review and edit as needed.`);
        }
      } else {
        if (fileErrors.length > 0) {
          setLocalErr(fileErrors.join("\n"));
        } else {
          setLocalErr("No readable text found in the uploaded file(s). Please type the offer text directly.");
        }
      }
    } catch (err: any) {
      setLocalErr(err.message || "Document text extraction failed. Please type the offer text.");
    } finally {
      setOcrBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  // ---- Submit Offer ----
  function submit(e: FormEvent) {
    e.preventDefault();
    const cleanCells = textCells.map((c) => c.trim()).filter(Boolean);
    const combined = cleanCells.join("\n\n");
    const websiteClean = website.trim();
    const tokenClean = tokenCont.trim();

    if (!combined && !websiteClean && !tokenClean) {
      setLocalErr("Enter at least one offer message, website, or token address.");
      return;
    }
    setLocalErr(null);

    // Distinguish token name vs contract address if user typed 0x...
    let contractAddr = "";
    let tokenName = "";
    if (tokenClean.startsWith("0x") || tokenClean.length > 30) {
      contractAddr = tokenClean;
    } else {
      tokenName = tokenClean;
    }

    const nextForm: FormState = {
      ...form,
      text: combined,
      url: websiteClean,
      token_name: tokenName,
      contract_address: contractAddr,
      website: websiteClean,
      tokenCont: tokenClean,
      mode: "live", // User-submitted check runs live verification
    };

    setForm(nextForm);
    onSubmit(nextForm);
  }

  const generalErr = localErr ?? (error && !error.field ? error.message : undefined);

  return (
    <main id="main" tabIndex={-1} className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="text-3xl font-bold md:text-4xl text-ink">Verify Before You Trust</h1>
      <p className="mt-2 text-muted">
        Give OfferCheck whatever you have (text, screenshot, voice, website, or contract address). We'll verify the claims against blockchain, market, liquidity, and security data.
      </p>

      {healthErr && (
        <div role="alert" className="mt-4 rounded-md border border-caution/40 bg-caution-tint p-3 text-sm text-ink">
          <strong>Backend connection warning:</strong> {healthErr}
        </div>
      )}

      <form onSubmit={submit} noValidate className="mt-6 space-y-6">
        {/* Section 1: Offer Text & Messages */}
        <section aria-labelledby="s1" className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 id="s1" className="text-xl font-semibold text-ink">What offer did you receive?</h2>
            <div className="flex items-center gap-2">
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileUpload}
                multiple
                accept="image/png,image/jpeg,image/webp,application/pdf"
                className="hidden"
                id="file-upload"
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={ocrBusy}
                className="btn-ghost text-sm flex items-center gap-1.5"
                title="Upload screenshot or PDF to extract text"
              >
                {ocrBusy ? "⏳ Reading file…" : "📷 Upload Screenshot / PDF"}
              </button>
              <button
                type="button"
                onClick={toggleVoice}
                disabled={voiceUploading}
                className={`btn-ghost text-sm flex items-center gap-1.5 ${voiceBusy ? "bg-signal-tint text-signal border-signal" : ""}`}
                title="Record audio of the offer"
              >
                {voiceBusy ? "⏹ Stop Recording" : voiceUploading ? "⏳ Transcribing…" : "🎙 Speak"}
              </button>
            </div>
          </div>

          {infoMsg && (
            <p className="rounded-md border border-okay/40 bg-okay-tint p-3 text-sm text-okay">
              ✓ {infoMsg}
            </p>
          )}

          {textCells.map((c, i) => (
            <div key={i} className="space-y-2">
              <div className="relative">
                <textarea
                  rows={4}
                  className="field w-full"
                  value={c}
                  onChange={(e) => updateCell(i, e.target.value)}
                  placeholder={
                    i === 0
                      ? "Paste the offer message, pitch, WhatsApp/Telegram chat, promise, or details here..."
                      : `Additional promoter reply or chat message #${i + 1}...`
                  }
                  aria-invalid={i === 0 && !!localErr}
                />
              </div>
              {textCells.length > 1 && (
                <div className="flex justify-end">
                  <button
                    type="button"
                    className="text-xs text-signal hover:underline"
                    onClick={() => removeTextCell(i)}
                  >
                    ✕ Remove this text
                  </button>
                </div>
              )}
            </div>
          ))}

          {textCells.length < 10 && (
            <button
              type="button"
              className="btn-ghost text-sm"
              onClick={() => addTextCell("")}
            >
              + Add another text message
            </button>
          )}
        </section>

        {/* Section 2: Optional fields */}
        <section aria-labelledby="s2" className="space-y-3 pt-2 border-t border-rule">
          <h2 id="s2" className="text-lg font-semibold text-ink">Optional details (if available)</h2>
          
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-xs font-medium text-muted mb-1">
                Website URL (optional)
              </label>
              <input
                type="url"
                className="field w-full text-sm"
                value={website}
                onChange={(e) => setWebsite(e.target.value)}
                placeholder="https://example.com/offer"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-muted mb-1">
                Token Name or Contract Address (optional)
              </label>
              <input
                type="text"
                className="field w-full text-sm"
                value={tokenCont}
                onChange={(e) => setTokenCont(e.target.value)}
                placeholder="e.g. BTC, PEPE, or 0x..."
              />
            </div>
          </div>
        </section>

        {generalErr && (
          <div role="alert" className="rounded-md border border-signal/40 bg-signal-tint p-3 text-signal text-sm whitespace-pre-line">
            {generalErr}
          </div>
        )}

        <div className="pt-2">
          <button type="submit" className="btn-primary w-full text-lg py-3">
            CHECK OFFER
          </button>
        </div>
      </form>
    </main>
  );
}