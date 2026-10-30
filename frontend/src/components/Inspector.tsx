import { type ReactNode, useEffect, useRef } from "react";

import type { Claim, Evidence, Metric } from "../api/client";
import { CLAIM_TYPE_LABEL, FIELD_LABEL, SECTION_LABEL, date, metricDisplay, usd } from "../lib/format";
import { CloseIcon, ExternalIcon } from "./icons";
import { VerificationPill } from "./ui";

export type InspectTarget =
  | { kind: "claim"; claim: Claim; number: number }
  | { kind: "metric"; metric: Metric }
  | { kind: "fact"; field: string; period: string; value: string | null; provenance: Record<string, unknown> | null; filingUrl?: string };

const TYPE_EXPLAINER: Record<string, string> = {
  fact: "Something the filing states. It must quote the filing verbatim.",
  calculation: "Computed by FinResearch from reported figures with a tested formula. The model never does the arithmetic.",
  interpretation: "Analytical judgement drawn from the cited passages and metrics. Read it as opinion, not fact.",
};

const SOURCE_SECTION: Record<string, string> = {
  business: "Item 1. Business",
  risk_factors: "Item 1A. Risk Factors",
  mdna: "Management's Discussion and Analysis",
  market_risk: "Market risk disclosures",
  document: "Filing text",
};

