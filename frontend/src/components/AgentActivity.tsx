import type { Researcher, ToolCall, Trace } from "../api/client";
import { useTrace } from "../api/client";
import { SECTION_LABEL, duration } from "../lib/format";
import { CheckIcon, CrossIcon } from "./icons";
import { Bar, Empty, ErrorBlock, Pill, Panel } from "./ui";

const TOOL_LABEL: Record<string, string> = {
  search_filings: "Search",
  read_passage: "Read",
  get_metrics: "Metrics",
  get_reported_figures: "Figures",
  get_report_claims: "Report",
};

/** The one argument worth showing for a tool call: the search terms, the passage, the metrics asked for. */
export function toolInput(call: ToolCall): string {
  const input = call.input as Record<string, unknown>;
  const value = input.query ?? input.handle ?? (input.keys as string[] | undefined)?.join(", ") ?? (input.fields as string[] | undefined)?.join(", ");
  const form = input.form && input.form !== "any" ? ` (${input.form})` : "";
  return value ? `${value}${form}` : "all";
}

export function ToolCallRow({ call }: { call: ToolCall }) {
  return (
    <li className="grid grid-cols-[64px_minmax(0,1fr)_auto] items-baseline gap-x-3 py-1.5">
      <span className="num text-small text-muted">{TOOL_LABEL[call.tool] ?? call.tool}</span>
      <span className="min-w-0">
        <span className="block truncate text-ink" title={toolInput(call)}>{toolInput(call)}</span>
        <span className="block truncate text-small text-muted" title={call.summary}>{call.summary}</span>
      </span>
      <span className="num text-small text-muted">{duration(call.ms)}</span>
    </li>
  );
}

function StatusMark({ status }: { status: string }) {
  if (status === "completed") return <CheckIcon className="text-soft" />;
  if (status === "failed") return <CrossIcon className="text-negative" />;
  return <span className="live-dot h-2 w-2 rounded-full bg-accent" />;
}

function Lane({ researcher }: { researcher: Researcher }) {
  const running = researcher.status === "running";
  return (
    <li className="border-t border-rule">
      <details open={running} className="group">
        <summary className="grid cursor-pointer list-none grid-cols-[20px_minmax(0,1fr)_auto] items-start gap-x-3 px-6 py-3 hover:bg-raised">
          <span className="mt-0.5 flex h-4 w-4 items-center justify-center" aria-hidden="true"><StatusMark status={researcher.status} /></span>
          <span className="min-w-0">
            <span className="block text-ink">{researcher.question}</span>
            <span className="block text-small text-muted">
              {researcher.kind === "gap" ? "Re-checking a rejected claim" : "Planned question"}
              {researcher.attempt > 1 && `, attempt ${researcher.attempt}`}
            </span>
          </span>
          <span className="num text-right text-small text-muted">
            <span className="block">{researcher.tool_calls.length} {researcher.tool_calls.length === 1 ? "call" : "calls"}</span>
            {researcher.duration_ms != null && <span className="block">{duration(researcher.duration_ms)}</span>}
          </span>
        </summary>
        <div className="px-6 pb-4 pl-[56px]">
          {researcher.tool_calls.length > 0
            ? <ol aria-label="Tool calls" className="divide-y divide-rule">{researcher.tool_calls.map((call, i) => <ToolCallRow key={i} call={call} />)}</ol>
            : <p className="text-muted">{running ? "Thinking about where to look…" : "No tool calls recorded."}</p>}
          {researcher.answer && <p className="mt-3 text-read">{researcher.answer}</p>}
          {researcher.gaps.length > 0 && (
            <p className="mt-2 text-small text-muted">Not in the filings: {researcher.gaps.join("; ")}</p>
          )}
          {researcher.dropped_handles.length > 0 && (
            <p className="mt-2 text-small text-muted">
              Ignored {researcher.dropped_handles.length} cited {researcher.dropped_handles.length === 1 ? "passage" : "passages"} that
              no tool had returned, so they can't become evidence.
            </p>
          )}
          {researcher.error_message && <p role="alert" className="mt-2 text-[var(--pill-negative-ink)]">{researcher.error_message}</p>}
        </div>
      </details>
    </li>
  );
}

