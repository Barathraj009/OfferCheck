const steps = [
  ["Read the claims", "The offer text, screenshot, link or voice note is turned into structured claims: price, promised return, referral rewards, deadlines."],
  ["Check the facts", "Claims are compared with market data, the token contract, liquidity, the website's age and safety lists. Sources that can't be reached are marked unavailable, never assumed safe."],
  ["Score with fixed rules", "A transparent rule engine adds points for each warning sign. Every point links to one finding and its source. AI does not set the score."],
  ["Explain in plain words", "You get what was claimed, what was verified, what contradicts it, how confident the check is, and what to verify yourself."],
];

export default function Home() {
  return (
    <main id="main" tabIndex={-1}>
      <section className="border-b border-rule">
        <div className="mx-auto grid max-w-5xl gap-10 px-4 py-14 md:grid-cols-[1.1fr_1fr] md:items-center">
          <div>
            <h1 className="text-4xl font-bold md:text-5xl">Check the offer before you send the money.</h1>
            <p className="mt-5 max-w-prose text-lg text-muted">
              Someone is selling you Bitcoin cheaply, or a new token that promises to multiply your money? Paste the message, upload the poster or enter the contract. You get an evidence-based risk report in minutes.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              <a href="#/check" className="btn-primary">Check an offer</a>
              <a href="#/learn" className="btn-ghost">How these scams work</a>
            </div>
            <p className="mt-4 text-sm text-muted">Works without any account. Demo mode runs without API keys and always labels sample data.</p>
          </div>
          <figure aria-label="Example scam message with warning signs marked" className="card p-5">
            <figcaption className="mb-3 text-sm font-semibold text-muted">An example message, and what we look at</figcaption>
            <p className="leading-8">
              Bitcoin for <mark className="rounded bg-signal-tint px-1">₹32 lakh only</mark>. <mark className="rounded bg-amber-tint px-1">Pay within 2 hours</mark>, only 2 slots left.{" "}
              <mark className="rounded bg-signal-tint px-1">Guaranteed to double</mark> your money in 30 days.{" "}
              <mark className="rounded bg-amber-tint px-1">Refer 3 friends</mark> and earn commission.
            </p>
            <ul className="mt-4 space-y-2 border-t border-rule pt-4 text-sm">
              <li><span className="chip bg-signal-tint text-signal">Compared with live price</span> <span className="text-muted">Is it far below the market?</span></li>
              <li><span className="chip bg-signal-tint text-signal">Realistic?</span> <span className="text-muted">Doubling in a month is over 1,000% a year.</span></li>
              <li><span className="chip bg-amber-tint text-amber">Pressure tactics</span> <span className="text-muted">Deadlines and recruiting rewards.</span></li>
            </ul>
          </figure>
        </div>
      </section>

      <section className="mx-auto max-w-5xl px-4 py-14">
        <h2 className="text-2xl font-bold md:text-3xl">Two tricks behind most crypto scams</h2>
        <div className="mt-6 grid gap-5 md:grid-cols-2">
          <div className="card p-5"><h3 className="text-xl font-semibold">Famous coins at a "too good" price</h3><p className="mt-2 text-muted">Sellers rely on you not knowing the real price of Bitcoin or Ethereum. A big discount is the bait; the payment is the trap.</p></div>
          <div className="card p-5"><h3 className="text-xl font-semibold">New tokens with trapdoors</h3><p className="mt-2 text-muted">"10x returns" tokens can hide contracts that let you buy but not sell, mint unlimited tokens, or drain the liquidity.</p></div>
        </div>
      </section>

      <section className="border-t border-rule bg-panel">
        <div className="mx-auto max-w-5xl px-4 py-14">
          <h2 className="text-2xl font-bold md:text-3xl">How a check works</h2>
          <ol className="mt-8 grid gap-6 md:grid-cols-2">
            {steps.map(([t, d], i) => (
              <li key={t} className="flex gap-4">
                <span className="flex h-9 w-9 flex-none items-center justify-center rounded-full bg-brand font-display font-bold text-white" aria-hidden>{i + 1}</span>
                <div><h3 className="text-lg font-semibold">{t}</h3><p className="mt-1 text-muted">{d}</p></div>
              </li>
            ))}
          </ol>
          <p className="mt-10 rounded-md border border-signal/40 bg-signal-tint p-4 font-medium text-signal">Never share your wallet seed phrase, private key, OTP, password, or recovery phrase with anyone. This tool will never ask for them.</p>
        </div>
      </section>
    </main>
  );
}
