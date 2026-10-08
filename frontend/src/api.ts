import type { FormState, Health, Report, Scenario } from "./types";

export class ApiError extends Error {
  field: string | null;
  constructor(message: string, field: string | null = null) {
    super(message);
    this.field = field;
  }
}

async function parse<T>(res: Response, path: string): Promise<T> {
  let body: any = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON response e.g. proxy HTML error */
  }

  if (!res.ok) {
    const errorMsg = body?.error?.message;
    if (errorMsg) {
      throw new ApiError(errorMsg, body?.error?.field ?? null);
    }
    if (res.status === 400) {
      throw new ApiError("Bad request: the submitted data could not be processed.", null);
    }
    if (res.status === 404) {
      throw new ApiError(`API endpoint not found: ${path} (HTTP 404).`, null);
    }
    if (res.status === 413) {
      throw new ApiError("The uploaded file is too large. Maximum allowed size is 5 MB.", "file");
    }
    if (res.status === 415) {
      throw new ApiError("Unsupported file format. Please upload an image (PNG, JPEG, WebP) or PDF file.", "file");
    }
    if (res.status === 422) {
      throw new ApiError(body?.error?.message ?? "The submitted data is invalid or missing required fields.", body?.error?.field ?? null);
    }
    if (res.status === 429) {
      throw new ApiError("Too many requests sent to the server. Please wait a few minutes before trying again.", null);
    }
    if (res.status === 502 || res.status === 504) {
      throw new ApiError(`Verification server gateway error (HTTP ${res.status}). The FastAPI backend on port 8000 may be starting up or unresponsive.`, null);
    }
    if (res.status === 503) {
      throw new ApiError("The text extraction or verification service is temporarily unavailable on this server.", null);
    }
    throw new ApiError(`The server returned an error (HTTP ${res.status}${res.statusText ? `: ${res.statusText}` : ""}).`, body?.error?.field ?? null);
  }
  return body as T;
}

async function call<T>(path: string, init?: RequestInit, timeoutMs = 60000): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(path, { ...init, signal: ctrl.signal });
    return await parse<T>(res, path);
  } catch (e) {
    if (e instanceof ApiError) throw e;
    if ((e as Error).name === "AbortError") {
      throw new ApiError(`Request timed out after ${Math.round(timeoutMs / 1000)}s while communicating with ${path}. Please try again.`);
    }
    const errObj = e as Error;
    const details = errObj?.message ? ` (${errObj.message})` : "";
    throw new ApiError(`Unable to connect to the verification server at ${path}${details}. Please ensure the FastAPI backend is running on http://127.0.0.1:8000.`);
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

export function saveReport(report: Report) {
  return call<{ id: string; saved_at: string }>("/api/reports", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(report),
  }, 15000);
}

export function getSavedReport(id: string) {
  return call<Report>(`/api/reports/${encodeURIComponent(id)}`, undefined, 10000);
}

export function listSavedReports() {
  return call<{ reports: any[] }>("/api/reports", undefined, 8000);
}

export function ocrImage(file: File, ocrLang: string) {
  const fd = new FormData();
  fd.append("file", file);
  return call<{ text: string; empty: boolean }>(`/api/ocr?lang=${encodeURIComponent(ocrLang)}`, { method: "POST", body: fd }, 45000);
}

export function deleteSavedReport(id: string) {
  return call<{ deleted: boolean }>(`/api/reports/${encodeURIComponent(id)}`, { method: "DELETE" }, 8000);
}

export function shareLink(id: string) {
  return `${window.location.origin}${window.location.pathname}#/report/${encodeURIComponent(id)}`;
}
