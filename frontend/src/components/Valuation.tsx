import { type FormEvent, useState } from "react";

import { ApiError, type Valuation as ValuationData, type WhatIf, useValuation, useWhatIf } from "../api/client";
import { money, pct, toNumber, usd } from "../lib/format";
import { Bar, Button, ErrorBlock, Panel } from "./ui";

type Assumption = ValuationData["assumptions"][number];

function assumptionValue(a: Assumption): string {
  if (a.unit === "ratio") return pct(a.value, { digits: 2 });
  if (a.unit === "years") return `${toNumber(a.value)} years`;
  if (a.unit === "number") return Number(a.value).toFixed(2);
  if (a.unit === "shares") return `${((toNumber(a.value) ?? 0) / 1e6).toLocaleString("en-US", { maximumFractionDigits: 0 })}M`;
  return usd(a.value);
}

function Driver({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="px-6 py-4">
      <dt className="text-small text-muted">{label}</dt>
      <dd className="num mt-1 text-card">{value}</dd>
      <dd className="text-small text-muted">{note}</dd>
    </div>
  );
}

function Sensitivity({ data }: { data: ValuationData }) {
  const grid = data.sensitivity!;
  const base = toNumber(data.derived!.cost_of_capital) ?? 0;
  const baseGrowth = data.assumptions.find((a) => a.key === "stable_growth")?.value;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[480px] text-small">
        <caption className="mb-2 text-left text-muted">
          Value per share as the cost of capital (rows, all phases) and stable growth (columns) change. The base case is highlighted.
        </caption>
        <thead>
          <tr>
            <th scope="col" className="py-1.5 pr-3 text-left font-normal text-muted">Cost of capital</th>
            {grid.stable_growths.map((g) => (
              <th key={g} scope="col" className="num py-1.5 px-2 text-right font-normal text-muted">g {pct(g, { digits: 1 })}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grid.value_per_share.map((row, r) => (
            <tr key={r} className="border-t border-rule">
              <th scope="row" className="num py-1.5 pr-3 text-left font-normal text-soft">
                {pct(base + (toNumber(grid.cost_of_capital_deltas[r]) ?? 0), { digits: 2 })}
              </th>
              {row.map((v, c) => {
                const isBase = toNumber(grid.cost_of_capital_deltas[r]) === 0 && grid.stable_growths[c] === baseGrowth;
                return (
                  <td key={c} className={`num py-1.5 px-2 text-right ${isBase ? "bg-raised font-semibold text-ink" : "text-soft"}`}>
                    {v === null ? <span title="Stable growth would reach the cost of capital">n/a</span> : money(v)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function WhatIfPanel({ data, onResult, onReset, pending, error, submit }: {
  data: ValuationData; onResult: boolean; onReset: () => void; pending: boolean; error: Error | null;
  submit: (body: WhatIf) => void;
}) {
  const editable = data.assumptions.filter((a) => a.editable);
  const shown = (a: Assumption) => (a.unit === "ratio" ? String(Number(((toNumber(a.value) ?? 0) * 100).toFixed(2))) : String(toNumber(a.value)));
  const [draft, setDraft] = useState<Record<string, string>>(() => Object.fromEntries(editable.map((a) => [a.key, shown(a)])));
  const [unchanged, setUnchanged] = useState(false);
  const send = (e: FormEvent) => {
    e.preventDefault();
    // Only what the reader actually edited is an override; untouched fields keep their sourced defaults.
    const body: Record<string, string | number> = {};
    for (const a of editable) {
      const raw = draft[a.key]?.trim();
      if (!raw || raw === shown(a)) continue;
      body[a.key] = a.unit === "ratio" ? String(Number(raw) / 100) : Number(raw);
    }
    setUnchanged(Object.keys(body).length === 0);
    if (Object.keys(body).length) submit(body as WhatIf);
  };
  return (
    <form onSubmit={send} className="rounded-[6px] bg-raised px-4 py-4">
      <p className="mb-3 text-small text-muted">
        Change any assumption and recompute. The filings, risk-free rate and industry data stay as stored, nothing is saved, and no AI is involved.
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {editable.map((a) => (
          <label key={a.key} className="block">
            <span className="block text-small text-muted">{a.label}{a.unit === "ratio" ? " (%)" : a.unit === "years" ? " (years)" : ""}</span>
            <input type="number" step={a.unit === "years" ? 1 : 0.1} inputMode="decimal" value={draft[a.key] ?? ""}
              onChange={(e) => setDraft({ ...draft, [a.key]: e.target.value })}
              className="num mt-1 h-[34px] w-full rounded-[6px] border border-control bg-transparent px-3 focus:border-muted focus:outline-none" />
          </label>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Button type="submit" variant="primary" disabled={pending}>{pending ? "Recomputing…" : "Recompute"}</Button>
        {onResult && <Button onClick={onReset}>Back to the default</Button>}
        {error && <span role="alert" className="text-[var(--pill-negative-ink)]">{error.message}</span>}
        {unchanged && <span role="status" className="text-muted">Change at least one assumption first.</span>}
      </div>
    </form>
  );
}

const POSITION = {
  below_range: { label: "Looks undervalued", tone: "bg-[var(--pill-positive-bg)] text-[var(--pill-positive-ink)]" },
  within_range: { label: "Roughly fair value", tone: "bg-[var(--pill-neutral-bg)] text-[var(--pill-neutral-ink)]" },
  above_range: { label: "Looks overvalued", tone: "bg-[var(--pill-negative-bg)] text-[var(--pill-negative-ink)]" },
} as const;

function readPrice(jobId: string): string {
  try { return localStorage.getItem(`price:${jobId}`) ?? ""; } catch { return ""; }
}

function PriceCheck({ jobId, overrides }: { jobId: string; overrides: WhatIf }) {
  const check = useWhatIf(jobId);
  const [price, setPrice] = useState(() => readPrice(jobId));
  const result = check.data?.price_check;
  const send = (e: FormEvent) => {
    e.preventDefault();
    const value = Number(price);
    if (!(value > 0)) return;
    try { localStorage.setItem(`price:${jobId}`, String(value)); } catch { /* private mode: not remembered */ }
    check.mutate({ ...overrides, market_price: String(value) });
  };
  return (
    <div className="mt-4 rounded-[6px] border border-control px-4 py-4">
      <form onSubmit={send} className="flex flex-wrap items-end gap-3">
        <label className="block">
          <span className="block text-small text-muted">Current share price (you enter it; the app fetches no prices)</span>
          <span className="mt-1 flex items-center gap-1.5">
            <span className="text-muted">$</span>
            <input type="number" min="0.01" step="0.01" inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)}
              placeholder="e.g. 245.50" aria-label="Current share price in US dollars"
              className="num h-[34px] w-36 rounded-[6px] border border-control bg-transparent px-3 focus:border-muted focus:outline-none" />
          </span>
        </label>
        <Button type="submit" variant="primary" disabled={check.isPending || !(Number(price) > 0)}>
          {check.isPending ? "Comparing…" : "Compare with the estimate"}
        </Button>
        {check.isError && <span role="alert" className="text-[var(--pill-negative-ink)]">{check.error.message}</span>}
      </form>
      {result && (
        <div className="mt-4" aria-live="polite">
          <div className="flex flex-wrap items-center gap-3">
            <span className={`inline-flex h-7 items-center rounded-full px-3 font-medium ${POSITION[result.position as keyof typeof POSITION].tone}`}>
              {POSITION[result.position as keyof typeof POSITION].label}
            </span>
            <span className="num text-soft">
              Price {money(result.price)} against an estimate of {money(result.value_per_share)} ({money(result.range_low)} to {money(result.range_high)})
            </span>
          </div>
          <dl className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <dt className="text-small text-muted">Estimate vs price</dt>
              <dd className="num text-card">{pct(result.gap, { sign: true, digits: 0 })}</dd>
            </div>
            <div>
              <dt className="text-small text-muted">Growth the price implies</dt>
              <dd className="num text-card">{result.implied_high_growth ? `${pct(result.implied_high_growth, { digits: 1 })} a year` : "out of range"}</dd>
            </div>
            <div>
              <dt className="text-small text-muted">Growth assumed here</dt>
              <dd className="num text-card">{pct(check.data?.assumptions.find((a) => a.key === "high_growth")?.value, { digits: 1 })} a year</dd>
            </div>
          </dl>
          <p className="mt-3 max-w-[80ch] text-soft">{result.explanation}</p>
          <p className="mt-2 max-w-[80ch] text-small text-muted">
            This compares a price with an estimate built from the assumptions below; change them with "What if" and compare again.
            It is decision support, not investment advice: the estimate can be wrong, and the filings can't see everything the market prices in.
          </p>
        </div>
      )}
    </div>
  );
}

/** The deterministic DCF: headline value, its drivers, every sourced assumption, and a what-if. */
export function ValuationSection({ jobId }: { jobId: string }) {
  const stored = useValuation(jobId);
  const whatIf = useWhatIf(jobId);
  const [open, setOpen] = useState(false);
  const [variant, setVariant] = useState<ValuationData | null>(null);
  const [overrides, setOverrides] = useState<WhatIf>({});

  if (stored.isError) {
    const missing = stored.error instanceof ApiError && stored.error.status === 404;
    return (
      <Panel id="valuation" title="Valuation">
        {missing
          ? <p className="px-6 pb-6 text-muted">This report was written before valuations existed. Run the research again to add one.</p>
          : <ErrorBlock error={stored.error} onRetry={() => stored.refetch()} />}
      </Panel>
    );
  }
  if (!stored.data) {
    return <Panel id="valuation" title="Valuation"><div className="px-6 pb-6"><Bar w="40%" h={28} /><div className="mt-3"><Bar w="80%" h={14} /></div></div></Panel>;
  }
  const base = stored.data;
  if (base.status !== "valued") {
    return (
      <Panel id="valuation" title="Valuation">
        <p className="px-6 pb-6 text-soft">No DCF value for this company: {base.skip_reason}</p>
      </Panel>
    );
  }
  const data = variant ?? base;
  const derived = data.derived!;
  const bridge = data.bridge!;
  const change = variant ? (toNumber(variant.value_per_share)! / toNumber(base.value_per_share)! - 1) : null;
  const overridden = new Set(variant?.overridden ?? []);

  return (
    <Panel id="valuation" title="Valuation" aside={<span>Discounted cash flow, computed from the filings without AI</span>}>
      <div className="px-6 pb-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-small text-muted">{variant ? "What-if intrinsic value per share" : "Intrinsic value per share"}</p>
            <p className="num text-[32px] leading-[40px] font-semibold">{money(data.value_per_share)}</p>
            <p className="text-small text-muted">
              Range <span className="num text-soft">{money(data.range_low)} to {money(data.range_high)}</span> for cost of capital and stable growth ±0.5 points
              {change !== null && <>. Default <span className="num text-soft">{money(base.value_per_share)}</span> ({pct(change, { sign: true })})</>}
            </p>
          </div>
          <Button onClick={() => setOpen(!open)} aria-expanded={open}>{open ? "Hide what-if" : "What if…"}</Button>
        </div>
        <p className="mt-3 max-w-[80ch] text-small text-muted">
          An estimate of what the business is worth from its cash flows: free cash flow to the firm for FY{(data.base_year ?? 0) + 1}–FY{(data.base_year ?? 0) + data.projection.length},
          then a terminal value, discounted at the cost of capital ({data.industry} industry data). Enter today's share price to see
          where it sits against this estimate; the estimate is only as good as the assumptions below.
        </p>
        <PriceCheck key={JSON.stringify(overrides)} jobId={jobId} overrides={overrides} />
        {open && (
          <div className="mt-4">
            <WhatIfPanel data={base} onResult={!!variant} pending={whatIf.isPending} error={whatIf.error}
              onReset={() => { setVariant(null); setOverrides({}); whatIf.reset(); }}
              submit={(body) => whatIf.mutate(body, { onSuccess: (data) => { setVariant(data); setOverrides(body); } })} />
          </div>
        )}
      </div>

      <dl className="grid grid-cols-2 border-t border-rule lg:grid-cols-4 lg:divide-x lg:divide-rule">
        <Driver label="Cost of capital" value={pct(derived.cost_of_capital, { digits: 2 })} note={`stable ${pct(derived.stable_cost_of_capital, { digits: 2 })}`} />
        <Driver label="High growth" value={pct(data.assumptions.find((a) => a.key === "high_growth")?.value, { digits: 1 })}
          note={`${data.assumptions.find((a) => a.key === "high_growth_years")?.value} years, reinvesting ${pct(derived.reinvestment_rate)}`} />
        <Driver label="Stable growth" value={pct(data.assumptions.find((a) => a.key === "stable_growth")?.value, { digits: 1 })}
          note={`reinvesting ${pct(derived.stable_reinvestment_rate)}`} />
        <Driver label="Terminal value share" value={pct(data.terminal?.share_of_operating_value, { digits: 0 })} note="of operating value" />
      </dl>

      <div className="grid grid-cols-1 gap-6 border-t border-rule px-6 py-5 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div className="min-w-0">
          <h3 className="mb-2 font-semibold">Assumptions and sources</h3>
          <table className="w-full text-small">
            <tbody>
              {data.assumptions.map((a) => (
                <tr key={a.key} className="border-t border-rule first:border-t-0">
                  <th scope="row" className="py-1.5 pr-3 text-left font-normal text-soft">
                    {a.label}{overridden.has(a.key) && <span className="ml-2 rounded-full bg-[var(--pill-warning-bg)] px-2 text-[var(--pill-warning-ink)]">changed</span>}
                  </th>
                  <td className="num py-1.5 pr-3 text-right whitespace-nowrap">{assumptionValue(a)}</td>
                  <td className="py-1.5 text-muted [overflow-wrap:anywhere]">{a.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="min-w-0">
          <h3 className="mb-2 font-semibold">From firm value to value per share</h3>
          <dl className="text-small">
            {([
              ["Present value of cash flows", bridge.present_value_of_fcff, ""],
              ["Present value of terminal value", bridge.present_value_of_terminal, ""],
              ["Operating value", bridge.operating_value, "total"],
              ["+ Cash", bridge.cash, ""],
              ["+ Short-term investments", bridge.non_operating_assets, ""],
              ["− Debt", bridge.debt, ""],
              ["− Minority interest", bridge.minority_interest, ""],
              ["Equity value", bridge.equity_value, "total"],
            ] as const).map(([label, value, kind]) => (
              <div key={label} className={`flex justify-between gap-4 py-1.5 ${kind === "total" ? "border-t border-rule font-semibold" : ""}`}>
                <dt className={kind ? "text-ink" : "text-soft"}>{label}</dt>
                <dd className="num">{usd(value)}</dd>
              </div>
            ))}
            <div className="flex justify-between gap-4 py-1.5">
              <dt className="text-soft">÷ Diluted shares</dt>
              <dd className="num">{`${((toNumber(bridge.shares) ?? 0) / 1e6).toLocaleString("en-US", { maximumFractionDigits: 0 })}M`}</dd>
            </div>
            <div className="flex justify-between gap-4 border-t border-rule py-1.5 font-semibold">
              <dt>Value per share</dt>
              <dd className="num">{money(bridge.value_per_share)}</dd>
            </div>
          </dl>
        </div>
      </div>

      <div className="border-t border-rule px-6 py-5">
        <h3 className="mb-2 font-semibold">Projected free cash flow to the firm</h3>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-small">
            <thead>
              <tr className="text-muted">
                {["Year", "Growth", "After-tax EBIT", "Reinvestment", "Free cash flow", "Cost of capital", "Present value"].map((h, i) => (
                  <th key={h} scope="col" className={`py-1.5 font-normal ${i === 0 ? "text-left" : "text-right"}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.projection.map((row) => (
                <tr key={row.year} className="border-t border-rule">
                  <th scope="row" className="num py-1.5 text-left font-normal">FY{row.fiscal_year}</th>
                  <td className="num py-1.5 text-right">{pct(row.growth, { digits: 1 })}</td>
                  <td className="num py-1.5 text-right">{usd(row.after_tax_ebit)}</td>
                  <td className="num py-1.5 text-right">{usd(row.reinvestment)}</td>
                  <td className="num py-1.5 text-right">{usd(row.fcff)}</td>
                  <td className="num py-1.5 text-right">{pct(row.cost_of_capital, { digits: 2 })}</td>
                  <td className="num py-1.5 text-right">{usd(row.present_value)}</td>
                </tr>
              ))}
              <tr className="border-t border-rule font-semibold">
                <th scope="row" className="py-1.5 text-left">Terminal</th>
                <td className="num py-1.5 text-right">{pct(data.assumptions.find((a) => a.key === "stable_growth")?.value, { digits: 1 })}</td>
                <td className="num py-1.5 text-right">{usd(data.terminal?.after_tax_ebit)}</td>
                <td className="num py-1.5 text-right">{pct(data.terminal?.reinvestment_rate)}</td>
                <td className="num py-1.5 text-right">{usd(data.terminal?.fcff)}</td>
                <td className="num py-1.5 text-right">{pct(derived.stable_cost_of_capital, { digits: 2 })}</td>
                <td className="num py-1.5 text-right">{usd(data.terminal?.present_value)}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div className="border-t border-rule px-6 py-5"><Sensitivity data={data} /></div>

      {data.warnings.length > 0 && (
        <div className="border-t border-rule px-6 py-4">
          <h3 className="mb-1 text-small font-medium text-muted">Notes on this valuation</h3>
          <ul className="list-disc space-y-1 pl-5 text-small text-soft marker:text-muted">
            {data.warnings.map((w) => <li key={w}>{w}</li>)}
          </ul>
        </div>
      )}
      <p className="px-6 pb-5 text-small text-muted">
        Method: Damodaran, <i>Damodaran on Valuation</i>, ch. 2 (FCFF, three stages). Calculation version <span className="num">{data.calculation_version}</span>.
      </p>
    </Panel>
  );
}
