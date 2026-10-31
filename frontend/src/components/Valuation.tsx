import { type FormEvent, type ReactNode, useState } from "react";

import { ApiError, type Valuation as ValuationData, type WhatIf, useValuation, useWhatIf } from "../api/client";
import { dateTime, money, pct, toNumber, usd } from "../lib/format";
import { Bar, Button, ErrorBlock, Panel } from "./ui";

type Assumption = ValuationData["assumptions"][number];

const METHOD_LABEL: Record<string, string> = { dcf: "Cash-flow DCF", epv: "Earnings power" };

function assumption(data: ValuationData, key: string): Assumption | undefined {
  return data.assumptions.find((a) => a.key === key);
}

function shares(value: string | number | null | undefined): string {
  return `${((toNumber(value) ?? 0) / 1e6).toLocaleString("en-US", { maximumFractionDigits: 0 })}M`;
}

function assumptionValue(a: Assumption): string {
  if (a.unit === "ratio") return pct(a.value, { digits: 2 });
  if (a.unit === "years") return `${toNumber(a.value)} years`;
  if (a.unit === "number") return Number(a.value).toFixed(2);
  if (a.unit === "shares") return shares(a.value);
  return usd(a.value);
}

const POSITION = {
  below_range: { label: "Looks undervalued", tone: "bg-[var(--pill-positive-bg)] text-[var(--pill-positive-ink)]" },
  within_range: { label: "Roughly fairly valued", tone: "bg-[var(--pill-neutral-bg)] text-[var(--pill-neutral-ink)]" },
  above_range: { label: "Looks overvalued", tone: "bg-[var(--pill-negative-bg)] text-[var(--pill-negative-ink)]" },
} as const;

/** One scale with each method's value, the fair-value range and the share price, so the gap is visible at a glance. */
function MethodsScale({ data }: { data: ValuationData }) {
  const points = [
    ...data.methods_used.map((m) => ({ key: m, label: METHOD_LABEL[m] ?? m, value: toNumber(m === "dcf" ? data.dcf?.value_per_share : data.epv?.value_per_share) })),
  ].filter((p): p is { key: string; label: string; value: number } => p.value !== null);
  const price = toNumber(data.market_price?.price);
  const low = toNumber(data.range_low) ?? 0;
  const high = toNumber(data.range_high) ?? 0;
  const fair = toNumber(data.fair_value) ?? 0;
  const max = Math.max(high, price ?? 0, ...points.map((p) => p.value)) * 1.08 || 1;
  const at = (v: number) => `${Math.max(0, Math.min(100, (v / max) * 100))}%`;
  const described = [
    ...points.map((p) => `${p.label} ${money(p.value)}`),
    `fair value ${money(fair)} (range ${money(low)} to ${money(high)})`,
    price !== null ? `share price ${money(price)}` : "no share price",
  ].join(", ");

  return (
    <figure className="mt-5">
      <div role="img" aria-label={`Values per share on one scale: ${described}.`} className="relative h-12">
        <div className="absolute inset-x-0 top-[22px] h-px bg-[var(--control)]" />
        <div className="absolute top-[14px] h-[17px] rounded-[3px] bg-[color-mix(in_srgb,var(--accent)_22%,transparent)]"
          style={{ left: at(low), width: `calc(${at(high)} - ${at(low)})`, minWidth: 2 }} />
        {points.map((p) => (
          <div key={p.key} className="absolute top-[10px] h-[25px] w-px bg-soft" style={{ left: at(p.value) }} />
        ))}
        <div className="absolute top-[6px] h-[33px] w-[2px] -translate-x-1/2 bg-[var(--accent)]" style={{ left: at(fair) }} />
        {price !== null && (
          <div className="absolute top-0 h-12 w-[2px] -translate-x-1/2 bg-ink" style={{ left: at(price) }}>
            <span className={`num absolute -top-0.5 whitespace-nowrap text-small text-ink ${price / max > 0.75 ? "right-1.5" : "left-1.5"}`}>price</span>
          </div>
        )}
      </div>
      <figcaption className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-small text-muted">
        {points.map((p) => <span key={p.key}><span className="inline-block h-3 w-px translate-y-0.5 bg-soft" /> {p.label} <span className="num text-soft">{money(p.value)}</span></span>)}
        <span><span className="inline-block h-3 w-[2px] translate-y-0.5 bg-[var(--accent)]" /> Fair value <span className="num text-soft">{money(fair)}</span></span>
        <span><span className="inline-block h-2.5 w-4 rounded-[2px] bg-[color-mix(in_srgb,var(--accent)_22%,transparent)]" /> Range <span className="num text-soft">{money(low)}–{money(high)}</span></span>
        {price !== null && <span><span className="inline-block h-3 w-[2px] translate-y-0.5 bg-ink" /> Price <span className="num text-soft">{money(price)}</span></span>}
      </figcaption>
    </figure>
  );
}

