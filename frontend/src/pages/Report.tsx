import { useEffect, useState } from "react";
import type { Check, Claims, Finding, Report } from "../types";
import { getSavedReport, saveReport, shareLink } from "../api";

const LEVEL_STYLE: Record<string, { text: string; bg: string; bar: string }> = {
  low: { text: "text-okay", bg: "bg-okay-tint", bar: "#23704A" }, moderate: { text: "text-amber", bg: "bg-amber-tint", bar: "#8A5A00" },
  high: { text: "text-signal", bg: "bg-signal-tint", bar: "#B8322A" }, very_high: { text: "text-signal", bg: "bg-signal-tint", bar: "#8E1F19" },
  insufficient: { text: "text-muted", bg: "bg-ground", bar: "#4A5D55" },
};
const SEV: Record<string, { label: string; cls: string; color: string }> = {
  critical: { label: "Critical", cls: "bg-signal text-white", color: "#8E1F19" }, high: { label: "High", cls: "bg-signal-tint text-signal", color: "#B8322A" },
  medium: { label: "Medium", cls: "bg-amber-tint text-amber", color: "#8A5A00" }, low: { label: "Low", cls: "bg-amber-tint text-amber", color: "#8A5A00" },
  ok: { label: "No concern", cls: "bg-okay-tint text-okay", color: "#23704A" },
};
const STATUS: Record<string, string> = { verified: "Verified", not_found: "Not found in this source", unavailable: "Unavailable / not verified", not_applicable: "Not run", claim: "Stated in the offer text" };
const CONF_STYLE = { High: "bg-okay-tint text-okay", Medium: "bg-amber-tint text-amber", Low: "bg-signal-tint text-signal" };

function when(t: string) {
  const d = new Date(t);
  return isNaN(d.getTime()) ? t : d.toLocaleString();
}

function Meter({ score }: { score: number }) {
  const seg = [["Low", 25, "#23704A"], ["Moderate", 25, "#8A5A00"], ["High", 30, "#B8322A"], ["Very high", 20, "#8E1F19"]] as const;
  return (
    <div className="mt-4" role="img" aria-label={`Risk score ${score} out of 100`}>
      <div className="relative flex h-3 overflow-hidden rounded-full">
        {seg.map(([n, w, c]) => <div key={n} style={{ width: `${w}%`, background: c }} />)}
      </div>
      <div className="relative h-4"><div className="absolute -top-1 h-5 w-1 rounded bg-ink" style={{ left: `calc(${Math.min(100, score)}% - 2px)` }} /></div>
      <div className="flex text-xs text-muted">{seg.map(([n, w]) => <span key={n} style={{ width: `${w}%` }}>{n}</span>)}</div>
    </div>
  );
}

function FindingCard({ f }: { f: Finding }) {
  const s = SEV[f.severity];
  return (
    <article className="card border-l-4 p-4" style={{ borderLeftColor: s.color }}>
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-lg font-semibold">{f.title}</h3>
        <span className={`chip ${s.cls}`}>{s.label}</span>
        {f.points > 0 && <span className="chip bg-ground text-ink">+{f.points} points</span>}
        {f.demo && <span className="chip bg-ink text-white">DEMO DATA</span>}
      </div>
      <p className="mt-2">{f.observed}</p>
      <p className="mt-2 text-sm text-muted"><strong className="text-ink">Why it matters:</strong> {f.why}</p>
      <dl className="mt-3 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
        <div><dt className="text-muted">Source</dt><dd className="font-medium">{f.source}</dd></div>
        <div><dt className="text-muted">Status</dt><dd className="font-medium">{STATUS[f.status] ?? f.status}</dd></div>
        <div><dt className="text-muted">Checked</dt><dd className="font-medium">{f.demo ? "Simulated" : when(f.timestamp)}</dd></div>
      </dl>
      <details className="mt-3 text-sm">
        <summary className="cursor-pointer font-medium text-brand">Explain this in simple words</summary>
        <p className="mt-2 rounded-md bg-brand-tint p-3">{f.explanation}</p>
      </details>
    </article>
  );
}

