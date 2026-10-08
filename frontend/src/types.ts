export type CheckStatus = "verified" | "not_found" | "unavailable" | "not_applicable";

export interface Health {
  ok: boolean;
  default_mode: "demo" | "live";
  sources: Record<string, boolean>;
  chains: Record<string, string>;
  max_input_chars: number;
  llm_provider: string;
  llm: { available: boolean; model: string | null; models: string[] };
  zero_cost_ready: boolean;
}
export interface Scenario {
  id: string;
  title: string;
  blurb: string;
  inputs: { text: string; url: string; token_name: string; contract_address: string; chain: string };
}
export interface Check {
  check_id: string;
  label: string;
  source: string;
  status: CheckStatus;
  summary: string;
  reason: string | null;
  timestamp: string;
  demo: boolean;
  data?: Record<string, unknown> | null;
}
export interface Finding {
  rule_id: string;
  title: string;
  severity: "ok" | "low" | "medium" | "high" | "critical";
  points: number;
  observed: string;
  why: string;
  explanation: string;
  source: string;
  check_id: string;
  status: string;
  timestamp: string;
  demo: boolean;
}
export interface Claims {
  asset_name: string | null;
  asset_symbol: string | null;
  contract_address: string | null;
  chain: string | null;
  claimed_price: number | null;
  quoted_currency: string | null;
  quantity: number | null;
  quantity_assumed: boolean;
  claimed_market_price: number | null;
  promised_return_pct: number | null;
  promised_multiplier: number | null;
  return_period_days: number | null;
  guaranteed_language: boolean;
  referral: boolean;
  urgency: boolean;
  limited_time: boolean;
  requests_secrets: boolean;
  seller_identity: string | null;
  entity_name?: string | null;
  website_url: string | null;
  other_flags: string[];
}
export interface Report {
  mode: "demo" | "live";
  is_demo: boolean;
  demo_scenario: string | null;
  generated_at: string;
  claims: Claims;
  extraction: { method: string; llm_configured: boolean; llm_provider?: string | null; notes: string[] };
  checks: Check[];
  findings: Finding[];
  risk: {
    score: number;
    raw_points: number;
    level: string;
    level_key: string;
    insufficient_evidence: boolean;
    outcome?: "verified-legit" | "suspicious" | "could-not-verify";
    outcome_label?: string;
  };
  confidence: { score: number; level: "High" | "Medium" | "Low"; reasons: string[] };
  coverage: {
    available: number;
    total: number;
    unavailable: { check_id: string; label: string; source: string; reason: string }[];
    not_applicable: { check_id: string; label: string; reason: string }[];
  };
  conflicts: string[];
  summary: { text: string; method: "template" | "llm"; language: string };
  checklist: string[];
  never_share: string;
  disclaimers: string[];
}
export interface FormState {
  text: string;
  url: string;
  token_name: string;
  contract_address: string;
  chain: string;
  website: string;
  tokenCont: string;
  mode: "demo" | "live";
  demo_scenario: string | null;
  lang: string;
}
export const emptyForm = (mode: "demo" | "live" = "demo"): FormState => ({
  text: "", url: "", token_name: "", contract_address: "", chain: "", website: "", tokenCont: "", mode, demo_scenario: null, lang: "en",
});
export interface FieldError { field: string | null; message: string }
