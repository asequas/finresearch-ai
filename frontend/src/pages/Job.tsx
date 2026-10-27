import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError, isActive, useJob, useJobAction, useMeta } from "../api/client";
import { CheckIcon, CrossIcon } from "../components/icons";
import { StageStrip, stageStates } from "../components/StageStrip";
import { Bar, Button, ButtonLink, ErrorBlock, Kv, Notice, PageTitle, Panel, StatusPill } from "../components/ui";
import { STAGES, dateTime, duration, elapsed } from "../lib/format";

function useNow(active: boolean) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [active]);
  return now;
}

export function JobPage() {
  const { jobId = "" } = useParams();
  const job = useJob(jobId);
  const meta = useMeta();
  const cancel = useJobAction("cancel");
  const retry = useJobAction("retry");
  const live = !!job.data && isActive(job.data.status);
  useNow(live);

  if (job.isError) {
    const missing = job.error instanceof ApiError && job.error.status === 404;
    return (
      <>
        <PageTitle title={missing ? "Job not found" : "Research job"} sub={missing ? "It may belong to another account or never existed." : undefined} />
        <Panel><div className="pt-6"><ErrorBlock error={job.error} onRetry={missing ? undefined : () => job.refetch()} /></div></Panel>
      </>
    );
  }

  const data = job.data;
  const states = data ? stageStates(data, data.stages) : null;
  const runsByStage = new Map((data?.stages ?? []).map((run) => [run.stage, run]));
  const waitingSeconds = data?.status === "queued" ? (Date.now() - new Date(data.created_at).getTime()) / 1000 : 0;
  const noWorker = data?.status === "queued" && waitingSeconds > 20 && meta.data?.queue.running === 0;

  const sub = !data ? undefined
    : data.status === "completed" ? `Completed in ${elapsed(data.started_at, data.completed_at)}. The report is ready.`
    : data.status === "failed" ? data.error_message
    : data.status === "cancelled" ? "Cancelled. Completed stages are kept, so a retry resumes where it stopped."
    : data.status === "queued" && data.attempts > 0 ? `Retrying soon (attempt ${data.attempts + 1} of ${data.max_attempts}). Last error: ${data.error_message}`
    : data.status === "queued" ? "Waiting for a worker to pick this up."
    : `Running for ${elapsed(data.started_at)} · ${STAGES.find((s) => s.key === data.current_stage)?.label ?? "starting"}`;

  return (
    <>
      <nav aria-label="Breadcrumb" className="mb-3 text-small text-muted">
        <Link to="/research" className="hover:text-ink">Research</Link> <span aria-hidden="true">/</span> <span className="num">{data?.ticker ?? "…"}</span>
      </nav>
      <PageTitle
        title={data ? `${data.ticker} · ${data.company}` : <Bar w={320} h={28} />}
        sub={sub}
        actions={data && (
          <>
            {isActive(data.status) && !data.cancel_requested && (
              <Button onClick={() => cancel.mutate(data.id)} disabled={cancel.isPending}>Cancel</Button>
            )}
            {(data.status === "failed" || data.status === "cancelled") && (
              <Button variant="primary" onClick={() => retry.mutate(data.id)} disabled={retry.isPending}>Retry</Button>
            )}
            {data.has_report && <ButtonLink to={`/reports/${data.id}`} variant="primary">Open report</ButtonLink>}
          </>
        )}
      />

      {noWorker && (
        <div className="mb-6">
          <Notice>No worker has picked this job up yet. Start one with <code className="num">python -m backend.worker.main</code>.</Notice>
        </div>
      )}
      {(cancel.isError || retry.isError) && (
        <p role="alert" className="mb-4 text-[var(--pill-negative-ink)]">{(cancel.error ?? retry.error)?.message}</p>
      )}

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <Panel id="stages" title="Stages" aside={data && <StatusPill status={data.status} />}>
          <div className="px-6 pb-2">
            {data ? <StageStrip job={data} runs={data.stages} /> : <Bar w="100%" h={6} />}
            <div className="mt-3 flex items-baseline justify-between text-small text-muted">
              <span>Progress</span>
              <span className="num text-ink" aria-live="polite">{data ? `${data.progress}%` : "—"}</span>
            </div>
          </div>
          <ol className="mt-2 divide-y divide-rule pb-2" aria-label="Pipeline stages">
            {STAGES.map((stage) => {
              const state = states?.[stage.key] ?? "pending";
              const run = runsByStage.get(stage.key);
              return (
                <li key={stage.key} className="grid grid-cols-[20px_1fr_auto] items-start gap-x-3 px-6 py-3"
                  aria-current={state === "running" ? "step" : undefined}>
                  <span className="mt-0.5 flex h-4 w-4 items-center justify-center" aria-hidden="true">
                    {state === "done" ? <CheckIcon className="text-soft" />
                      : state === "failed" ? <CrossIcon className="text-negative" />
                      : state === "running" ? <span className="live-dot h-2 w-2 rounded-full bg-accent" />
                      : <span className="h-1.5 w-1.5 rounded-full bg-control" />}
                  </span>
                  <span className="min-w-0">
                    <span className={state === "pending" ? "text-muted" : "text-ink"}>{stage.label}</span>
                    <span className={`block ${state === "failed" ? "text-[var(--pill-negative-ink)]" : "text-muted"}`}>
                      {state === "failed" && run?.error_message ? run.error_message : stage.detail}
                    </span>
                  </span>
                  <span className="num text-right text-small text-muted">
                    {state === "running" && run ? elapsed(run.started_at)
                      : run?.duration_ms != null ? duration(run.duration_ms) : "—"}
                    {run && run.attempt > 1 && <span className="block">attempt {run.attempt}</span>}
                    {run?.input_tokens != null && <span className="block">{(run.input_tokens + (run.output_tokens ?? 0)).toLocaleString()} tok</span>}
                  </span>
                </li>
              );
            })}
          </ol>
          <p className="sr-only" aria-live="polite">
            {data?.status === "running" ? `Now ${STAGES.find((s) => s.key === data.current_stage)?.label ?? ""}` : data?.status}
          </p>
        </Panel>

        <div className="grid grid-cols-1 gap-6">
        <Panel id="request" title="Request">
          <div className="px-6 pb-6">
            <p className="text-read">{data?.query ?? <Bar w="90%" h={16} />}</p>
            <dl className="mt-4 border-t border-rule pt-3">
              <Kv label="Submitted"><span className="num">{dateTime(data?.created_at)}</span></Kv>
              <Kv label="Started"><span className="num">{dateTime(data?.started_at)}</span></Kv>
              <Kv label="Finished"><span className="num">{dateTime(data?.completed_at)}</span></Kv>
              <Kv label="Job ID"><span className="num text-small">{data?.id.slice(0, 8) ?? "—"}…</span></Kv>
            </dl>
            <p className="mt-4 text-small text-muted">
              You can leave this page and come back; the job lives in the database, not in this tab.
            </p>
          </div>
        </Panel>
        <Panel id="execution" title="Execution">
          <dl className="px-6 pb-3">
            <Kv label="Attempt"><span className="num">{data ? `${Math.max(data.attempts, 1)} of ${data.max_attempts}` : "—"}</span></Kv>
            <Kv label="Worker lease">
              <span className="num">
                {data?.status === "running" && data.lease_expires_at
                  ? `${duration(Math.max(0, new Date(data.lease_expires_at).getTime() - Date.now()))} left`
                  : data?.status === "queued" ? "not claimed" : "released"}
              </span>
            </Kv>
            <Kv label="Cancel requested">{data?.cancel_requested ? "Yes, stops after this stage" : "No"}</Kv>
          </dl>
          <p className="px-6 pb-6 text-muted">
            A worker holds a lease on the job and renews it every few seconds. If the worker crashes, the lease runs out and another
            worker resumes from the last completed stage; a worker that loses its lease can't write anything more.
          </p>
        </Panel>
        </div>
      </div>
    </>
  );
}
