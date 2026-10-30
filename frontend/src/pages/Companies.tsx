import { Link } from "react-router-dom";

import { useCompanies } from "../api/client";
import { Bar, ButtonLink, Empty, ErrorBlock, PageTitle, Panel, StatusPill } from "../components/ui";
import { relative } from "../lib/format";
import { useTitle } from "../lib/useTitle";

export function Companies() {
  const companies = useCompanies();
  useTitle("Companies");

  return (
    <>
      <PageTitle title="Companies" sub="Companies you have researched, resolved to their SEC registration." />
      <Panel id="companies" title="Researched companies" aside={companies.data && <span className="num">{companies.data.length}</span>}>
        {companies.isPending ? (
          <div className="grid gap-4 px-6 pb-6">{[0, 1, 2].map((i) => <Bar key={i} w="100%" h={36} />)}</div>
        ) : companies.isError ? <ErrorBlock error={companies.error} onRetry={() => companies.refetch()} />
        : companies.data.length === 0 ? (
          <Empty action={<ButtonLink to="/research">Start research</ButtonLink>}>A company appears here once a job has resolved its ticker on SEC EDGAR.</Empty>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[680px] text-body">
              <thead>
                <tr className="text-small text-muted">
                  <th scope="col" className="px-6 py-2 text-left font-normal">Company</th>
                  <th scope="col" className="py-2 text-left font-normal">Industry</th>
                  <th scope="col" className="py-2 text-right font-normal">CIK</th>
                  <th scope="col" className="py-2 text-right font-normal">Jobs</th>
                  <th scope="col" className="py-2 pr-6 text-right font-normal">Latest</th>
                </tr>
              </thead>
              <tbody>
                {companies.data.map(({ company, display_name, job_count, latest_job_id, latest_job_status, latest_report_job_id, latest_activity_at }) => (
                  <tr key={company.id} className="border-t border-rule">
                    <td className="px-6 py-3">
                      <Link to={`/companies/${company.ticker}`} className="block font-medium hover:underline">{display_name}</Link>
                      <span className="num text-small text-muted" translate="no">{company.ticker}{company.exchange ? ` on ${company.exchange}` : ""}</span>
                    </td>
                    <td className="max-w-[260px] truncate py-3 text-soft">{company.sic_description ?? "—"}</td>
                    <td className="num py-3 text-right text-muted">{company.cik}</td>
                    <td className="num py-3 text-right">{job_count}</td>
                    <td className="py-3 pr-6 text-right">
                      <span className="flex items-center justify-end gap-3">
                        {latest_report_job_id
                          ? <Link to={`/reports/${latest_report_job_id}`} className="font-medium hover:underline">Open report</Link>
                          : <Link to={`/research/${latest_job_id}`}><StatusPill status={latest_job_status as "queued"} /></Link>}
                      </span>
                      <span className="num block text-small text-muted">{relative(latest_activity_at)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
