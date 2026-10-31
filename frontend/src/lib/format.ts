import type { JobStatus, Stage } from "../api/client";

/** Display-only formatting. All arithmetic happens server-side in Decimal. */

const DASH = "—";

export function toNumber(value: string | number | null | undefined): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : null;
}

export function usd(value: string | number | null | undefined, opts: { compact?: boolean; sign?: boolean } = {}): string {
  const n = toNumber(value);
  if (n === null) return DASH;
  const sign = n < 0 ? "-" : opts.sign && n > 0 ? "+" : "";
  const abs = Math.abs(n);
  if (opts.compact !== false) {
    for (const [threshold, suffix] of [[1e12, "T"], [1e9, "B"], [1e6, "M"]] as const) {
      if (abs >= threshold) return `${sign}$${(abs / threshold).toFixed(2)}${suffix}`;
    }
  }
  return `${sign}$${abs.toLocaleString("en-US", { maximumFractionDigits: 2, minimumFractionDigits: abs < 100 ? 2 : 0 })}`;
}

/** API spend: small amounts need sub-cent precision ("$0.0401"); a dollar or more reads in cents ("$1.27"). */
export function money(value: string | number | null | undefined): string {
  const n = toNumber(value);
  if (n === null) return DASH;
  if (n === 0) return "$0.00";
  const abs = Math.abs(n);
  if (abs < 0.0001) return `${n < 0 ? "-" : ""}<$0.0001`;
  const digits = abs >= 1 ? 2 : abs >= 0.01 ? 3 : 4;
  return `${n < 0 ? "-" : ""}$${abs.toFixed(digits)}`;
}

