const topics: [string, string, string][] = [
  ["Below-market 'cheap coin' offers", "A seller offers Bitcoin or Ethereum at a steep discount. Anyone with real coins could sell at the market price instantly, so a large discount means the 'deal' is the bait.", "Compare with a market-data site (CoinGecko, CoinMarketCap) yourself. Be wary of pay-first, deliver-later arrangements."],
  ["Fake or new token scams", "Creators launch a token, hype it on social media, and disappear with the money once enough people buy.", "Check whether the token is listed on a recognised data source and whether the contract address matches the project's official site."],
  ["Unrealistic-return promises", "'Guaranteed', 'risk-free', or 'double in 30 days' claims. Real investments can lose money, and doubling in a month implies more than 1,000% a year.", "Ask who is actually paying the return. If the answer is new depositors, it is a Ponzi-style scheme."],
  ["Honeypots", "A honeypot is a token setup that may allow people to buy the token but prevent or severely restrict them from selling it.", "Scan the contract with a security tool before buying, and never rely on the seller's own 'proof' screenshots."],
  ["Hidden minting and owner powers", "Contracts can let the owner create unlimited tokens, edit balances, pause trading or take back ownership after pretending to give it up.", "Look for a verified contract, a credible independent audit, and renounced or time-locked owner rights."],
  ["Liquidity tricks (rug pulls)", "Liquidity is the money pool that makes trading possible. Creators can add tiny liquidity, fake volume, or withdraw the pool, leaving holders unable to sell.", "Check total liquidity, whether it is locked, and whether both buys and sells are happening."],
  ["Referral and recruitment schemes", "Rewards for bringing in friends and family make the scheme spread through trusted relationships and hide the lack of any real product.", "If you earn mainly by recruiting, treat it as a red flag, however it is described."],
  ["Phishing and fake websites", "Look-alike sites, new domains and urgent messages are used to steal logins, wallets and payments.", "Type the official address yourself, check how old the site is, and don't connect your wallet to unfamiliar sites."],
  ["Protecting your wallet", "Your seed phrase and private key control your funds completely. Support staff, 'recovery agents' and 'validators' never need them.", "Never share your seed phrase, private key, OTP, password or recovery phrase. Keep a hardware wallet for larger amounts."],
];

export default function Learn() {
  return (
    <main id="main" tabIndex={-1} className="mx-auto max-w-3xl px-4 py-12">
      <h1 className="text-3xl font-bold md:text-4xl">Learn how crypto scams work</h1>
      <p className="mt-3 text-lg text-muted">Plain-language explanations of the warning signs this tool looks for.</p>
      <div className="mt-8 space-y-4">
        {topics.map(([t, what, tip]) => (
          <article key={t} className="card p-5">
            <h2 className="text-xl font-semibold">{t}</h2>
            <p className="mt-2">{what}</p>
            <p className="mt-3 rounded-md bg-brand-tint p-3 text-sm"><strong>What to do:</strong> {tip}</p>
          </article>
        ))}
      </div>
      <p className="mt-8"><a href="#/check" className="btn-primary">Check an offer</a></p>
    </main>
  );
}
