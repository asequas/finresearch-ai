import { Link } from "react-router-dom";

import { isActive, useJobs, useMeta } from "../api/client";
import { JobRows, JobRowsLoading } from "../components/JobRows";
import { ResearchForm } from "../components/ResearchForm";
import { Empty, ErrorBlock, Notice, PageTitle, Panel } from "../components/ui";
import { duration, relative } from "../lib/format";
import { useTitle } from "../lib/useTitle";

/** The screen's question: what is running, and what is ready to read? */
export function Overview() {
  const jobs = useJobs({ limit: 30 });
  const meta = useMeta();
  useTitle("Overview");
  const all = jobs.data?.pages.flatMap((p) => p.items) ?? [];
  const active = all.filter((j) => isActive(j.status));
  const ready = all.filter((j) => j.has_report).slice(0, 6);
  const failed = all.filter((j) => j.status === "failed").slice(0, 3);

  const finding = jobs.isPending
    ? "Loading your research desk…"
    : active.length
      ? `${active.length} ${active.length === 1 ? "job is" : "jobs are"} in progress.${ready[0] ? ` Latest report: ${ready[0].ticker}, ${relative(ready[0].completed_at)}.` : ""}`
      : ready[0]
        ? `Nothing running. Latest report: ${ready[0].ticker}, ${relative(ready[0].completed_at)}.`
        : "No research yet. Start with a ticker and a question.";

  return (
    <>
      <PageTitle title="Overview" sub={finding} />
      {meta.data && (!meta.data.gemini_configured || !meta.data.sec_configured) && (
        <div className="mb-6">
          <Notice>
            Research jobs need {[!meta.data.gemini_configured && "GEMINI_API_KEY", !meta.data.sec_configured && "SEC_USER_AGENT"].filter(Boolean).join(" and ")} in
            the backend's .env. Jobs submitted now will fail with that reason. <Link to="/settings" className="font-medium underline underline-offset-4">See setup</Link>
          </Notice>
        </div>
      )}
      <dl className="panel mb-6 grid grid-cols-2 gap-y-4 py-4 lg:grid-cols-4 lg:divide-x lg:divide-rule lg:py-0" aria-label="Queue">
        {[
          ["Running", meta.data?.queue.running],
          ["Queued", meta.data?.queue.queued],
          ["Oldest waiting", meta.data?.queue.oldest_queued_seconds != null ? duration(meta.data.queue.oldest_queued_seconds * 1000) : meta.data ? "0s" : undefined],
          ["Reports ready", jobs.data ? `${all.filter((j) => j.has_report).length}${jobs.hasNextPage ? "+" : ""}` : undefined],
        ].map(([label, value]) => (
          <div key={label as string} className="px-6 lg:py-4">
            <dt className="text-muted">{label}</dt>
            <dd className="num mt-1 text-section">{value ?? "—"}</dd>
          </div>
        ))}
      </dl>
      <div className="grid grid-cols-1 items-start gap-6 xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="grid gap-6">
          <Panel id="in-progress" title="In progress" aside={active.length ? <span className="num">{active.length} active</span> : undefined}>
            {jobs.isPending ? <JobRowsLoading rows={2} />
              : jobs.isError ? <ErrorBlock error={jobs.error} onRetry={() => jobs.refetch()} />
              : active.length ? <div className="pb-2"><JobRows jobs={active} /></div>
              : <Empty>No jobs running. New research appears here with its eight stages.</Empty>}
          </Panel>

          <Panel id="ready" title="Ready to read" aside={<Link to="/reports" className="text-soft hover:text-ink">View all</Link>}>
            {jobs.isPending ? <JobRowsLoading rows={4} />
              : ready.length ? <div className="pb-2"><JobRows jobs={ready} showStrip={false} /></div>
              : <Empty>Completed reports appear here, newest first.</Empty>}
          </Panel>

          {failed.length > 0 && (
            <Panel id="failed" title="Needs attention" aside={<Link to="/research?status=failed" className="text-soft hover:text-ink">View all</Link>}>
              <div className="pb-2"><JobRows jobs={failed} showStrip={false} /></div>
            </Panel>
          )}
        </div>

        <div className="xl:sticky xl:top-8">
          <Panel id="new" title="New research">
            <ResearchForm compact />
          </Panel>
        </div>
      </div>
    </>
  );
}
