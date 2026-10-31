import { type ReactNode, useState } from "react";
import { Link } from "react-router-dom";

import { type CostSummary, useCosts } from "../api/client";
import { Bar, Empty, ErrorBlock, PageTitle, Panel, StatusPill } from "../components/ui";
import { STAGES, date, money, toNumber, tokens } from "../lib/format";
import { useTitle } from "../lib/useTitle";

const STAGE_LABEL: Record<string, string> = {
  ...Object.fromEntries(STAGES.map((s) => [s.key, s.label])),
  analyzing: "Analyze (linear pipeline)",
  critic: "Critic",
  restore: "Restore draft",
  chat: "Ask the analyst",
};

const WINDOWS = [7, 30, 90] as const;

function Meter({ spent, cap }: { spent: number; cap: number }) {
  const share = cap > 0 ? Math.min(1, spent / cap) : 0;
  const tone = share >= 1 ? "bg-negative" : share >= 0.8 ? "bg-warning" : "bg-accent";
  return (
    <div className="mt-2 h-1.5 w-full rounded-[1px] bg-raised" role="meter" aria-valuemin={0} aria-valuemax={cap} aria-valuenow={spent}
      aria-label={`${money(spent)} of ${money(cap)} spent`}>
      <div className={`h-full rounded-[1px] ${tone}`} style={{ width: `${Math.max(share * 100, spent > 0 ? 2 : 0)}%` }} />
    </div>
  );
}

/** Daily spend at list price; today carries the accent. Hand-rolled like the other charts (no chart library). */
function DailySpend({ days }: { days: CostSummary["days"] }) {
  const [active, setActive] = useState<number | null>(null);
  const values = days.map((d) => toNumber(d.list_price) ?? 0);
  const max = Math.max(...values, 0);
  if (max === 0) return <p className="px-6 pb-6 text-muted">No model calls in this period.</p>;
  const top = niceMax(max);
  const W = 100 / days.length;
  const shown = active ?? days.length - 1;
  const total = values.reduce((a, b) => a + b, 0);
  return (
    <figure className="px-6 pb-6">
      <figcaption className="mb-3 flex flex-wrap items-baseline justify-between gap-2 text-small text-muted">
        <span>
          <span className="num text-ink">{date(days[shown]!.date)}</span>: <span className="num text-ink">{money(values[shown])}</span>
          {" "}across <span className="num">{days[shown]!.calls}</span> calls
        </span>
        <span>Scale to <span className="num">{money(top)}</span> a day</span>
      </figcaption>
      <div className="relative h-40 border-b border-rule" role="img"
        aria-label={`Daily model spend at list price over ${days.length} days, ${money(total)} in total, highest ${money(max)} in a day.`}>
        {[0.5, 1].map((f) => (
          <div key={f} className="absolute inset-x-0 border-t border-dashed border-rule" style={{ bottom: `${f * 100}%` }} aria-hidden="true" />
        ))}
        <div className="absolute inset-0 flex items-end" onMouseLeave={() => setActive(null)}>
          {days.map((d, i) => (
            <button key={d.date} type="button" className="group flex h-full items-end justify-center focus:outline-none" style={{ width: `${W}%` }}
              onMouseEnter={() => setActive(i)} onFocus={() => setActive(i)} onBlur={() => setActive(null)}
              aria-label={`${date(d.date)}: ${money(values[i])}, ${d.calls} calls`}>
              <span className={`block w-[60%] max-w-6 rounded-t-[1px] ${i === days.length - 1 ? "bg-accent" : "bg-control"} ${shown === i ? "opacity-100" : "opacity-70"} group-focus-visible:outline group-focus-visible:outline-1`}
                style={{ height: `${(values[i]! / top) * 100}%`, minHeight: values[i]! > 0 ? 2 : 0 }} />
            </button>
          ))}
        </div>
      </div>
      <div className="mt-1.5 flex justify-between text-small text-muted num" aria-hidden="true">
        <span>{date(days[0]!.date, { month: "short", day: "numeric" })}</span>
        <span>{date(days[days.length - 1]!.date, { month: "short", day: "numeric" })}</span>
      </div>
    </figure>
  );
}

function niceMax(value: number): number {
  const exp = 10 ** Math.floor(Math.log10(value));
  for (const step of [1, 2, 2.5, 5, 10]) if (step * exp >= value) return step * exp;
  return 10 * exp;
}

function Th({ children, right = false }: { children: ReactNode; right?: boolean }) {
  return <th scope="col" className={`px-2.5 py-2 text-small font-normal text-muted first:pl-6 last:pr-6 ${right ? "text-right" : "text-left"}`}>{children}</th>;
}

