import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { ApiError, type Claim, type Report, useJob, useReport } from "../api/client";
import { BarChart, LedgerBar, LineChart } from "../components/charts";
import { DownloadIcon, ExternalIcon, PrintIcon } from "../components/icons";
import { type InspectTarget, Inspector } from "../components/Inspector";
import { SectionIndex } from "../components/SectionIndex";
import { Bar, Button, ButtonLink, Empty, ErrorBlock, Panel, Pill, VerificationPill } from "../components/ui";
import { download, reportToMarkdown } from "../lib/exportMarkdown";
import { useTitle } from "../lib/useTitle";
import { useToast } from "../components/Toast";
import { CLAIM_TYPE_LABEL, FIELD_LABEL, SECTION_LABEL, VERIFICATION_LABEL, changeText, date, fieldValue, metricDisplay, metricValue, toNumber, usd, usdTick } from "../lib/format";

const KEY_METRICS = [
  "revenue_growth", "gross_margin", "operating_margin", "net_margin", "free_cash_flow", "fcf_margin",
  "return_on_equity", "rd_intensity", "current_ratio", "debt_to_equity", "net_debt", "interest_coverage",
];
const STATEMENT_ROWS = [
  "revenue", "gross_profit", "operating_income", "net_income", "eps", "operating_cash_flow", "capital_expenditure",
  "cash", "debt", "total_assets", "stockholders_equity",
];
const STATUS_COLOR: Record<string, string> = {
  supported: "var(--positive)", partially_supported: "var(--warning)", unsupported: "var(--negative)", not_verified: "var(--control)",
};
const SECTIONS = [
  { id: "answer", label: "Answer" },
  { id: "summary", label: "Summary" },
  { id: "financials", label: "Financials" },
  { id: "scenarios", label: "Scenarios" },
  { id: "risks", label: "Risks" },
  { id: "ledger", label: "Evidence" },
  { id: "limitations", label: "Limitations" },
];
const SEVERITY_TONE = { high: "negative", medium: "warning", low: "neutral" } as const;

function Cite({ ids, numbers, onOpen }: { ids: string[]; numbers: Map<string, number>; onOpen: (id: string) => void }) {
  return (
    <>
      {ids.map((id) => numbers.get(id) && (
        <button key={id} type="button" onClick={() => onOpen(id)} aria-label={`Open claim ${numbers.get(id)}`}
          className="press num ml-1 inline-flex h-5 min-w-5 items-center justify-center rounded-[3px] bg-raised px-1 align-[1px] text-small text-soft hover:text-ink">
          {numbers.get(id)}
        </button>
      ))}
    </>
  );
}

function ReportSkeleton() {
  return (
    <div aria-busy="true" aria-label="Loading report" className="grid gap-6">
      <Bar w="50%" h={28} />
      <Bar w="80%" h={16} />
      <div className="panel h-48" />
      <div className="panel h-72" />
    </div>
  );
}

export function ReportPage() {
  const { jobId = "" } = useParams();
  const report = useReport(jobId);
  const missing = report.error instanceof ApiError && report.error.status === 404;
  const job = useJob(jobId);

  if (report.isPending) return <ReportSkeleton />;
  if (report.isError) {
    return (
      <>
        <h1 className="mb-2 text-title font-semibold">{missing ? "Report not ready" : "Report"}</h1>
        <Panel>
          <div className="px-6 py-6">
            {missing ? (
              <div className="flex flex-wrap items-center justify-between gap-4 text-soft">
                <span>{job.data ? `This job is ${job.data.status}. The report appears when all eight stages finish.` : "There is no report for this job."}</span>
                <ButtonLink to={`/research/${jobId}`}>View job progress</ButtonLink>
              </div>
            ) : <ErrorBlock error={report.error} onRetry={() => report.refetch()} />}
          </div>
        </Panel>
      </>
    );
  }
  return <ReportView report={report.data} />;
}

