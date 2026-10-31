import { Link, useParams } from "react-router-dom";

import { ApiError, type CompanyDetail, useCompany } from "../api/client";
import { BarChart, LineChart } from "../components/charts";
import { JobRows } from "../components/JobRows";
import { Bar, ButtonLink, ErrorBlock, PageTitle, Panel } from "../components/ui";
import { changeText, date, metricDisplay, money, toNumber, usd, usdTick } from "../lib/format";
import { useTitle } from "../lib/useTitle";

const STRIP = [
  { key: "revenue_growth", label: "Revenue growth", sign: true },
  { key: "operating_margin", label: "Operating margin" },
  { key: "fcf_margin", label: "Free cash flow margin" },
  { key: "return_on_equity", label: "Return on equity" },
  { key: "net_debt", label: "Net debt" },
];

function latestMetric(detail: CompanyDetail, key: string) {
  const series = detail.metrics.filter((m) => m.key === key && !m.period.includes("-"));
  return series[series.length - 1];
}

function series(detail: CompanyDetail, key: string) {
  return detail.financials.map((f) => ({
    label: f.period,
    value: toNumber(detail.metrics.find((m) => m.key === key && m.period === f.period)?.value),
  }));
}

/** The company workspace: what the latest report's filings say, over five years, and all research on it. */
export function CompanyPage() {
  const { ticker = "" } = useParams();
  const company = useCompany(ticker.toUpperCase());
  const detail = company.data;
  useTitle(detail ? `${detail.company.name} (${detail.company.ticker})` : ticker.toUpperCase());

  if (company.isError) {
    const missing = company.error instanceof ApiError && company.error.status === 404;
    return (
      <>
        <PageTitle title={ticker.toUpperCase()} sub={missing ? "There is no research on this company yet." : undefined}
          actions={<ButtonLink to={`/research?new=${ticker.toUpperCase()}`} variant="primary">Research {ticker.toUpperCase()}</ButtonLink>} />
        {!missing && <Panel><div className="pt-6"><ErrorBlock error={company.error} onRetry={() => company.refetch()} /></div></Panel>}
      </>
    );
  }

  // Prefer the name the user typed ("NVIDIA Corporation") over SEC's registrant style ("NVIDIA CORP").
  const name = detail?.jobs[0]?.company ?? detail?.company.name ?? ticker.toUpperCase();
  return (
    <>
      <nav aria-label="Breadcrumb" className="mb-3 text-small text-muted">
        <Link to="/companies" className="hover:text-ink">Companies</Link> <span aria-hidden="true">/</span>{" "}
        <span className="num" translate="no">{ticker.toUpperCase()}</span>
      </nav>
      <PageTitle
        title={detail ? <>{name} <span className="font-normal text-muted" translate="no">{detail.company.ticker}</span></> : <Bar w={320} h={28} />}
        sub={detail && (detail.data_as_of
          ? `Figures from the latest report, fiscal year ended ${date(detail.data_as_of)}.`
          : "Research is in progress; figures appear when the first report is ready.")}
        actions={detail && (
          <>
            <ButtonLink to={`/research?new=${detail.company.ticker}&company=${encodeURIComponent(name)}`}>New research</ButtonLink>
            {detail.latest_report_job_id && <ButtonLink to={`/reports/${detail.latest_report_job_id}`} variant="primary">Open latest report</ButtonLink>}
          </>
        )}
      />

      {detail && (
        <dl className={`panel mb-6 grid grid-cols-2 gap-x-4 gap-y-4 px-6 py-4 ${detail.latest_valuation ? "md:grid-cols-5" : "md:grid-cols-4"}`} aria-label="Company facts">
          {[
            ["Industry", detail.company.sic_description ?? "—"],
            ["Fiscal year ends", detail.company.fiscal_year_end ? date(`2026-${detail.company.fiscal_year_end.slice(0, 2)}-${detail.company.fiscal_year_end.slice(2)}`, { month: "long", day: "numeric" }) : "—"],
            ["Exchange", detail.company.exchange ?? "—"],
            ["SEC CIK", detail.company.cik],
          ].map(([label, value]) => (
            <div key={label}>
              <dt className="text-small text-muted">{label}</dt>
              <dd className={label === "SEC CIK" ? "num" : ""}>{value}</dd>
            </div>
          ))}
          {detail.latest_valuation && (
            <div>
              <dt className="text-small text-muted">Fair value per share</dt>
              <dd>
                <Link to={`/reports/${detail.latest_valuation.job_id}#valuation`} className="num hover:underline">
                  {money(detail.latest_valuation.value_per_share)}
                </Link>
                <span className="ml-1.5 text-small text-muted">FY{detail.latest_valuation.base_year} base</span>
              </dd>
            </div>
          )}
        </dl>
      )}

      {detail && detail.metrics.length > 0 && (
        <>
          <dl className="panel mb-6 grid grid-cols-2 gap-y-4 py-4 md:grid-cols-5 md:divide-x md:divide-rule md:py-0" aria-label="Latest fiscal year">
            {STRIP.map(({ key, label, sign }) => {
              const metric = latestMetric(detail, key);
              return (
                <div key={key} className="px-6 md:py-4">
                  <dt className="text-muted">{label}</dt>
                  <dd className="num mt-1 text-section">{metric ? metricDisplay(key, metric.value, metric.unit, { sign }) : "—"}</dd>
                  <dd className="num text-small text-muted">{metric?.period ?? "not reported"}</dd>
                </div>
              );
            })}
          </dl>

          <div className="mb-6 grid grid-cols-1 gap-6 xl:grid-cols-3">
            <Panel id="revenue" title="Revenue">
              <div className="px-6 pb-5">
                <BarChart title={`${name} revenue by fiscal year`} format={(v) => usd(v)} tickFormat={usdTick}
                  changeFormat={(a, b) => changeText(a, b, "pct")}
                  points={detail.financials.map((f) => ({ label: f.period, value: toNumber(f.values.revenue?.value) }))} />
              </div>
            </Panel>
            <Panel id="margin" title="Operating margin">
              <div className="px-6 pb-5">
                <LineChart title={`${name} operating margin by fiscal year`} format={(v) => `${(v * 100).toFixed(1)}%`} tickFormat={(v) => `${Math.round(v * 100)}%`}
                  changeFormat={(a, b) => changeText(a, b, "pp")} points={series(detail, "operating_margin")} />
              </div>
            </Panel>
            <Panel id="fcf" title="Free cash flow">
              <div className="px-6 pb-5">
                <BarChart title={`${name} free cash flow by fiscal year`} format={(v) => usd(v)} tickFormat={usdTick}
                  changeFormat={(a, b) => changeText(a, b, "pct")} points={series(detail, "free_cash_flow")} />
              </div>
            </Panel>
          </div>
        </>
      )}

      <Panel id="history" title="Research on this company" aside={detail && <span className="num">{detail.jobs.length}</span>}>
        {detail ? <div className="pb-2"><JobRows jobs={detail.jobs} /></div>
          : <div className="grid gap-4 px-6 pb-6">{[0, 1].map((i) => <Bar key={i} w="100%" h={36} />)}</div>}
      </Panel>
    </>
  );
}
