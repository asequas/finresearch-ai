import type { Job, JobDetail, Stage } from "../api/client";
import { STAGES } from "../lib/format";

export type StageState = "done" | "running" | "failed" | "pending";

type Run = JobDetail["stages"] extends (infer R)[] | undefined ? R : never;

export function stageStates(job: Job, runs: Run[] = []): Record<Stage, StageState> {
  const done = new Set(runs.filter((r) => r.status === "completed").map((r) => r.stage));
  const latestByStage = new Map<string, Run>();
  for (const run of runs) latestByStage.set(run.stage, run);

  // Without stage runs (list rows), infer from the current stage: the pipeline is sequential.
  const currentIndex = STAGES.findIndex((s) => s.key === job.current_stage);
  if (runs.length === 0 && currentIndex > 0) STAGES.slice(0, currentIndex).forEach((s) => done.add(s.key));
  if (runs.length === 0 && job.status === "failed" && job.current_stage) {
    latestByStage.set(job.current_stage, { stage: job.current_stage, status: "failed" } as Run);
  }

  const states = {} as Record<Stage, StageState>;
  for (const { key } of STAGES) {
    // Running wins over done: researchers run in parallel, and a revision round revisits a finished stage.
    if (job.status === "running" && job.current_stage === key) states[key] = "running";
    else if (job.status === "completed" || done.has(key)) states[key] = "done";
    else if (latestByStage.get(key)?.status === "failed") states[key] = "failed";
    else states[key] = "pending";
  }
  return states;
}

const FILL: Record<StageState, string> = {
  done: "bg-soft",
  running: "bg-accent",
  failed: "bg-negative",
  pending: "bg-raised",
};

/**
 * The product's signature: one segment per pipeline stage. Completed stages are ink,
 * the running stage carries the one accent, a failed stage the negative colour.
 */
export function StageStrip({ job, runs, compact = false }: { job: Job; runs?: Run[]; compact?: boolean }) {
  const states = stageStates(job, runs);
  const current = STAGES.find((s) => states[s.key] === "running" || states[s.key] === "failed");
  const doneCount = STAGES.filter((s) => states[s.key] === "done").length;
  const label =
    job.status === "completed"
      ? `All ${STAGES.length} stages complete`
      : `${doneCount} of ${STAGES.length} stages complete${current ? `, ${states[current.key] === "failed" ? "failed at" : "now"} ${current.label.toLowerCase()}` : ""}`;

  return (
    <div role="img" aria-label={label} className="flex w-full gap-[3px]">
      {STAGES.map((stage) => (
        <span
          key={stage.key}
          title={`${stage.label}: ${states[stage.key]}`}
          className={`${compact ? "h-1" : "h-1.5"} flex-1 rounded-[1px] ${FILL[states[stage.key]]} ${states[stage.key] === "running" ? "live-dot" : ""}`}
        />
      ))}
    </div>
  );
}
