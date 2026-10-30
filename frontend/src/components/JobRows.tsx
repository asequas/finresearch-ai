import { Link } from "react-router-dom";

import type { Job } from "../api/client";
import { STAGES, relative } from "../lib/format";
import { StageStrip } from "./StageStrip";
import { Bar, StatusPill } from "./ui";

function stageLabel(job: Job) {
  if (job.status === "queued") return job.attempts > 0 ? `Retrying (attempt ${job.attempts + 1} of ${job.max_attempts})` : "Waiting for a worker";
  if (job.status === "running") return STAGES.find((s) => s.key === job.current_stage)?.label ?? "Starting";
  if (job.status === "failed") return job.error_message ?? "Failed";
  if (job.status === "cancelled") return "Cancelled";
  return job.has_report ? "Report ready" : "Completed";
}

/** Dense job list: ticker, company and question, the stage strip, status, recency. */
export function JobRows({ jobs, showStrip = true }: { jobs: Job[]; showStrip?: boolean }) {
  return (
    <ul className="divide-y divide-rule">
      {jobs.map((job) => (
        <li key={job.id}>
          <Link
            to={job.has_report ? `/reports/${job.id}` : `/research/${job.id}`}
            className="press grid grid-cols-[64px_1fr_auto] items-center gap-x-4 gap-y-1.5 px-6 py-3 hover:bg-raised md:grid-cols-[72px_minmax(0,1fr)_200px_112px]"
          >
            <span className="num font-medium" translate="no">{job.ticker}</span>
            <span className="min-w-0">
              <span className="block truncate">{job.company}</span>
              <span className="block truncate text-muted">{job.query}</span>
            </span>
            <span className="col-span-3 row-start-2 md:col-span-1 md:row-start-auto">
              {showStrip && <StageStrip job={job} compact />}
              <span className={`mt-1.5 block truncate ${job.status === "failed" ? "text-[var(--pill-negative-ink)]" : "text-muted"}`}>
                {stageLabel(job)}
              </span>
            </span>
            <span className="col-start-3 row-start-1 flex flex-col items-end gap-1 md:col-start-auto md:row-start-auto">
              <StatusPill status={job.status} />
              <span className="num text-small text-muted">{relative(job.updated_at)}</span>
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function JobRowsLoading({ rows = 3 }: { rows?: number }) {
  return (
    <ul aria-busy="true" aria-label="Loading jobs" className="divide-y divide-rule">
      {Array.from({ length: rows }, (_, i) => (
        <li key={i} className="grid grid-cols-[64px_1fr_auto] items-center gap-4 px-6 py-3 md:grid-cols-[72px_minmax(0,1fr)_200px_112px]">
          <Bar w={40} h={14} />
          <span className="grid gap-1.5"><Bar w="45%" h={14} /><Bar w="70%" h={12} /></span>
          <span className="hidden md:block"><Bar w="100%" h={4} /></span>
          <Bar w={72} h={20} />
        </li>
      ))}
    </ul>
  );
}
