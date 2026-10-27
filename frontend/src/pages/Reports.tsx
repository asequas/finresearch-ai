import { Link } from "react-router-dom";

import { useJobs } from "../api/client";
import { Bar, Button, ButtonLink, Empty, ErrorBlock, PageTitle, Panel } from "../components/ui";
import { date, relative } from "../lib/format";

export function Reports() {
  const jobs = useJobs({ status: "completed" });
  const rows = (jobs.data?.pages.flatMap((p) => p.items) ?? []).filter((j) => j.has_report);

  return (
    <>
      <PageTitle title="Reports" sub="Every completed report, newest first. Reports are saved, so you can come back to them at any time."
        actions={<ButtonLink to="/research" variant="primary">New research</ButtonLink>} />
      <Panel id="reports" title="Completed reports" aside={jobs.data && <span className="num">{rows.length} shown</span>}>
        {jobs.isPending ? (
          <div className="grid gap-4 px-6 pb-6">{[0, 1, 2].map((i) => <Bar key={i} w="100%" h={36} />)}</div>
        ) : jobs.isError ? <ErrorBlock error={jobs.error} onRetry={() => jobs.refetch()} />
        : rows.length === 0 ? <Empty action={<ButtonLink to="/research">Start research</ButtonLink>}>No reports yet.</Empty>
        : (
          <div className="overflow-x-auto">
            <table className="w-full text-body max-md:min-w-[560px]">
              <thead>
                <tr className="text-small text-muted">
                  <th scope="col" className="w-20 px-6 py-2 text-left font-normal">Ticker</th>
                  <th scope="col" className="py-2 text-left font-normal">Question</th>
                  <th scope="col" className="py-2 pr-6 text-right font-normal">Completed</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((job) => (
                  <tr key={job.id} className="border-t border-rule hover:bg-raised">
                    <td className="num px-6 py-3 align-top font-medium">
                      <Link to={`/reports/${job.id}`} className="hover:underline">{job.ticker}</Link>
                    </td>
                    <td className="py-3 align-top">
                      <Link to={`/reports/${job.id}`} className="block">
                        <span className="block">{job.company}</span>
                        <span className="block max-w-[80ch] truncate text-small text-muted">{job.query}</span>
                      </Link>
                    </td>
                    <td className="num py-3 pr-6 text-right align-top">
                      {date(job.completed_at)}
                      <span className="block text-small text-muted">{relative(job.completed_at)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {jobs.hasNextPage && (
              <div className="px-6 py-4"><Button onClick={() => jobs.fetchNextPage()} disabled={jobs.isFetchingNextPage}>Load more</Button></div>
            )}
          </div>
        )}
      </Panel>
    </>
  );
}
