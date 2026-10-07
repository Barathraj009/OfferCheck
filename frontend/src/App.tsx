import { useCallback, useEffect, useState } from "react";
import { analyze, ApiError, getHealth } from "./api";
import { emptyForm, FieldError, FormState, Health, Report } from "./types";
import Home from "./pages/Home";
import Check from "./pages/Check";
import ReportPage from "./pages/Report";
import Learn from "./pages/Learn";
import About from "./pages/About";

const routeOf = () => (window.location.hash.replace(/^#/, "") || "/");
const go = (r: string) => { window.location.hash = r; window.scrollTo(0, 0); };

const NAV: [string, string][] = [["/", "Home"], ["/check", "Check an offer"], ["/learn", "Learn"], ["/about", "How it works"]];

function Analyzing({ live }: { live: boolean }) {
  return (
    <main id="main" className="mx-auto max-w-2xl px-4 py-16" aria-live="polite">
      <h1 className="text-3xl font-bold">Checking the offer…</h1>
      <p className="mt-3 text-muted">
        {live ? "Each source is queried once, in parallel. Slow or unavailable sources are marked as unavailable instead of blocking the report." : "Running the demo analysis."}
      </p>
      <ul className="card mt-8 divide-y divide-rule">
        {["Read the claims in the offer", "Look up market data and the token contract", "Check liquidity, website age and website safety", "Apply the fixed scoring rules"].map((t) => (
          <li key={t} className="flex items-center gap-3 px-4 py-3">
            <span className="h-3 w-3 animate-pulse rounded-full bg-brand" aria-hidden />
            {t}
          </li>
        ))}
      </ul>
    </main>
  );
}

export default function App() {
  const [route, setRoute] = useState(routeOf());
  const [health, setHealth] = useState<Health | null>(null);
  const [healthErr, setHealthErr] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm());
  const [report, setReport] = useState<Report | null>(() => {
    try { const s = sessionStorage.getItem("report"); return s ? (JSON.parse(s) as Report) : null; } catch { return null; }
  });
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<FieldError | null>(null);

  useEffect(() => {
    const on = () => setRoute(routeOf());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  useEffect(() => {
    getHealth().then((h) => { setHealth(h); setForm((f) => (f.text || f.url || f.token_name ? f : { ...f, mode: h.default_mode })); })
      .catch((e: ApiError) => setHealthErr(e.message));
  }, []);

  const submit = useCallback(async (f: FormState) => {
    setError(null); setPending(true); go("/analysis");
    try {
      const r = await analyze(f);
      setReport(r);
      try { sessionStorage.setItem("report", JSON.stringify(r)); } catch { /* storage may be unavailable */ }
      setPending(false); go("/report");
    } catch (e) {
      const err = e as ApiError;
      setError({ field: err.field ?? null, message: err.message });
      setPending(false); go("/check");
    }
  }, []);

  let page;
  if (route === "/analysis") page = pending ? <Analyzing live={form.mode === "live"} /> : <Check form={form} setForm={setForm} health={health} healthErr={healthErr} error={error} onSubmit={submit} />;
  else if (route === "/check") page = <Check form={form} setForm={setForm} health={health} healthErr={healthErr} error={error} onSubmit={submit} />;
  else if (route === "/report") page = report ? <ReportPage report={report} onNew={() => { setForm(emptyForm(health?.default_mode ?? "demo")); setError(null); go("/check"); }} /> : <Check form={form} setForm={setForm} health={health} healthErr={healthErr} error={error} onSubmit={submit} />;
  else if (route === "/learn") page = <Learn />;
  else if (route === "/about") page = <About />;
  else page = <Home />;

  return (
    <div className="flex min-h-screen flex-col">
      <a href="#main" onClick={(e) => { e.preventDefault(); document.getElementById("main")?.focus(); }} className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-brand focus:px-3 focus:py-2 focus:text-white">Skip to content</a>
      <header className="border-b border-rule bg-panel">
        <nav aria-label="Main" className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3">
          <a href="#/" className="font-display text-xl font-bold text-brand">OfferCheck</a>
          <ul className="flex flex-wrap items-center gap-x-5 gap-y-1">
            {NAV.map(([to, label]) => (
              <li key={to}>
                <a href={`#${to}`} aria-current={route === to ? "page" : undefined} className={`py-2 inline-block font-medium hover:text-brand ${route === to ? "text-brand underline underline-offset-8 decoration-2" : "text-ink"}`}>{label}</a>
              </li>
            ))}
          </ul>
        </nav>
      </header>
      <div className="flex-1" tabIndex={-1}>{page}</div>
      <footer className="border-t border-rule bg-panel">
        <div className="mx-auto max-w-5xl px-4 py-6 text-sm text-muted">
          <p><strong className="text-ink">Risk assessment and verification assistance, not financial, legal or investment advice.</strong> Scores reflect only the evidence that could be checked, and no automated system can guarantee fraud detection. Never share your seed phrase, private key, OTP or password with anyone.</p>
        </div>
      </footer>
    </div>
  );
}