function Verdicts({ counts }: { counts: Record<string, number> }) {
  const order: [string, string, "positive" | "warning" | "negative" | "neutral"][] = [
    ["supported", "supported", "positive"], ["partially_supported", "partly supported", "warning"],
    ["unsupported", "unsupported", "negative"], ["not_verified", "not verified", "neutral"],
  ];
  return (
    <span className="flex flex-wrap gap-2">
      {order.filter(([key]) => counts[key]).map(([key, label, tone]) => (
        <Pill key={key} tone={tone}><span className="num">{counts[key]}</span> {label}</Pill>
      ))}
    </span>
  );
}

function RoundHeading({ round, count }: { round: number; count: number }) {
  return (
    <h3 className="px-6 pt-4 pb-2 text-small font-medium text-muted">
      {round === 0 ? `Researchers, ${count} in parallel` : `Revision ${round}: re-researching what the fact-checker rejected`}
    </h3>
  );
}

function Critic({ round }: { round: Trace["rounds"][number] }) {
  return (
    <div className="mx-6 my-3 rounded-[6px] bg-raised px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="font-medium">
          {round.restored ? "Fact-check of the restored draft" : `Fact-check${round.revision > 0 ? ` after revision ${round.revision}` : ""}`}
        </span>
        <Verdicts counts={round.verdicts} />
      </div>
      {round.decision && (
        <p className="mt-2 text-soft">
          {round.decision === "revise"
            ? `Sent ${round.gaps.length} ${round.gaps.length === 1 ? "item" : "items"} back for more research (${round.reason}).`
            : round.decision === "restore"
              ? `The revision made things worse, so it was undone: ${round.reason}.`
              : `Moved on to writing the report: ${round.reason}.`}
        </p>
      )}
    </div>
  );
}

/** Live view of the research agent: its plan, every researcher's tool calls, and the critic's decisions. */
export function AgentActivity({ jobId, live }: { jobId: string; live: boolean }) {
  const trace = useTrace(jobId, live);
  const data = trace.data;

  const aside = data && data.mode === "agent" && (
    <span className="num">{data.totals.researchers} agents, {data.totals.tool_calls} tool calls{data.totals.revisions ? `, ${data.totals.revisions} revision` : ""}</span>
  );

  return (
    <Panel id="agent" title="Research agent" aside={aside}>
      {trace.isError ? <ErrorBlock error={trace.error} onRetry={() => trace.refetch()} />
        : !data ? <div className="px-6 pb-6"><Bar w="70%" h={14} /><div className="mt-3"><Bar w="90%" h={14} /></div></div>
        : data.mode === "linear" ? (
          <p className="px-6 pb-6 text-muted">This report came from the earlier linear pipeline (one retrieval pass, one draft), so there is no agent trace.</p>
        )
        : data.plan.length === 0 ? (
          <Empty>The planner hasn't run yet. Its sub-questions appear here as soon as it does.</Empty>
        ) : (
          <>
            <p className="px-6 pb-3 text-muted">
              A planner splits the question; researcher agents search the filings and metrics in parallel; a fact-checker
              verifies every claim and sends material failures back for another look.
            </p>
            <h3 className="px-6 pt-2 pb-2 text-small font-medium text-muted">Plan</h3>
            <ol className="px-6 pb-2" aria-label="Research plan">
              {data.plan.map((q, i) => (
                <li key={q.id} className="grid grid-cols-[24px_minmax(0,1fr)_auto] gap-x-2 py-1">
                  <span className="num text-muted">{i + 1}</span>
                  <span>{q.question}</span>
                  <span className="text-small text-muted">{SECTION_LABEL[q.focus] ?? q.focus}</span>
                </li>
              ))}
            </ol>
            {[...new Set(data.researchers.map((r) => r.round))].sort().map((round) => {
              const lanes = data.researchers.filter((r) => r.round === round);
              const checks = data.rounds.filter((r) => r.revision === round);
              return (
                <section key={round} aria-label={round === 0 ? "Researchers" : `Revision ${round}`}>
                  <RoundHeading round={round} count={lanes.length} />
                  <ul>{lanes.map((r) => <Lane key={`${r.task_id}-${r.round}`} researcher={r} />)}</ul>
                  {checks.map((check) => <Critic key={`${check.revision}-${check.restored}`} round={check} />)}
                </section>
              );
            })}
            <div className="pb-3" />
          </>
        )}
    </Panel>
  );
}