function claimRows(c: Claims): [string, string][] {
  const rows: [string, string | null][] = [
    ["Asset", c.asset_name ? `${c.asset_name}${c.asset_symbol ? ` (${c.asset_symbol})` : ""}` : null],
    ["Price asked", c.claimed_price != null ? `${c.quoted_currency ?? ""} ${c.claimed_price.toLocaleString("en-IN")}${c.quantity ? ` for ${c.quantity} unit(s)` : c.quantity_assumed ? " (quantity not stated; 1 unit assumed)" : ""}` : null],
    ["Market price the seller states", c.claimed_market_price != null ? `${c.quoted_currency ?? ""} ${c.claimed_market_price.toLocaleString("en-IN")}` : null],
    ["Promised return", c.promised_multiplier ? `${c.promised_multiplier}x` : c.promised_return_pct ? `${c.promised_return_pct}%` : null],
    ["Time period", c.return_period_days ? `${c.return_period_days} day(s)` : null],
    ["Guaranteed / risk-free wording", c.guaranteed_language ? "Yes" : null], ["Referral or commission", c.referral ? "Yes" : null],
    ["Urgency / limited time", c.urgency || c.limited_time ? "Yes" : null], ["Asks for secret credentials", c.requests_secrets ? "Yes" : null],
    ["Seller", c.seller_identity], ["Website", c.website_url], ["Network", c.chain], ["Contract", c.contract_address],
    ["Other", c.other_flags.length ? c.other_flags.join("; ") : null],
  ];
  return rows.filter((r): r is [string, string] => !!r[1]);
}

function CheckRow({ c }: { c: Check }) {
  const tone = c.status === "verified" ? "text-okay" : c.status === "not_found" ? "text-amber" : c.status === "unavailable" ? "text-signal" : "text-muted";
  const fb = Array.isArray(c.data?.fallback_from) ? (c.data?.fallback_from as string[]) : [];
  return (
    <li className="grid gap-1 px-4 py-3 sm:grid-cols-[1.4fr_1fr_2fr]">
      <span className="font-medium">{c.label}</span>
      <span className="text-sm">{c.demo && c.status !== "not_applicable" ? "Simulated (demo)" : c.source}{fb.length ? <span className="text-muted"> (after {fb.join(", ")})</span> : null}</span>
      <span className="text-sm"><strong className={tone}>{STATUS[c.status]}</strong>{c.reason ? <span className="text-muted"> · {c.reason}</span> : null}</span>
    </li>
  );
}