function readPrice(jobId: string): string {
  try { return localStorage.getItem(`price:${jobId}`) ?? ""; } catch { return ""; }
}

function PriceBlock({ data, jobId, typed, onPrice, pending, error }: {
  data: ValuationData; jobId: string; typed: string | null; onPrice: (price: string | null) => void; pending: boolean; error: Error | null;
}) {
  const [draft, setDraft] = useState(() => typed ?? readPrice(jobId));
  const [editing, setEditing] = useState(false);
  const quote = data.market_price;
  const check = data.price_check;
  const growth = assumption(data, "initial_growth");
  const years = assumption(data, "high_growth_years");
  const send = (e: FormEvent) => {
    e.preventDefault();
    if (!(Number(draft) > 0)) return;
    try { localStorage.setItem(`price:${jobId}`, String(Number(draft))); } catch { /* private mode: not remembered */ }
    onPrice(String(Number(draft)));
    setEditing(false);
  };

  return (
    <div className="mt-5 rounded-[6px] border border-control px-4 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-small text-muted">Share price</p>
          {quote ? (
            <>
              <p className="num text-card">{money(quote.price)}</p>
              <p className="text-small text-muted">
                {quote.source}{quote.as_of && <>, <span className="num">{dateTime(quote.as_of)}</span></>}
              </p>
            </>
          ) : (
            <p className="text-soft">No delayed quote is available right now. Enter the price to compare.</p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {typed && <Button onClick={() => { onPrice(null); setEditing(false); }}>Use the delayed quote</Button>}
          {!editing && quote && <Button onClick={() => setEditing(true)}>Enter a price</Button>}
        </div>
      </div>

      {(editing || !quote) && (
        <form onSubmit={send} className="mt-3 flex flex-wrap items-end gap-3">
          <label className="block">
            <span className="block text-small text-muted">Share price in US dollars</span>
            <span className="mt-1 flex items-center gap-1.5">
              <span className="text-muted">$</span>
              <input type="number" min="0.01" step="0.01" inputMode="decimal" value={draft} onChange={(e) => setDraft(e.target.value)}
                placeholder="e.g. 245.50"
                className="num h-[34px] w-36 rounded-[6px] border border-control bg-transparent px-3 focus:border-muted focus:outline-none" />
            </span>
          </label>
          <Button type="submit" variant="primary" disabled={pending || !(Number(draft) > 0)}>{pending ? "Comparing…" : "Compare"}</Button>
          {editing && <Button onClick={() => setEditing(false)}>Cancel</Button>}
        </form>
      )}
      {error && <p role="alert" className="mt-2 text-[var(--pill-negative-ink)]">{error.message}</p>}

      {check && (
        <div className="mt-4 border-t border-rule pt-4" aria-live="polite">
          <span className={`inline-flex h-7 items-center rounded-full px-3 font-medium ${POSITION[check.position as keyof typeof POSITION].tone}`}>
            {POSITION[check.position as keyof typeof POSITION].label}
          </span>
          <dl className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <dt className="text-small text-muted">Fair value vs price</dt>
              <dd className="num text-card">{pct(check.gap, { sign: true, digits: 0 })}</dd>
            </div>
            <div>
              <dt className="text-small text-muted">Growth the price implies</dt>
              <dd className="num text-card">{check.implied_growth ? `${pct(check.implied_growth, { digits: 1 })} a year` : "out of range"}</dd>
              <dd className="text-small text-muted">for {toNumber(years?.value)} years, then fading</dd>
            </div>
            <div>
              <dt className="text-small text-muted">Growth assumed here</dt>
              <dd className="num text-card">{pct(growth?.value, { digits: 1 })} a year</dd>
              <dd className="text-small text-muted">{data.overridden.includes("initial_growth") ? "your what-if" : "from the revenue record"}</dd>
            </div>
          </dl>
          <p className="mt-3 max-w-[80ch] text-soft">{check.explanation}</p>
          <p className="mt-2 max-w-[80ch] text-small text-muted">
            Decision support, not investment advice. The fair value is only as good as the assumptions below, and the
            filings can't see everything the market prices in. If you believe faster growth is coming, test it with "What if".
          </p>
        </div>
      )}
    </div>
  );
}

function WhatIfPanel({ data, active, onReset, pending, error, submit }: {
  data: ValuationData; active: boolean; onReset: () => void; pending: boolean; error: Error | null;
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
        Change any assumption and recompute. The filings, Treasury yield and industry data stay as stored, nothing is saved, and no AI is involved.
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
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
        {active && <Button onClick={onReset}>Back to the default</Button>}
        {error && <span role="alert" className="text-[var(--pill-negative-ink)]">{error.message}</span>}
        {unchanged && <span role="status" className="text-muted">Change at least one assumption first.</span>}
      </div>
    </form>
  );
}

function Driver({ label, value, note }: { label: string; value: string; note: ReactNode }) {
  return (
    <div className="px-6 py-4">
      <dt className="text-small text-muted">{label}</dt>
      <dd className="num mt-1 text-card">{value}</dd>
      <dd className="text-small text-muted">{note}</dd>
    </div>
  );
}

function Lines({ rows }: { rows: [string, ReactNode, "total" | ""][] }) {
  return (
    <dl className="text-small">
      {rows.map(([label, value, kind]) => (
        <div key={label} className={`flex justify-between gap-4 py-1.5 ${kind === "total" ? "border-t border-rule font-semibold" : ""}`}>
          <dt className={kind ? "text-ink" : "text-soft"}>{label}</dt>
          <dd className="num whitespace-nowrap">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Th({ children, left }: { children: ReactNode; left?: boolean }) {
  return <th scope="col" className={`py-1.5 font-normal ${left ? "text-left" : "text-right"}`}>{children}</th>;
}

function Sensitivity({ data }: { data: ValuationData }) {
  const grid = data.sensitivity!;
  const wacc = toNumber(data.cost_of_capital?.cost_of_capital) ?? 0;
  const growth = toNumber(assumption(data, "initial_growth")?.value) ?? 0;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[480px] text-small">
        <caption className="mb-2 text-left text-muted">
          Cash-flow DCF value per share as the cost of capital (rows) and the first years' growth (columns) change. The base case is highlighted.
        </caption>
        <thead>
          <tr className="text-muted">
            <Th left>Cost of capital</Th>
            {grid.growth_deltas.map((d) => <Th key={d}>growth {pct(Math.max(growth + (toNumber(d) ?? 0), 0), { digits: 1 })}</Th>)}
          </tr>
        </thead>
        <tbody>
          {grid.value_per_share.map((row, r) => (
            <tr key={r} className="border-t border-rule">
              <th scope="row" className="num py-1.5 pr-3 text-left font-normal text-soft">
                {pct(wacc + (toNumber(grid.cost_of_capital_deltas[r]) ?? 0), { digits: 2 })}
              </th>
              {row.map((v, c) => {
                const isBase = toNumber(grid.cost_of_capital_deltas[r]) === 0 && toNumber(grid.growth_deltas[c]) === 0;
                return (
                  <td key={c} className={`num py-1.5 px-2 text-right ${isBase ? "bg-raised font-semibold text-ink" : "text-soft"}`}>
                    {v === null ? <span title="Long-run growth would reach the cost of capital">n/a</span> : money(v)}
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

/** The deterministic fair value: a blend of a cash-flow DCF and earnings power, set against the share price. */
export function ValuationSection({ jobId }: { jobId: string }) {
  const stored = useValuation(jobId);
  const recompute = useWhatIf(jobId);
  const [open, setOpen] = useState(false);
  const [variant, setVariant] = useState<ValuationData | null>(null);
  const [overrides, setOverrides] = useState<WhatIf>({});
  const [typed, setTyped] = useState<string | null>(null);

  const run = (nextOverrides: WhatIf, nextPrice: string | null) => {
    setOverrides(nextOverrides);
    setTyped(nextPrice);
    if (!Object.keys(nextOverrides).length && !nextPrice) {
      setVariant(null);
      recompute.reset();
      return;
    }
    recompute.mutate({ ...nextOverrides, ...(nextPrice ? { market_price: nextPrice } : {}) }, { onSuccess: setVariant });
  };

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
        <p className="px-6 pb-6 text-soft">No fair value for this company: {base.skip_reason}</p>
      </Panel>
    );
  }
  const data = variant ?? base;
  const whatIf = data.what_if;
  const change = whatIf ? (toNumber(data.fair_value)! / toNumber(base.fair_value)! - 1) : null;
  const overridden = new Set(data.overridden);
  const coc = data.cost_of_capital!;
  const dcf = data.dcf;
  const epv = data.epv;
  const value = (key: string) => assumption(data, key)?.value;
  const bridge = (enterprise: string | number): [string, ReactNode, "total" | ""][] => [
    ["+ Cash", usd(value("cash")), ""],
    ["+ Short-term investments", usd(value("non_operating_assets")), ""],
    ["− Debt", usd(value("debt")), ""],
    ["− Minority interest", usd(value("minority_interest")), ""],
    ["Equity value", usd(toNumber(enterprise)! + (toNumber(value("cash")) ?? 0) + (toNumber(value("non_operating_assets")) ?? 0) - (toNumber(value("debt")) ?? 0) - (toNumber(value("minority_interest")) ?? 0)), "total"],
    ["÷ Diluted shares", shares(value("shares")), ""],
  ];

  return (
    <Panel id="valuation" title="Valuation" aside={<span>Computed from the filings without AI</span>}>
      <div className="px-6 pb-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-small text-muted">{whatIf ? "What-if fair value per share" : "Fair value per share"}</p>
            <p className="num text-[32px] leading-[40px] font-semibold">{money(data.fair_value)}</p>
            <p className="text-small text-muted">
              Range <span className="num text-soft">{money(data.range_low)} to {money(data.range_high)}</span>, where the methods land
              {change !== null && <>. Default <span className="num text-soft">{money(base.fair_value)}</span> ({pct(change, { sign: true })})</>}
            </p>
          </div>
          <Button onClick={() => setOpen(!open)} aria-expanded={open}>{open ? "Hide what-if" : "What if…"}</Button>
        </div>
        <p className="mt-3 max-w-[80ch] text-small text-muted">
          The middle of {data.methods_used.length === 2 ? "two methods" : "one method"} built from reported numbers:
          {data.methods_used.includes("dcf") && <> a <b className="font-medium text-soft">cash-flow DCF</b> (free cash flow growing at the company's revenue record, fading to long-run growth)</>}
          {data.methods_used.length === 2 && " and "}
          {data.methods_used.includes("epv") && <> <b className="font-medium text-soft">earnings power</b> (today's normalised operating profit with no growth at all)</>}
          , both discounted at a {pct(coc.cost_of_capital, { digits: 2 })} cost of capital ({data.industry} industry data).
        </p>

        <MethodsScale data={data} />

        <PriceBlock key={typed ?? "quote"} data={data} jobId={jobId} typed={typed} pending={recompute.isPending}
          error={recompute.isError && !open ? recompute.error : null}
          onPrice={(price) => run(overrides, price)} />

        {open && (
          <div className="mt-4">
            <WhatIfPanel data={base} active={Object.keys(overrides).length > 0} pending={recompute.isPending}
              error={recompute.isError ? recompute.error : null}
              onReset={() => run({}, typed)} submit={(body) => run(body, typed)} />
          </div>
        )}
      </div>

      <dl className="grid grid-cols-2 border-t border-rule lg:grid-cols-4 lg:divide-x lg:divide-rule">
        <Driver label="Cost of capital" value={pct(coc.cost_of_capital, { digits: 2 })} note={`equity ${pct(coc.cost_of_equity, { digits: 2 })}, beta ${Number(coc.levered_beta).toFixed(2)}`} />
        <Driver label="Growth, first years" value={pct(value("initial_growth"), { digits: 1 })}
          note={`${toNumber(value("high_growth_years"))} years, then ${toNumber(value("fade_years"))} fading`} />
        <Driver label="Long-run growth" value={pct(value("stable_growth"), { digits: 1 })} note="forever after" />
        <Driver label="Terminal value" value={dcf ? pct(dcf.terminal_share, { digits: 0 }) : "—"} note="of the DCF value" />
      </dl>

      <div className="grid grid-cols-1 gap-6 border-t border-rule px-6 py-5 lg:grid-cols-2">
        <div className="min-w-0">
          <h3 className="mb-1 font-semibold">Cash-flow DCF</h3>
          {dcf ? (
            <Lines rows={[
              ["Present value of 10 years' cash flow", usd(dcf.present_value_of_fcf), ""],
              ["Present value of the terminal value", usd(dcf.terminal_present_value), ""],
              ["Enterprise value", usd(dcf.enterprise_value), "total"],
              ...bridge(dcf.enterprise_value),
              ["Value per share", money(dcf.value_per_share), "total"],
            ]} />
          ) : <p className="text-small text-soft">Not used: reported free cash flow isn't positive.</p>}
        </div>
        <div className="min-w-0">
          <h3 className="mb-1 font-semibold">Earnings power (no growth)</h3>
          {epv ? (
            <Lines rows={[
              ["Normalised operating income", usd(value("normalised_operating_income")), ""],
              [`After tax (${pct(value("tax_rate"), { digits: 1 })})`, usd(epv.normalised_after_tax_operating_income), ""],
              [`÷ Cost of capital (${pct(coc.cost_of_capital, { digits: 2 })})`, "", ""],
              ["Enterprise value", usd(epv.enterprise_value), "total"],
              ...bridge(epv.enterprise_value),
              ["Value per share", money(epv.value_per_share), "total"],
            ]} />
          ) : <p className="text-small text-soft">Not used: normalised operating income isn't positive.</p>}
        </div>
      </div>

      {data.fcf_history.length > 0 && (
        <div className="border-t border-rule px-6 py-5">
          <h3 className="mb-2 font-semibold">Reported free cash flow</h3>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-small">
              <thead>
                <tr className="text-muted">
                  <Th left>Year</Th><Th>Cash from operations</Th><Th>+ After-tax interest</Th><Th>− Capex</Th>
                  <Th>− Stock compensation</Th><Th>= Free cash flow</Th><Th>Margin</Th>
                </tr>
              </thead>
              <tbody>
                {data.fcf_history.map((h) => (
                  <tr key={h.fiscal_year} className="border-t border-rule">
                    <th scope="row" className="num py-1.5 text-left font-normal">FY{h.fiscal_year}</th>
                    <td className="num py-1.5 text-right">{usd(h.operating_cash_flow)}</td>
                    <td className="num py-1.5 text-right">{usd(h.after_tax_interest)}</td>
                    <td className="num py-1.5 text-right">{usd(h.capital_expenditure)}</td>
                    <td className="num py-1.5 text-right">{usd(h.share_based_compensation)}</td>
                    <td className="num py-1.5 text-right font-medium">{usd(h.fcf)}</td>
                    <td className="num py-1.5 text-right">{pct(h.fcf_margin, { digits: 1 })}</td>
                  </tr>
                ))}
                <tr className="border-t border-rule font-semibold">
                  <th scope="row" className="py-1.5 text-left" colSpan={5}>Starting point</th>
                  <td className="num py-1.5 text-right">{usd(value("base_fcf"))}</td>
                  <td />
                </tr>
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-small text-muted">{assumption(data, "base_fcf")?.source}</p>
        </div>
      )}

      {dcf && (
        <div className="border-t border-rule px-6 py-5">
          <h3 className="mb-2 font-semibold">Projected free cash flow</h3>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-small">
              <thead>
                <tr className="text-muted"><Th left>Year</Th><Th>Growth</Th><Th>Free cash flow</Th><Th>Discount factor</Th><Th>Present value</Th></tr>
              </thead>
              <tbody>
                {dcf.projection.map((row) => (
                  <tr key={row.year} className="border-t border-rule">
                    <th scope="row" className="num py-1.5 text-left font-normal">FY{row.fiscal_year}</th>
                    <td className="num py-1.5 text-right">{pct(row.growth, { digits: 1 })}</td>
                    <td className="num py-1.5 text-right">{usd(row.fcf)}</td>
                    <td className="num py-1.5 text-right">{Number(row.discount_factor).toFixed(3)}</td>
                    <td className="num py-1.5 text-right">{usd(row.present_value)}</td>
                  </tr>
                ))}
                <tr className="border-t border-rule font-semibold">
                  <th scope="row" className="py-1.5 text-left">Terminal</th>
                  <td className="num py-1.5 text-right">{pct(value("stable_growth"), { digits: 1 })}</td>
                  <td className="num py-1.5 text-right">{usd(dcf.terminal_value)}</td>
                  <td />
                  <td className="num py-1.5 text-right">{usd(dcf.terminal_present_value)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}

      {data.sensitivity && dcf && <div className="border-t border-rule px-6 py-5"><Sensitivity data={data} /></div>}

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
          <h3 className="mb-1 font-semibold">Cost of capital</h3>
          <Lines rows={[
            ["Risk-free rate", pct(value("risk_free_rate"), { digits: 2 }), ""],
            ["+ Beta × equity risk premium", `${Number(coc.levered_beta).toFixed(2)} × ${pct(value("equity_risk_premium"), { digits: 2 })}`, ""],
            ["Cost of equity", pct(coc.cost_of_equity, { digits: 2 }), "total"],
            ["Cost of debt, after tax", pct(coc.after_tax_cost_of_debt, { digits: 2 }), ""],
            ["Debt weight", pct(value("debt_to_capital"), { digits: 1 }), ""],
            ["Cost of capital", pct(coc.cost_of_capital, { digits: 2 }), "total"],
          ]} />
        </div>
      </div>

      {data.warnings.length > 0 && (
        <div className="border-t border-rule px-6 py-4">
          <h3 className="mb-1 text-small font-medium text-muted">Notes on this valuation</h3>
          <ul className="list-disc space-y-1 pl-5 text-small text-soft marker:text-muted">
            {data.warnings.map((w) => <li key={w}>{w}</li>)}
          </ul>
        </div>
      )}
      <p className="px-6 pb-5 text-small text-muted">
        Method: fair-value blend (cash-flow DCF and earnings power value, with a reverse DCF against the price). Calculation version <span className="num">{data.calculation_version}</span>.
      </p>
    </Panel>
  );
}