function escape(text: string) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Highlight each ellipsis-separated part of the quote inside its passage (whitespace-insensitive). */
export function Highlighted({ context, quote }: { context: string; quote: string }) {
  const parts = quote.split(/\.\.\.|…/).map((p) => p.trim().replace(/^[\s.,;:]+|[\s.,;:]+$/g, "")).filter((p) => p.length > 3);
  if (!parts.length) return <>{context}</>;
  // Match like the verifier: whitespace- and quote-insensitive, and "$" optional (table cells split it off).
  const words = (p: string) => p.replace(/\$\s*/g, "").split(/\s+/).filter(Boolean)
    .map((w) => (/^[\d(]/.test(w) ? "\\$?\\s*" : "") + escape(w).replace(/['’]/g, "['’]"));
  const pattern = new RegExp(parts.map((p) => words(p).join("\\s+")).join("|"), "gi");
  const nodes: ReactNode[] = [];
  let last = 0;
  for (const match of context.matchAll(pattern)) {
    nodes.push(context.slice(last, match.index));
    nodes.push(<mark key={match.index}>{match[0]}</mark>);
    last = match.index + match[0].length;
  }
  nodes.push(context.slice(last));
  return <>{nodes}</>;
}

function EvidenceBlock({ evidence }: { evidence: Evidence }) {
  const passage = useRef<HTMLQuoteElement>(null);
  // Bring the highlighted words into view; the quote is often deep inside a long passage.
  useEffect(() => {
    const mark = passage.current?.querySelector("mark");
    if (mark && passage.current) passage.current.scrollTop = Math.max(0, (mark as HTMLElement).offsetTop - 48);
  }, [evidence.id]);
  return (
    <figure className="border-t border-rule pt-4">
      <figcaption className="mb-2 flex flex-wrap items-baseline justify-between gap-2 text-small text-muted">
        <span>
          <span className="text-ink">{evidence.document.form}</span>, {SOURCE_SECTION[evidence.section ?? ""] ?? evidence.section ?? "Filing"}, filed{" "}
          <span className="num">{date(evidence.document.filed)}</span>
        </span>
        <a href={evidence.document.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-soft hover:text-ink">
          Open on SEC.gov <ExternalIcon />
        </a>
      </figcaption>
      <blockquote ref={passage} className="relative max-h-72 overflow-y-auto rounded-[6px] bg-raised p-4 text-read whitespace-pre-line text-soft">
        {evidence.context ? <Highlighted context={evidence.context} quote={evidence.quote} /> : evidence.quote}
      </blockquote>
      <p className={`mt-2 text-small ${evidence.quote_verified ? "text-muted" : "text-[var(--pill-negative-ink)]"}`}>
        {evidence.quote_verified
          ? "The quoted words appear verbatim in this passage."
          : `Quote not found in the passage: “${evidence.quote}”. It does not count as support.`}
      </p>
    </figure>
  );
}

function MetricBlock({ metric, divided = true }: { metric: Metric; divided?: boolean }) {
  return (
    <div className={divided ? "border-t border-rule pt-4" : ""}>
      <div className="flex items-baseline justify-between gap-4">
        <span>{metric.label} <span className="num text-muted">{metric.period}</span></span>
        <span className="num text-card">{metricDisplay(metric.key, metric.value, metric.unit)}</span>
      </div>
      <p className="num mt-2 rounded-[6px] bg-raised px-3 py-2 text-small text-soft">{metric.formula}</p>
      <table className="mt-3 w-full text-small">
        <caption className="sr-only">Inputs</caption>
        <thead>
          <tr className="text-muted">
            <th scope="col" className="py-1 text-left font-normal">Input</th>
            <th scope="col" className="py-1 text-left font-normal">Period</th>
            <th scope="col" className="py-1 text-right font-normal">Reported value</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(metric.inputs as Record<string, { name: string; value: string; period: string }>).map(([key, input]) => (
            <tr key={key} className="border-t border-rule">
              <td className="py-1.5">{FIELD_LABEL[input.name] ?? input.name}</td>
              <td className="num py-1.5 text-muted">{input.period}</td>
              <td className="num py-1.5 text-right">{input.name === "eps" ? usd(input.value, { compact: false }) : usd(input.value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-small text-muted">Inputs come from SEC XBRL company facts. Calculation version <span className="num">{metric.calculation_version}</span>.</p>
    </div>
  );
}

export function Inspector({ target, onClose }: { target: InspectTarget | null; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (target && !dialog.open) dialog.showModal();
    if (!target && dialog.open) dialog.close();
  }, [target]);

  return (
    <dialog ref={ref} className="sheet" onClose={onClose} onClick={(e) => e.target === ref.current && onClose()}
      aria-labelledby="inspector-title">
      {target && (
        <div className="flex h-full flex-col">
          <header className="flex items-start justify-between gap-4 border-b border-rule px-6 py-4">
            <div>
              <p className="text-small text-muted">
                {target.kind === "claim" ? <>Claim <span className="num">{target.number}</span> in {SECTION_LABEL[target.claim.section] ?? target.claim.section}</>
                  : target.kind === "metric" ? "Calculation" : "Reported figure"}
              </p>
              <h2 id="inspector-title" className="text-card font-semibold">
                {target.kind === "claim" ? CLAIM_TYPE_LABEL[target.claim.claim_type]
                  : target.kind === "metric" ? target.metric.label
                  : `${FIELD_LABEL[target.field] ?? target.field}, ${target.period}`}
              </h2>
            </div>
            <button type="button" onClick={onClose} aria-label="Close" className="press -mr-2 flex h-9 w-9 items-center justify-center rounded-full text-muted hover:text-ink">
              <CloseIcon />
            </button>
          </header>
          <div className="flex-1 space-y-5 overflow-y-auto px-6 py-5">
            {target.kind === "claim" && (
              <>
                <p className="text-read">{target.claim.text}</p>
                <div className="flex flex-wrap items-center gap-3">
                  <VerificationPill status={target.claim.verification_status} />
                  {target.claim.verification_note && <span className="text-small text-muted">{target.claim.verification_note}</span>}
                </div>
                <p className="text-small text-muted">{TYPE_EXPLAINER[target.claim.claim_type]}</p>
                {target.claim.metrics.map((m) => <MetricBlock key={m.id} metric={m} />)}
                {target.claim.evidence.map((e) => <EvidenceBlock key={e.id} evidence={e} />)}
                {!target.claim.metrics.length && !target.claim.evidence.length && (
                  <p className="border-t border-rule pt-4 text-soft">No evidence was cited for this claim, so it is marked unsupported.</p>
                )}
              </>
            )}
            {target.kind === "metric" && <MetricBlock metric={target.metric} divided={false} />}
            {target.kind === "fact" && (
              <div className="space-y-3">
                <p className="num text-section">{target.value === null ? "Not reported" : target.field === "eps" ? usd(target.value, { compact: false }) : usd(target.value, { compact: false })}</p>
                {target.provenance ? (
                  <dl className="divide-y divide-rule">
                    {[
                      ["XBRL concept", String(target.provenance.concept ?? "—")],
                      ["Filing", `${target.provenance.form ?? ""}, accession ${target.provenance.accession ?? ""}`],
                      ["Filed", date(String(target.provenance.filed ?? ""))],
                      ["Period", `${date(String(target.provenance.period_start ?? "")) === "—" ? "" : `${date(String(target.provenance.period_start))} – `}${date(String(target.provenance.period_end ?? ""))}`],
                      ["Unit", String(target.provenance.unit ?? "USD")],
                    ].map(([label, value]) => (
                      <div key={label} className="flex justify-between gap-4 py-2">
                        <dt className="text-muted">{label}</dt><dd className="num text-right">{value}</dd>
                      </div>
                    ))}
                  </dl>
                ) : <p className="text-soft">The company did not report this item in XBRL for this period, so it is shown as a dash and any metric that needs it is skipped.</p>}
                <p className="text-small text-muted">When a later filing restates a figure, the most recently filed value is used.</p>
              </div>
            )}
          </div>
        </div>
      )}
    </dialog>
  );
}