export default function ReportPage({ report: rProp, reportId, onNew }: { report: Report | null; reportId?: string; onNew: () => void }) {
  const [loaded, setLoaded] = useState<Report | null>(rProp);
  const [saving, setSaving] = useState(false);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (loaded || !reportId) return;
    getSavedReport(reportId)
      .then((r: Report) => { setLoaded(r); setShareUrl(shareLink(reportId)); })
      .catch(() => setError("We couldn't load this saved report. It may have been deleted or the link is wrong."));
  }, [loaded, reportId]);

  async function onSave() {
    if (!loaded) return;
    setSaving(true);
    setError(null);
    try {
      const res = await saveReport(loaded);
      setShareUrl(shareLink(res.id));
    } catch (e: any) {
      setError(e.message ?? "Could not save the report.");
    } finally {
      setSaving(false);
    }
  }

  function exportJson() {
    if (!loaded) return;
    const blob = new Blob([JSON.stringify(loaded, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `offercheck-report-${loaded.generated_at.slice(0, 10)}.json`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  if (error && !loaded) {
    return (
      <main id="main" className="mx-auto max-w-2xl px-4 py-10">
        <h1 className="text-2xl font-bold">Saved report</h1>
        <p className="mt-3 text-muted">{error}</p>
        <button className="btn-primary mt-4" onClick={onNew}>Check a new offer</button>
      </main>
    );
  }
  const r = loaded;
  if (!r) {
    return (
      <main id="main" className="mx-auto max-w-2xl px-4 py-10">
        <h1 className="text-2xl font-bold">Loading report…</h1>
        <p className="mt-3 text-muted">If this takes a moment, the link may be invalid or the server is offline.</p>
      </main>
    );
  }
  const st = LEVEL_STYLE[r.risk.level_key] ?? LEVEL_STYLE.insufficient;
  const risk = r.findings.filter((f) => f.points > 0);
  const fine = r.findings.filter((f) => f.points === 0);
  const rows = claimRows(r.claims);
  return (
    <main id="main" tabIndex={-1} className="mx-auto max-w-4xl px-4 py-10">
      {r.is_demo && (
        <div role="note" className="mb-6 rounded-md border-2 border-ink bg-ink px-4 py-3 text-center font-display font-bold tracking-wide text-white">DEMO DATA, NOT LIVE VERIFICATION</div>
      )}
      <h1 className="text-3xl font-bold md:text-4xl">Risk report</h1>
      <p className="mt-1 text-sm text-muted">Generated {when(r.generated_at)} · {r.mode === "demo" ? "Demo mode" : "Live verification"}</p>

      <section aria-labelledby="overall" className="mt-6 grid gap-4 md:grid-cols-[1.4fr_1fr]">
        <div className={`card p-5 ${st.bg}`}>
          <h2 id="overall" className="text-base font-semibold text-muted">Overall result</h2>
          {r.risk.insufficient_evidence ? (
            <p className={`mt-1 font-display text-3xl font-bold ${st.text}`}>Not enough evidence</p>
          ) : (
            <p className="mt-1 flex flex-wrap items-baseline gap-x-3"><span className={`font-display text-5xl font-bold ${st.text}`}>{r.risk.score}<span className="text-2xl text-muted"> / 100</span></span><span className={`font-display text-2xl font-bold ${st.text}`}>{r.risk.level}</span></p>
          )}
          {!r.risk.insufficient_evidence && <Meter score={r.risk.score} />}
          {r.risk.raw_points > 100 && <p className="mt-2 text-xs text-muted">Rule points total {r.risk.raw_points}; the score is capped at 100.</p>}
        </div>
        <div className="card p-5">
          <h2 className="text-base font-semibold text-muted">Confidence in this assessment</h2>
          <p className="mt-1"><span className={`chip text-lg ${CONF_STYLE[r.confidence.level]}`}>{r.confidence.level}</span> <span className="text-muted">({r.confidence.score}/100)</span></p>
          <p className="mt-2 font-medium">Verification coverage: {r.coverage.available} / {r.coverage.total} checks available</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted">{r.confidence.reasons.map((x) => <li key={x}>{x}</li>)}</ul>
        </div>
      </section>
      {r.confidence.level !== "High" && !r.risk.insufficient_evidence && r.risk.score < 25 && (
        <p role="note" className="mt-4 rounded-md border border-amber/40 bg-amber-tint p-3 text-sm text-amber">A low risk score with limited verification does not mean the offer is safe.</p>
      )}

      <section aria-labelledby="why" className="card mt-6 p-5">
        <h2 id="why" className="text-xl font-semibold">Why this score?</h2>
        <p className="mt-1 text-sm text-muted">Every point comes from a fixed rule matched against the evidence. The AI model and unavailable sources cannot add or remove points.</p>
        {risk.length ? (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead><tr className="border-b border-rule text-muted">
                <th className="py-2 pr-3 font-semibold">Rule</th><th className="py-2 pr-3 font-semibold">Evidence</th>
                <th className="py-2 pr-3 text-right font-semibold">Points</th><th className="py-2 font-semibold">Why it counts</th>
              </tr></thead>
              <tbody>
                {risk.map((f) => (
                  <tr key={f.rule_id} className="border-b border-rule align-top">
                    <td className="py-2 pr-3 font-medium">{f.title}</td>
                    <td className="py-2 pr-3">{f.observed}</td>
                    <td className="py-2 pr-3 text-right font-semibold">+{f.points}</td>
                    <td className="py-2 text-muted">{f.why}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot><tr className="border-t-2 border-rule">
                <td colSpan={2} className="py-2 pr-3 font-semibold">Total</td>
                <td className="py-2 pr-3 text-right font-semibold">{r.risk.raw_points}</td>
                <td className="py-2 text-muted">{r.risk.raw_points > 100 ? "Capped at 100 for the score." : "Matches the score above."}</td>
              </tr></tfoot>
            </table>
          </div>
        ) : (
          <p className="mt-2 text-sm text-muted">{r.risk.insufficient_evidence ? "There was not enough verified evidence to apply any scoring rule." : "No scoring rule matched the available evidence."}</p>
        )}
      </section>

      <section aria-labelledby="summary" className="card mt-6 p-5">
        <h2 id="summary" className="text-xl font-semibold">In plain words</h2>
        <p className="mt-2 max-w-prose">{r.summary.text}</p>
        <p className="mt-2 text-xs text-muted">{r.summary.method === "llm" ? "Written by an AI model from the verified findings below. It cannot change the score." : "Generated from a fixed template using the verified findings below."}</p>
      </section>

      <section aria-labelledby="claims" className="mt-8">
        <h2 id="claims" className="text-2xl font-semibold">What the offer claimed</h2>
        <p className="text-sm text-muted">Read by {r.extraction.method === "heuristic+llm" ? `pattern rules plus AI (${r.extraction.llm_provider === "ollama" ? "local model" : r.extraction.llm_provider === "anthropic" ? "AI API" : r.extraction.llm_provider ?? "AI"})` : "pattern rules"}. If something is wrong, go back and edit the offer text.</p>
        {rows.length ? (
          <dl className="card mt-3 divide-y divide-rule">{rows.map(([k, v]) => <div key={k} className="grid gap-1 px-4 py-2 sm:grid-cols-[1fr_2fr]"><dt className="text-muted">{k}</dt><dd className="break-words font-medium">{v}</dd></div>)}</dl>
        ) : <p className="mt-3 card p-4 text-muted">No specific claims could be extracted from the input.</p>}
        {r.extraction.notes.map((n) => <p key={n} className="mt-2 text-sm text-amber">{n}</p>)}
      </section>

      <section aria-labelledby="findings" className="mt-8">
        <h2 id="findings" className="text-2xl font-semibold">Key findings</h2>
        <div className="mt-3 space-y-4">
          {risk.length ? risk.map((f) => <FindingCard key={f.rule_id} f={f} />) : <p className="card p-4 text-muted">No warning indicators were found in the checks that could be completed.</p>}
        </div>
      </section>

      {fine.length > 0 && (
        <section aria-labelledby="fine" className="mt-8">
          <h2 id="fine" className="text-2xl font-semibold">Checks with no concern</h2>
          <div className="mt-3 space-y-4">{fine.map((f) => <FindingCard key={f.rule_id} f={f} />)}</div>
        </section>
      )}

      {r.conflicts.length > 0 && (
        <section aria-labelledby="conf" className="mt-8">
          <h2 id="conf" className="text-2xl font-semibold">Conflicting data</h2>
          <ul className="mt-3 list-disc space-y-1 pl-6">{r.conflicts.map((c) => <li key={c}>{c}</li>)}</ul>
        </section>
      )}

      <section aria-labelledby="sources" className="mt-8">
        <h2 id="sources" className="text-2xl font-semibold">What was checked?</h2>
        <ul className="card mt-3 divide-y divide-rule">{r.checks.map((c) => <CheckRow key={c.check_id} c={c} />)}</ul>
        <p className="mt-2 text-sm text-muted">Unavailable sources are never treated as "safe"; they lower confidence instead. "Not found" means the source answered with no record - it is not proof of fraud.</p>
      </section>

      <section aria-labelledby="verify" className="mt-8">
        <h2 id="verify" className="text-2xl font-semibold">Before sending money, verify</h2>
        <p role="alert" className="mt-3 rounded-md border border-signal/50 bg-signal-tint p-3 font-semibold text-signal">{r.never_share}</p>
        <ul className="mt-3 space-y-2">{r.checklist.map((c) => <li key={c} className="flex gap-3"><span aria-hidden className="mt-1 h-4 w-4 flex-none rounded border-2 border-brand" /><span>{c}</span></li>)}</ul>
      </section>

      <section aria-labelledby="limits" className="mt-8 rounded-lg border border-rule bg-panel p-5">
        <h2 id="limits" className="text-lg font-semibold">Important limits</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted">{r.disclaimers.map((d) => <li key={d}>{d}</li>)}</ul>
      </section>

      <div className="no-print mt-8 flex flex-wrap gap-3">
        <button className="btn-primary" onClick={onNew}>Check another offer</button>
        <button className="btn-ghost" onClick={() => window.print()}>Print or save as PDF</button>
        <button className="btn-ghost" onClick={exportJson} disabled={!r}>Export JSON</button>
        <button className="btn-ghost" onClick={onSave} disabled={!r || saving}>{saving ? "Saving…" : (shareUrl ? "Saved! Share link" : "Save report")}</button>
        {shareUrl && (
          <input aria-label="Shareable link" className="max-w-xs flex-1 truncate rounded border border-rule px-2 py-1 text-sm" readOnly value={shareUrl} onFocus={(e) => e.currentTarget.select()} />
        )}
        {error && <p className="self-center text-sm text-signal">{error}</p>}
        <a href="#/learn" className="btn-ghost">Learn about these warning signs</a>
      </div>
    </main>
  );
}