/** Token counts: "8,412", "521.5k", "1.20M". */
export function tokens(value: number | null | undefined): string {
  if (value === null || value === undefined) return DASH;
  if (value >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  if (value >= 1e4) return `${(value / 1e3).toFixed(1)}k`;
  return value.toLocaleString("en-US");
}

/** Axis ticks: "$300B", "$1.5T", "$25M"; no trailing decimals. */
export function usdTick(value: number): string {
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  for (const [threshold, suffix] of [[1e12, "T"], [1e9, "B"], [1e6, "M"]] as const) {
    if (abs >= threshold) return `${sign}$${Number((abs / threshold).toFixed(1))}${suffix}`;
  }
  return `${sign}$${Number(abs.toFixed(0)).toLocaleString("en-US")}`;
}

export function pct(value: string | number | null | undefined, opts: { sign?: boolean; digits?: number } = {}): string {
  const n = toNumber(value);
  if (n === null) return DASH;
  const text = (n * 100).toFixed(opts.digits ?? 1);
  return `${opts.sign && n > 0 ? "+" : ""}${text}%`;
}

export function times(value: string | number | null | undefined): string {
  const n = toNumber(value);
  return n === null ? DASH : `${n.toFixed(2)}x`;
}

/** Reader-facing metric value; negative net debt reads as net cash, never as "-$2.1B of debt". */
export function metricDisplay(key: string, value: string, unit: string, opts: { sign?: boolean } = {}): string {
  const n = toNumber(value);
  if (key === "net_debt" && n !== null && n < 0) return `Net cash ${usd(-n)}`;
  return metricValue(value, unit, opts);
}

export function changeText(now: number, before: number, kind: "pct" | "pp"): string {
  if (kind === "pp") {
    const diff = (now - before) * 100;
    return `${diff > 0 ? "+" : ""}${diff.toFixed(1)} pts`;
  }
  if (before === 0) return "—";
  const change = (now - before) / Math.abs(before);
  return `${change > 0 ? "+" : ""}${(change * 100).toFixed(1)}%`;
}

export function metricValue(value: string, unit: string, opts: { sign?: boolean } = {}): string {
  if (unit === "ratio") return pct(value, opts);
  if (unit === "times") return times(value);
  if (unit === "USD") return usd(value, opts);
  if (unit === "USD/shares" || unit === "USD/share") return usd(value, { compact: false });
  return value;
}

export function fieldValue(name: string, value: string | null): string {
  if (name === "eps") return usd(value, { compact: false });
  if (name === "diluted_shares") {
    const n = toNumber(value);
    return n === null ? DASH : `${(n / 1e6).toLocaleString("en-US", { maximumFractionDigits: 0 })}M`;
  }
  return usd(value);
}

export function date(value: string | null | undefined, opts: Intl.DateTimeFormatOptions = { year: "numeric", month: "short", day: "numeric" }): string {
  if (!value) return DASH;
  const d = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  return d.toLocaleDateString("en-US", opts);
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return DASH;
  return new Date(value).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function relative(value: string | null | undefined, now = Date.now()): string {
  if (!value) return DASH;
  const seconds = Math.round((now - new Date(value).getTime()) / 1000);
  if (seconds < 45) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
  const days = Math.round(seconds / 86400);
  return days === 1 ? "yesterday" : `${days} days ago`;
}

export function duration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return DASH;
  if (ms < 1000) return `${ms}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${String(Math.round(s % 60)).padStart(2, "0")}s`;
  return `${Math.floor(s / 3600)}h ${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}m`;
}

export function elapsed(from: string | null | undefined, to?: string | null): string {
  if (!from) return DASH;
  return duration((to ? new Date(to).getTime() : Date.now()) - new Date(from).getTime());
}

export const STAGES: { key: Stage; label: string; detail: string }[] = [
  { key: "resolving_company", label: "Resolve company", detail: "Ticker to SEC CIK, industry check" },
  { key: "fetching_filings", label: "Fetch filings", detail: "Latest 10-K and any newer 10-Q" },
  { key: "extracting_financials", label: "Extract financials", detail: "Five fiscal years from XBRL" },
  { key: "computing_metrics", label: "Compute metrics", detail: "Margins, growth, cash flow, debt ratios" },
  { key: "valuing", label: "Value (DCF)", detail: "Intrinsic value from the filings, no AI" },
  { key: "indexing_documents", label: "Index filings", detail: "Sections, chunks, 768-d embeddings" },
  { key: "planning", label: "Plan", detail: "Split the question into sub-questions" },
  { key: "researching", label: "Research", detail: "Parallel agents search filings and metrics" },
  { key: "drafting", label: "Draft", detail: "Claims from the researchers' evidence" },
  { key: "verifying", label: "Verify", detail: "Quotes, numbers, fact-check; re-research failures" },
  { key: "synthesizing", label: "Write report", detail: "Summary, scenarios, risks" },
];

export const STATUS_LABEL: Record<JobStatus, string> = {
  queued: "Queued",
  running: "Running",
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
};

export const VERIFICATION_LABEL: Record<string, string> = {
  supported: "Supported",
  partially_supported: "Partly supported",
  unsupported: "Unsupported",
  not_verified: "Not verified",
};

export const CLAIM_TYPE_LABEL: Record<string, string> = {
  fact: "Reported fact",
  calculation: "Calculation",
  interpretation: "Interpretation",
};

export const SECTION_LABEL: Record<string, string> = {
  business: "Business",
  growth: "Growth",
  profitability: "Profitability",
  cash_flow: "Cash flow",
  balance_sheet: "Balance sheet",
  risks: "Risks",
  outlook: "Outlook",
  analysis: "Analysis",
};

export const FIELD_LABEL: Record<string, string> = {
  revenue: "Revenue",
  cost_of_revenue: "Cost of revenue",
  gross_profit: "Gross profit",
  operating_income: "Operating income",
  net_income: "Net income",
  eps: "Diluted EPS",
  diluted_shares: "Diluted shares",
  operating_cash_flow: "Operating cash flow",
  capital_expenditure: "Capital expenditure",
  research_and_development: "R&D expense",
  interest_expense: "Interest expense",
  cash: "Cash and equivalents",
  current_assets: "Current assets",
  current_liabilities: "Current liabilities",
  total_assets: "Total assets",
  total_liabilities: "Total liabilities",
  stockholders_equity: "Stockholders' equity",
  debt: "Long-term debt",
};
