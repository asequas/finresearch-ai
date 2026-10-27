import { useSearchParams } from "react-router-dom";

import { type JobStatus, useJobs } from "../api/client";
import { JobRows, JobRowsLoading } from "../components/JobRows";
import { ResearchForm } from "../components/ResearchForm";
import { Button, Empty, ErrorBlock, PageTitle, Panel } from "../components/ui";
import { STATUS_LABEL } from "../lib/format";

const FILTERS: (JobStatus | undefined)[] = [undefined, "running", "queued", "completed", "failed", "cancelled"];

export function Research() {
  const [params, setParams] = useSearchParams();
  const status = (params.get("status") as JobStatus | null) ?? undefined;
  const ticker = params.get("ticker") ?? "";
  const jobs = useJobs({ status, ticker });
  const rows = jobs.data?.pages.flatMap((p) => p.items) ?? [];

  function set(key: string, value: string | undefined) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: true });
  }

  return (
    <>
      <PageTitle title="Research" sub="Ask a question about a US-listed company. The answer is built from its SEC filings, and every claim links to its evidence." />
      <div className="grid gap-6">
        <Panel id="ask" title="New research">
          <ResearchForm />
        </Panel>

        <Panel id="history" title="Job history">
          <div className="flex flex-wrap items-end justify-between gap-4 border-b border-rule px-6">
            <div role="tablist" aria-label="Filter by status" className="-mb-px flex gap-5 overflow-x-auto">
              {FILTERS.map((value) => (
                <button key={value ?? "all"} type="button" role="tab" aria-selected={status === value}
                  className={`sel-line press h-9 whitespace-nowrap ${status === value ? "text-ink" : "text-muted hover:text-soft"}`}
                  onClick={() => set("status", value)}>
                  {value ? STATUS_LABEL[value] : "All"}
                </button>
              ))}
            </div>
            <label className="mb-2 flex items-center gap-2 text-muted">
              <span>Ticker</span>
              <input value={ticker} onChange={(e) => set("ticker", e.target.value.toUpperCase())} spellCheck={false}
                className="num h-8 w-24 rounded-[6px] border border-control bg-transparent px-2 text-ink uppercase focus:border-accent focus:outline-none" />
            </label>
          </div>
          {jobs.isPending ? <JobRowsLoading rows={5} />
            : jobs.isError ? <div className="pt-4"><ErrorBlock error={jobs.error} onRetry={() => jobs.refetch()} /></div>
            : rows.length ? (
              <>
                <div className="pb-2"><JobRows jobs={rows} /></div>
                <div className="flex items-center justify-between gap-4 px-6 pb-5 text-small text-muted">
                  <span className="num">{rows.length} shown</span>
                  {jobs.hasNextPage && (
                    <Button onClick={() => jobs.fetchNextPage()} disabled={jobs.isFetchingNextPage}>
                      {jobs.isFetchingNextPage ? "Loading…" : "Load more"}
                    </Button>
                  )}
                </div>
              </>
            ) : <div className="pt-4"><Empty>{status || ticker ? "No jobs match these filters." : "No research yet. Your jobs will be listed here."}</Empty></div>}
        </Panel>
      </div>
    </>
  );
}
