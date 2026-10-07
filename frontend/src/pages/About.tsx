export default function About() {
  const h = "text-2xl font-semibold mt-10";
  return (
    <main id="main" tabIndex={-1} className="mx-auto max-w-3xl px-4 py-12 [&_p]:mt-3 [&_li]:mt-2">
      <h1 className="text-3xl font-bold md:text-4xl">How OfferCheck works</h1>
      <p className="text-lg text-muted">The goal is simple: verify before you pay. The method is deliberately transparent.</p>

      <h2 className={h}>Evidence first, score second, explanation last</h2>
      <p>Input → extracted claims → checks against external sources → fixed scoring rules → confidence → plain-language explanation. The AI is never asked "is this a scam?".</p>

      <h2 className={h}>What the AI does, and doesn't</h2>
      <ul className="list-disc pl-6">
        <li><strong>Does:</strong> reads messy or regional-language text and extracts claims; rewrites verified findings in simple words.</li>
        <li><strong>Does not:</strong> set the score, invent prices or contract facts, override a source, or decide that an unavailable check "passed".</li>
        <li>Without an AI key, a built-in rule-based reader and template explanation are used.</li>
      </ul>

      <h2 className={h}>Rule-based scoring</h2>
      <p>Each warning sign is a named rule with fixed points, for example a price more than 20% below market, a honeypot indicator, unlimited minting, a very new website or "guaranteed returns" language. Points are added and capped at 100. Every point can be traced to one finding, its evidence and its source.</p>
      <p>Levels: 0-24 Low, 25-49 Moderate, 50-79 High, 80-100 Very High. If nothing could be checked, the report says "Not enough evidence" instead of "safe".</p>

      <h2 className={h}>Risk is not confidence</h2>
      <p>Confidence shows how much of the picture we could actually verify: how many of the six checks returned data, whether you gave us a contract or website to check, and whether data points conflict. A low score with low confidence does not mean an offer is safe.</p>

      <h2 className={h}>Sources</h2>
      <p>CoinGecko / DexScreener / Binance (price and listing), Sourcify and public RPCs (contract verification - no key needed), GoPlus Security (contract risks), DexScreener (liquidity), RDAP (domain age), OpenPhish or Google Safe Browsing (website safety), plus a free local AI model for reading messy offers. Every finding names its source. If a source is unavailable we say so, and it only lowers confidence - never "safe". Demo mode data is simulated and labelled "DEMO DATA".</p>

      <h2 className={h}>Limits</h2>
      <ul className="list-disc pl-6">
        <li>A legitimate new token may not be indexed yet; "not found" is not proof of fraud.</li>
        <li>We never visit the suspect website; we only look up public records about its address.</li>
        <li>Supported contract networks: Ethereum, BNB Smart Chain, Polygon, Arbitrum, Base. Others are reported as unsupported.</li>
        <li>This is a risk assessment, not a legal determination. We do not accuse anyone of wrongdoing, and nothing here is financial advice.</li>
      </ul>
    </main>
  );
}