function Td({ children, right = false, mono = false }: { children: ReactNode; right?: boolean; mono?: boolean }) {
  return <td className={`px-2.5 py-2.5 whitespace-nowrap first:pl-6 last:pr-6 ${right ? "text-right" : ""} ${mono ? "num" : ""}`}>{children}</td>;
}

export function Costs() {
  useTitle("Costs");
  const [days, setDays] = useState<(typeof WINDOWS)[number]>(30);
  const costs = useCosts(days);
  const data = costs.data;
  const free = data?.budget.billing === "free";

  return (
    <>
      <PageTitle
        title="Costs"
        sub={free
          ? "Every Gemini call, priced from its own token counts. This project is on the free tier, so nothing is billed yet; amounts show what the same usage costs on the paid tier."
          : "Every Gemini call, priced from its own token counts at Google's published rates, against the spending caps."}
        actions={
          <div role="group" aria-label="Period" className="flex gap-4">
            {WINDOWS.map((w) => (
              <button key={w} type="button" onClick={() => setDays(w)} aria-pressed={days === w}
                className={`press pb-1 text-body ${days === w ? "border-b border-accent text-ink" : "border-b border-transparent text-muted hover:text-ink"}`}>
                {w} days
              </button>
            ))}
          </div>
        }
      />

      {costs.isError ? <Panel><div className="pt-6"><ErrorBlock error={costs.error} onRetry={() => costs.refetch()} /></div></Panel>
        : !data ? (
          <div aria-busy="true" aria-label="Loading costs" className="grid gap-6">
            <div className="panel h-[112px] p-6"><Bar w="40%" h={20} /></div>
            <div className="panel h-[260px] p-6"><Bar w="100%" h={160} /></div>
          </div>
        ) : (
          <div className="grid min-w-0 gap-6 [&>*]:min-w-0">
            {data.budget.blocked_reason && (
              <div role="alert" className="rounded-[6px] bg-[var(--pill-negative-bg)] px-4 py-3 text-[var(--pill-negative-ink)]">
                {data.budget.blocked_reason} New research and chat questions are paused until then.
              </div>
            )}

            <dl className="panel grid grid-cols-1 gap-y-4 py-4 sm:grid-cols-2 lg:grid-cols-4 lg:divide-x lg:divide-rule lg:py-0">
              <div className="px-6 lg:py-4">
                <dt className="text-small text-muted">Billed today</dt>
                <dd className="num mt-1 text-card">{money(data.budget.today)}<span className="text-muted"> of {money(data.budget.daily_cap)}</span></dd>
                <dd><Meter spent={toNumber(data.budget.today) ?? 0} cap={toNumber(data.budget.daily_cap) ?? 0} /></dd>
                <dd className="mt-1.5 text-small text-muted">Resets <span className="num">{date(data.budget.day_resets_at, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span></dd>
              </div>
              <div className="px-6 lg:py-4">
                <dt className="text-small text-muted">Billed this month</dt>
                <dd className="num mt-1 text-card">{money(data.budget.month)}<span className="text-muted"> of {money(data.budget.monthly_cap)}</span></dd>
                <dd><Meter spent={toNumber(data.budget.month) ?? 0} cap={toNumber(data.budget.monthly_cap) ?? 0} /></dd>
                <dd className="mt-1.5 text-small text-muted">Resets <span className="num">{date(data.budget.month_resets_at)}</span></dd>
              </div>
              <div className="px-6 lg:py-4">
                <dt className="text-small text-muted">Usage, last {days} days</dt>
                <dd className="num mt-1 text-card">{money(data.window.list_price)}</dd>
                <dd className="text-small text-muted">
                  <span className="num">{data.window.calls.toLocaleString()}</span> calls, <span className="num">{tokens(data.window.input_tokens + data.window.output_tokens)}</span> tokens
                </dd>
                <dd className="text-small text-muted">{free ? "at paid-tier prices; billed $0.00" : <>billed <span className="num">{money(data.window.billed)}</span></>}</dd>
              </div>
              <div className="px-6 lg:py-4">
                <dt className="text-small text-muted">Per research job</dt>
                <dd className="num mt-1 text-card">{money(data.per_job_average)}</dd>
                <dd className="text-small text-muted">average list price of completed jobs</dd>
              </div>
            </dl>

            {data.all_time.calls === 0 ? (
              <Panel><div className="pt-6"><Empty>No model calls yet. Costs appear here as soon as research or a chat question runs.</Empty></div></Panel>
            ) : (
              <>
                <Panel id="daily" title="Daily spend" aside={<span>List price, UTC days</span>}>
                  <DailySpend days={data.days} />
                </Panel>

                <div className="grid grid-cols-1 items-start gap-6 xl:grid-cols-2 [&>*]:min-w-0">
                  <Panel id="models" title="By model" aside={<span>Last {days} days</span>}>
                    <div className="overflow-x-auto pb-3">
                      <table className="w-full min-w-[520px]">
                        <thead><tr className="border-b border-rule"><Th>Model</Th><Th right>Calls</Th><Th right>Input</Th><Th right>Cached</Th><Th right>Output</Th><Th right>Cost</Th></tr></thead>
                        <tbody className="divide-y divide-rule">
                          {data.models.map((m) => (
                            <tr key={`${m.model}-${m.operation}`}>
                              <Td><span className="num">{m.model}</span>{m.operation === "embed" && <span className="block text-small text-muted">embeddings</span>}</Td>
                              <Td right mono>{m.calls.toLocaleString()}</Td>
                              <Td right mono>{tokens(m.input_tokens)}</Td>
                              <Td right mono>{tokens(m.cached_tokens)}</Td>
                              <Td right mono>{tokens(m.output_tokens)}</Td>
                              <Td right mono>{m.priced ? money(m.list_price) : <span className="text-muted" title="Not on the price list">not priced</span>}</Td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Panel>

                  <Panel id="stages" title="By stage" aside={<span>Where the money goes</span>}>
                    <div className="overflow-x-auto pb-3">
                      <table className="w-full min-w-[420px]">
                        <thead><tr className="border-b border-rule"><Th>Stage</Th><Th right>Calls</Th><Th right>Tokens</Th><Th right>Cost</Th><Th right>Share</Th></tr></thead>
                        <tbody className="divide-y divide-rule">
                          {data.stages.map((s) => {
                            const share = (toNumber(s.list_price) ?? 0) / Math.max(toNumber(data.window.list_price) ?? 0, 1e-12);
                            return (
                              <tr key={`${s.source}-${s.stage}`}>
                                <Td>{STAGE_LABEL[s.stage ?? ""] ?? s.stage ?? "Other"}</Td>
                                <Td right mono>{s.calls.toLocaleString()}</Td>
                                <Td right mono>{tokens(s.input_tokens + s.output_tokens)}</Td>
                                <Td right mono>{money(s.list_price)}</Td>
                                <Td right mono>{`${Math.round(share * 100)}%`}</Td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </Panel>
                </div>

                <Panel id="jobs" title="Research jobs" aside={<span>Most recent 25, research and chat combined</span>}>
                  <div className="overflow-x-auto pb-3">
                    <table className="w-full min-w-[640px]">
                      <thead><tr className="border-b border-rule"><Th>Company</Th><Th>Submitted</Th><Th>Status</Th><Th right>Calls</Th><Th right>Tokens</Th><Th right>Cost</Th></tr></thead>
                      <tbody className="divide-y divide-rule">
                        {data.jobs.map((j) => (
                          <tr key={j.job_id} className="hover:bg-raised">
                            <Td><Link to={`/research/${j.job_id}`} className="hover:underline">{j.company} <span className="num text-muted">{j.ticker}</span></Link></Td>
                            <Td mono>{date(j.created_at)}</Td>
                            <Td><StatusPill status={j.status as Parameters<typeof StatusPill>[0]["status"]} /></Td>
                            <Td right mono>{j.calls.toLocaleString()}</Td>
                            <Td right mono>{tokens(j.input_tokens + j.output_tokens)}</Td>
                            <Td right mono>{money(j.list_price)}</Td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Panel>
              </>
            )}

            <section aria-label="How costs are calculated" className="max-w-[90ch] space-y-1.5 text-small text-muted">
              <p>
                Each row is one model response. Cost = uncached input × input price + cached input × cached price + output
                (including thinking) × output price, at the rate in force that day (
                <a href={data.pricing_source} target="_blank" rel="noreferrer" className="underline-offset-4 hover:underline">Google's price list</a>,
                checked <span className="num">{date(data.pricing_checked)}</span>). Embedding tokens are counted with Gemini's countTokens endpoint.
                Rejected requests (429, 5xx) aren't billed and aren't counted.
              </p>
              {(data.estimated_calls > 0 || data.unpriced_calls > 0) && (
                <p>
                  {data.estimated_calls > 0 && <><span className="num">{data.estimated_calls}</span> rows are estimates rebuilt from per-stage totals of runs before the ledger existed. </>}
                  {data.unpriced_calls > 0 && <><span className="num">{data.unpriced_calls}</span> rows used models that aren't on the price list and add $0. </>}
                </p>
              )}
            </section>
          </div>
        )}
    </>
  );
}