function ReportView({ report }: { report: Report }) {
  const toast = useToast();
  useTitle(`${report.company.ticker} report`);
  // Filters and the open claim live in the URL, so a filtered ledger or a claim can be linked and survives reload.
  const [params, setParams] = useSearchParams();
  const statusFilter = params.get("status");
  const typeFilter = params.get("type");
  const setParam = (key: string, value: string | null) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  };
  const setStatusFilter = (value: string | null) => setParam("status", value);
  const setTypeFilter = (value: string | null) => setParam("type", value);
  const [target, setTargetState] = useState<InspectTarget | null>(null);
  const setTarget = (next: InspectTarget | null) => {
    setTargetState(next);
    setParam("claim", next?.kind === "claim" ? String(next.number) : null);
  };

  const numbers = useMemo(() => new Map(report.claims.map((c, i) => [c.id, i + 1])), [report.claims]);
  const claimsById = useMemo(() => new Map(report.claims.map((c) => [c.id, c])), [report.claims]);
  const openClaim = (id: string) => {
    const claim = claimsById.get(id);
    if (claim) setTarget({ kind: "claim", claim, number: numbers.get(id)! });
  };
  useEffect(() => {
    const n = Number(params.get("claim"));
    const claim = n ? report.claims[n - 1] : undefined;
    if (claim && !target) setTargetState({ kind: "claim", claim, number: n });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [report.claims]);
  const summary = report.verification_summary;
  const latest = report.financials[report.financials.length - 1];
  const primaryFiling = report.filings.find((f) => f.form === "10-K") ?? report.filings[0];
  const metricRows = KEY_METRICS.map((key) => ({ key, cells: report.metrics.filter((m) => m.key === key) })).filter((r) => r.cells.length);
  const periods = report.financials.map((f) => f.period);
  const cagr = report.metrics.find((m) => m.key === "revenue_cagr");

  const visibleClaims = report.claims.filter(
    (c) => (!statusFilter || c.verification_status === statusFilter) && (!typeFilter || c.claim_type === typeFilter),
  );
  const sections = [...new Set(visibleClaims.map((c) => c.section))];

  return (
    <>
      <nav aria-label="Breadcrumb" className="no-print mb-3 text-small text-muted">
        <Link to="/reports" className="hover:text-ink">Reports</Link> <span aria-hidden="true">/</span> <span className="num">{report.company.ticker}</span>
      </nav>

      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 max-w-[880px]">
          <h1 className="text-[22px] leading-[28px] font-semibold md:text-title">
            {report.job.company} <span className="font-normal text-muted">{report.company.ticker}</span>
          </h1>
          <p className="mt-1 text-read text-soft">{report.headline}</p>
        </div>
        <div className="no-print flex gap-3">
          <Button onClick={() => {
            download(`${report.company.ticker}-research-${report.data_as_of ?? "report"}.md`, reportToMarkdown(report));
            toast("Markdown report downloaded");
          }}>
            <DownloadIcon /> Markdown
          </Button>
          <Button onClick={() => window.print()}><PrintIcon /> Print or PDF</Button>
        </div>
      </header>

      {/* Freshness, sources and trust: always visible, never in a tooltip. */}
      <dl className="panel mb-6 grid grid-cols-2 divide-rule gap-y-4 py-4 lg:grid-cols-4 lg:divide-x lg:py-0">
        <div className="px-6 lg:py-4">
          <dt className="text-small text-muted">Data as of</dt>
          <dd className="num mt-1 text-card">{date(report.data_as_of)}</dd>
          <dd className="text-small text-muted">{latest?.period ?? "—"} fiscal year end</dd>
        </div>
        <div className="px-6 lg:py-4">
          <dt className="text-small text-muted">Primary source</dt>
          <dd className="mt-1 text-card">
            {primaryFiling ? <a href={primaryFiling.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1.5 hover:underline">{primaryFiling.form} <ExternalIcon /></a> : "—"}
          </dd>
          <dd className="text-small text-muted">filed <span className="num">{date(primaryFiling?.filed)}</span></dd>
        </div>
        <div className="px-6 lg:py-4">
          <dt className="text-small text-muted">Claims supported</dt>
          <dd className="num mt-1 text-card">{summary.supported}<span className="text-muted"> of {summary.total}</span></dd>
          <dd className="text-small text-muted">
            <span className="num">{summary.partially_supported}</span> partly supported, <span className="num">{summary.unsupported}</span> unsupported
          </dd>
        </div>
        <div className="px-6 lg:py-4">
          <dt className="text-small text-muted">Generated</dt>
          <dd className="num mt-1 text-card">{date(report.generated_at)}</dd>
          <dd className="truncate text-small text-muted">{report.models_used?.strong ? String(report.models_used.strong) : "—"}</dd>
        </div>
      </dl>


      <SectionIndex sections={SECTIONS.filter((section) => section.id !== "scenarios" || report.scenarios.length > 0)} />

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="grid min-w-0 grid-cols-1 gap-6">
          <Panel id="answer" title="Answer">
            <div className="px-6 pb-6">
              <p className="text-small text-muted">You asked: “{report.job.query}”</p>
              <p className="mt-3 max-w-[75ch] text-[17px] leading-[28px]">{report.direct_answer}</p>
              <h3 className="mt-6 mb-2 font-semibold">Key points</h3>
              <ul className="max-w-[80ch] divide-y divide-rule">
                {report.key_points.map((point, i) => (
                  <li key={i} className="py-2.5 text-read">
                    {point.text}<Cite ids={point.claim_ids} numbers={numbers} onOpen={openClaim} />
                  </li>
                ))}
              </ul>
            </div>
          </Panel>

          <Panel id="summary" title="Executive summary">
            <div className="grid gap-6 px-6 pb-6 xl:grid-cols-2">
              <p className="max-w-[75ch] text-read">{report.executive_summary}</p>
              {report.investment_thesis && (
                <div>
                  <h3 className="mb-1 font-semibold">Investment thesis</h3>
                  <p className="max-w-[75ch] text-read text-soft">{report.investment_thesis}</p>
                  <p className="mt-2 text-small text-muted">An interpretation of the verified claims, not a recommendation.</p>
                </div>
              )}
            </div>
          </Panel>

          <Panel id="financials" title="Financials" aside={<span>US dollars, fiscal years, from SEC XBRL</span>}>
            <div className="grid grid-cols-1 gap-6 px-6 pb-2 xl:grid-cols-2">
              <figure>
                <figcaption className="mb-2 flex justify-between text-small text-muted">
                  <span>Revenue</span>
                  {cagr && <button type="button" className="press hover:text-ink" onClick={() => setTarget({ kind: "metric", metric: cagr })}>
                    {cagr.label}: <span className="num text-ink">{metricValue(cagr.value, cagr.unit)}</span>
                  </button>}
                </figcaption>
                <BarChart title="Revenue by fiscal year" format={(v) => usd(v)} tickFormat={usdTick} changeFormat={(a, b) => changeText(a, b, "pct")}
                  points={report.financials.map((f) => ({ label: f.period, value: toNumber(f.values.revenue?.value) }))} />
              </figure>
              <figure>
                <figcaption className="mb-2 text-small text-muted">Operating margin</figcaption>
                <LineChart title="Operating margin by fiscal year" format={(v) => `${(v * 100).toFixed(1)}%`} tickFormat={(v) => `${Math.round(v * 100)}%`} changeFormat={(a, b) => changeText(a, b, "pp")}
                  points={periods.map((p) => ({ label: p, value: toNumber(report.metrics.find((m) => m.key === "operating_margin" && m.period === p)?.value) }))} />
              </figure>
            </div>

            <div className="overflow-x-auto px-6 pb-2">
              <table className="w-full min-w-[640px] text-body">
                <caption className="py-3 text-left text-small text-muted">Reported figures. Select a figure to see its XBRL concept and filing.</caption>
                <thead>
                  <tr className="text-small text-muted">
                    <th scope="col" className="w-[34%] py-2 text-left font-normal">Line item</th>
                    {periods.map((p) => <th key={p} scope="col" className="num py-2 text-right font-normal">{p}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {STATEMENT_ROWS.map((field) => (
                    <tr key={field} className="border-t border-rule">
                      <th scope="row" className="py-2 text-left font-normal text-soft">{FIELD_LABEL[field]}</th>
                      {report.financials.map((f) => {
                        const cell = f.values[field];
                        return (
                          <td key={f.period} className="py-1 text-right">
                            <button type="button"
                              onClick={() => setTarget({ kind: "fact", field, period: f.period, value: cell?.value ?? null, provenance: (cell?.provenance as Record<string, unknown>) ?? null })}
                              className={`press num rounded-[3px] px-1.5 py-1 hover:bg-raised ${cell?.value == null ? "text-muted" : f === latest ? "text-ink" : "text-soft"}`}>
                              {fieldValue(field, cell?.value ?? null)}
                            </button>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="overflow-x-auto px-6 pb-6">
              <table className="w-full min-w-[640px] text-body">
                <caption className="py-3 text-left text-small text-muted">Calculated metrics. Select a value to see its formula and inputs.</caption>
                <thead>
                  <tr className="text-small text-muted">
                    <th scope="col" className="w-[34%] py-2 text-left font-normal">Metric</th>
                    {periods.map((p) => <th key={p} scope="col" className="num py-2 text-right font-normal">{p}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {metricRows.map((row) => (
                    <tr key={row.key} className="border-t border-rule">
                      <th scope="row" className="py-2 text-left font-normal text-soft">{row.cells[0]!.label}</th>
                      {periods.map((p) => {
                        const metric = row.cells.find((m) => m.period === p);
                        return (
                          <td key={p} className="py-1 text-right">
                            {metric ? (
                              <button type="button" onClick={() => setTarget({ kind: "metric", metric })}
                                className={`press num rounded-[3px] px-1.5 py-1 hover:bg-raised ${p === latest?.period ? "text-ink" : "text-soft"}`}>
                                {metricDisplay(row.key, metric.value, metric.unit, { sign: row.key.endsWith("growth") })}
                              </button>
                            ) : <span className="num px-1.5 text-muted" title="Inputs not reported for this year">—</span>}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          {report.scenarios.length > 0 && (
            <Panel id="scenarios" title="Scenarios" aside={<span>Assumptions anchored to the data</span>}>
              <div className="grid gap-px bg-rule md:grid-cols-3">
                {report.scenarios.map((s) => (
                  <section key={s.name} className="bg-surface px-6 pt-1 pb-6" aria-label={`${s.name} case`}>
                    <h3 className="font-semibold capitalize">{s.name} case</h3>
                    <p className="mt-1 text-soft">{s.summary}</p>
                    <dl className="mt-3 grid gap-3">
                      {s.assumptions.map((a, i) => (
                        <div key={i}>
                          <dt className="text-small text-muted">{a.driver}</dt>
                          <dd>{a.assumption}</dd>
                          {(a.basis || (a.claim_ids?.length ?? 0) > 0) && (
                            <dd className="text-small text-muted">
                              Basis: {a.basis.replace(/\bclaim \d+(,\s*)?/g, "").replace(/[,\s]+$/, "") || "claims"}
                              <Cite ids={a.claim_ids ?? []} numbers={numbers} onOpen={openClaim} />
                            </dd>
                          )}
                        </div>
                      ))}
                    </dl>
                  </section>
                ))}
              </div>
              <p className="px-6 py-4 text-small text-muted">No price targets: market price data is out of scope, so scenarios describe operating outcomes, not valuation.</p>
            </Panel>
          )}

          <Panel id="risks" title="Risks">
            <ul className="divide-y divide-rule pb-2">
              {report.risks.map((risk, i) => (
                <li key={i} className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 px-6 py-3">
                  <span className="font-medium">{risk.title}<Cite ids={risk.claim_ids} numbers={numbers} onOpen={openClaim} /></span>
                  <Pill tone={SEVERITY_TONE[risk.severity as keyof typeof SEVERITY_TONE] ?? "neutral"}>{risk.severity}</Pill>
                  <span className="col-span-2 max-w-[80ch] text-soft">{risk.description}</span>
                </li>
              ))}
            </ul>
          </Panel>

          <Panel id="ledger" title="Evidence ledger" aside={<span className="num">{visibleClaims.length} of {report.claims.length} claims</span>}>
            <div className="no-print flex flex-wrap gap-x-6 gap-y-2 border-b border-rule px-6">
              <div role="group" aria-label="Filter by verification" className="-mb-px flex gap-4 overflow-x-auto">
                {[null, "supported", "partially_supported", "unsupported"].map((s) => (
                  <button key={s ?? "all"} type="button" aria-pressed={statusFilter === s} onClick={() => setStatusFilter(s)}
                    className={`sel-line press h-9 whitespace-nowrap ${statusFilter === s ? "text-ink" : "text-muted hover:text-soft"}`}>
                    {s ? VERIFICATION_LABEL[s] : "All"}
                  </button>
                ))}
              </div>
              <div role="group" aria-label="Filter by claim type" className="-mb-px flex gap-4 overflow-x-auto">
                {["fact", "calculation", "interpretation"].map((t) => (
                  <button key={t} type="button" aria-pressed={typeFilter === t} onClick={() => setTypeFilter(typeFilter === t ? null : t)}
                    className={`sel-line press h-9 whitespace-nowrap ${typeFilter === t ? "text-ink" : "text-muted hover:text-soft"}`}>
                    {CLAIM_TYPE_LABEL[t]}
                  </button>
                ))}
              </div>
            </div>
            {sections.length === 0 && <div className="pt-4"><Empty>No claims match these filters.</Empty></div>}
            {sections.map((section) => (
              <section key={section} aria-label={SECTION_LABEL[section] ?? section}>
                <h3 className="px-6 pt-4 pb-1 text-small text-muted">{SECTION_LABEL[section] ?? section}</h3>
                <ul>
                  {visibleClaims.filter((c) => c.section === section).map((claim) => (
                    <ClaimRow key={claim.id} claim={claim} number={numbers.get(claim.id)!} onOpen={() => openClaim(claim.id)} />
                  ))}
                </ul>
              </section>
            ))}
            <div className="h-3" />
          </Panel>
        </div>

        <aside className="grid gap-6 lg:sticky lg:top-16" aria-label="Report trust">
          <Panel id="verification" title="Verification">
            <div className="px-6 pb-5">
              <LedgerBar parts={(["supported", "partially_supported", "unsupported", "not_verified"] as const).map((k) => ({
                label: VERIFICATION_LABEL[k]!, value: summary[k], color: STATUS_COLOR[k]!,
              }))} />
              <dl className="mt-3">
                {(["supported", "partially_supported", "unsupported", "not_verified"] as const).map((k) => (
                  <div key={k} className="flex items-center justify-between py-1">
                    <dt className="flex items-center gap-2 text-soft">
                      <span className="h-2 w-2 rounded-full" style={{ background: STATUS_COLOR[k] }} aria-hidden="true" />{VERIFICATION_LABEL[k]}
                    </dt>
                    <dd className="num">{summary[k]}</dd>
                  </div>
                ))}
              </dl>
              <p className="mt-3 text-small text-muted">
                Quotes are checked verbatim against the filing, numbers against computed metrics, and the rest by a separate fact-check pass. Unsupported claims stay in the ledger, flagged, and are kept out of the summary.
              </p>
            </div>
          </Panel>

          <Panel id="limitations" title="Limitations">
            <ul className="list-disc space-y-2 px-6 pb-5 pl-10 text-soft marker:text-muted">
              {report.limitations.map((l, i) => <li key={i}>{l}</li>)}
            </ul>
          </Panel>

          <Panel id="sources" title="Sources">
            <ul className="divide-y divide-rule pb-2">
              {report.filings.map((f) => (
                <li key={f.id} className="px-6 py-2.5">
                  <a href={f.url} target="_blank" rel="noreferrer" className="flex items-center justify-between gap-3 hover:underline">
                    <span>{f.form} <span className="num text-muted">{f.accession}</span></span><ExternalIcon />
                  </a>
                  <dl className="grid grid-cols-2 text-small">
                    <dt className="text-muted">Period ended</dt><dd className="num text-right">{date(f.period)}</dd>
                    <dt className="text-muted">Filed</dt><dd className="num text-right">{date(f.filed)}</dd>
                  </dl>
                </li>
              ))}
              <li className="px-6 py-2.5 text-small text-muted">
                Financial data: SEC XBRL company facts for {report.company.name}, CIK <span className="num">{report.company.cik}</span>
                {report.company.sic_description ? `. Industry: ${report.company.sic_description}` : ""}
              </li>
            </ul>
          </Panel>

          {report.open_questions.length > 0 && (
            <Panel id="open-questions" title="Open questions">
              <ul className="list-disc space-y-2 px-6 pb-5 pl-10 text-soft marker:text-muted">
                {report.open_questions.map((q, i) => <li key={i}>{q}</li>)}
              </ul>
            </Panel>
          )}
        </aside>
      </div>

      <p className="mt-8 max-w-[90ch] text-small text-muted">{report.disclaimer}</p>
      <Inspector target={target} onClose={() => setTarget(null)} />
    </>
  );
}

function ClaimRow({ claim, number, onOpen }: { claim: Claim; number: number; onOpen: () => void }) {
  const sourceHint = claim.metrics[0]
    ? `${claim.metrics[0].label} ${claim.metrics[0].period}`
    : claim.evidence[0] ? `${claim.evidence[0].document.form}, ${claim.evidence[0].quote_verified ? "quote found verbatim" : "quote not found"}` : "no evidence cited";
  return (
    <li>
      <button type="button" onClick={onOpen}
        className="press grid w-full grid-cols-[28px_1fr_auto] items-start gap-x-3 gap-y-1 px-6 py-2.5 text-left hover:bg-raised">
        <span className="num pt-px text-muted">{number}</span>
        <span className={claim.verification_status === "unsupported" ? "text-muted" : ""}>{claim.text}</span>
        <VerificationPill status={claim.verification_status} />
        <span className="col-start-2 text-small text-muted">{CLAIM_TYPE_LABEL[claim.claim_type]}. Source: {sourceHint}</span>
      </button>
    </li>
  );
}
