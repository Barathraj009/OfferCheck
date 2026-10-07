import type { FormState, Health, Report, Scenario } from "./types";

export class ApiError extends Error {
  field: string | null;
  constructor(message: string, field: string | null = null) {
    super(message);
    this.field = field;
  }
}

async function parse<T>(res: Response): Promise<T> {
  let body: any = null;
  try { body = await res.json(); } catch { /* non-JSON error page */ }
  if (!res.ok) throw new ApiError(body?.error?.message ?? `The server returned an error (${res.status}).`, body?.error?.field ?? null);
  return body as T;
}

async function call<T>(path: string, init?: RequestInit, timeoutMs = 60000): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    return await parse<T>(await fetch(path, { ...init, signal: ctrl.signal }));
  } catch (e) {
    if (e instanceof ApiError) throw e;
    if ((e as Error).name === "AbortError") throw new ApiError("This is taking too long. Please try again in a moment.");
    throw new ApiError("Could not reach the verification server. Make sure the backend is running (see README).");
  } finally {
    clearTimeout(timer);
  }
}

export const getHealth = () => call<Health>("/api/health", undefined, 8000);
export const getScenarios = () => call<Scenario[]>("/api/demo-scenarios", undefined, 8000);

export const analyze = (f: FormState) =>
  call<Report>("/api/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: f.text, url: f.url, token_name: f.token_name, contract_address: f.contract_address, chain: f.chain,
      mode: f.mode, demo_scenario: f.demo_scenario, language: f.lang,
    }),
  }, 180000); // a local CPU model can take ~1 minute for extraction + explanation

export function ocrImage(file: File, ocrLang: string) {
  const fd = new FormData();
  fd.append("file", file);
  return call<{ text: string; empty: boolean }>(`/api/ocr?lang=${encodeURIComponent(ocrLang)}`, { method: "POST", body: fd }, 45000);
}
