import { type FormEvent, useId, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useSubmitResearch } from "../api/client";
import { Button } from "./ui";

const EXAMPLES = [
  { ticker: "MSFT", company: "Microsoft Corporation", query: "How durable is Microsoft's margin expansion, and what could reverse it?" },
  { ticker: "NVDA", company: "NVIDIA Corporation", query: "How dependent is NVIDIA on data-center demand, and how strong is its cash generation?" },
  { ticker: "COST", company: "Costco Wholesale Corporation", query: "Is Costco's growth driven by membership fees or merchandise margins?" },
];

const field =
  "h-10 w-full rounded-[6px] border border-control bg-transparent px-3 text-body text-ink placeholder:text-muted hover:border-muted focus:border-accent focus:outline-none";

function newKey() {
  return typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
}

export function ResearchForm({ compact = false }: { compact?: boolean }) {
  const ids = useId();
  const navigate = useNavigate();
  const submit = useSubmitResearch();
  // One key per form instance: double-clicks and network retries can't start a second job (ADR 0003).
  const [idempotencyKey, setIdempotencyKey] = useState(newKey);
  const [ticker, setTicker] = useState("");
  const [company, setCompany] = useState("");
  const [query, setQuery] = useState("");

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    submit.mutate(
      { body: { ticker, company, query }, idempotencyKey },
      {
        onSuccess: (job) => {
          setIdempotencyKey(newKey());
          navigate(`/research/${job.id}`);
        },
      },
    );
  }

  function edit(setter: (v: string) => void) {
    return (value: string) => {
      setter(value);
      if (submit.isError) submit.reset();
    };
  }

  return (
    <form onSubmit={onSubmit} className={`grid gap-4 px-6 pb-6 ${compact ? "" : "md:grid-cols-[140px_1fr]"}`} aria-describedby={`${ids}-scope`}>
      <div className="grid gap-2">
        <label htmlFor={`${ids}-ticker`} className="font-medium">Ticker</label>
        <input id={`${ids}-ticker`} className={`${field} num uppercase`} value={ticker} required maxLength={10}
          autoComplete="off" spellCheck={false} placeholder="MSFT" onChange={(e) => edit(setTicker)(e.target.value)} />
      </div>
      <div className="grid gap-2">
        <label htmlFor={`${ids}-company`} className="font-medium">Company</label>
        <input id={`${ids}-company`} className={field} value={company} required maxLength={255}
          placeholder="Microsoft Corporation" onChange={(e) => edit(setCompany)(e.target.value)} />
      </div>
      <div className={`grid gap-2 ${compact ? "" : "md:col-span-2"}`}>
        <label htmlFor={`${ids}-query`} className="font-medium">Question</label>
        <textarea id={`${ids}-query`} className={`${field} h-auto min-h-[88px] py-2 leading-5`} value={query} required
          maxLength={2000} placeholder="What do you want to know about this company?"
          onChange={(e) => edit(setQuery)(e.target.value)} />
      </div>
      <div className={`flex flex-wrap items-center gap-x-4 gap-y-3 ${compact ? "" : "md:col-span-2"}`}>
        <Button type="submit" variant="primary" disabled={submit.isPending}>
          {submit.isPending ? "Submitting…" : "Start research"}
        </Button>
        <p id={`${ids}-scope`} className="text-small text-muted">
          US-listed, non-financial companies that file a 10-K. Usually 2-4 minutes.
        </p>
      </div>
      {submit.isError && (
        <p role="alert" className={`text-[var(--pill-negative-ink)] ${compact ? "" : "md:col-span-2"}`}>{submit.error.message}</p>
      )}
      {!compact && (
        <div className="md:col-span-2">
          <p className="mb-2 text-small text-muted">Or start from an example</p>
          <div className="flex flex-wrap gap-2">
            {EXAMPLES.map((example) => (
              <button key={example.ticker} type="button"
                className="press h-8 rounded-full border border-control px-3 text-small text-soft hover:border-muted hover:text-ink"
                onClick={() => { setTicker(example.ticker); setCompany(example.company); setQuery(example.query); }}>
                <span className="num text-ink">{example.ticker}</span> · {example.query.split(",")[0]?.replace(/\?$/, "")}
              </button>
            ))}
          </div>
        </div>
      )}
    </form>
  );
}
