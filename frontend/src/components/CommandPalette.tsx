import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { useCompanies, useJobs } from "../api/client";
import { STATUS_LABEL, relative } from "../lib/format";
import { SearchIcon } from "./icons";

type Item = { id: string; group: string; title: string; detail: string; to: string; keywords: string };

const TICKER = /^[A-Za-z][A-Za-z0-9.\-]{0,9}$/;

/** ⌘K: jump to a company, report or job by ticker or name, or start research on a new ticker. */
export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const companies = useCompanies();
  const jobs = useJobs({ limit: 50 });

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      setQuery("");
      setActive(0);
      dialog.showModal();
      input.current?.focus();
    }
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const items = useMemo<Item[]>(() => {
    const list: Item[] = [];
    for (const c of companies.data ?? []) {
      list.push({
        id: `c-${c.company.id}`, group: "Companies", title: `${c.company.ticker}  ${c.display_name}`,
        detail: c.company.sic_description ?? "", to: `/companies/${c.company.ticker}`,
        keywords: `${c.company.ticker} ${c.display_name} ${c.company.name}`.toLowerCase(),
      });
    }
    for (const j of jobs.data?.pages.flatMap((p) => p.items) ?? []) {
      list.push({
        id: `j-${j.id}`, group: j.has_report ? "Reports" : "Research jobs", title: `${j.ticker}  ${j.query}`,
        detail: j.has_report ? `Report, ${relative(j.completed_at)}` : `${STATUS_LABEL[j.status]}, ${relative(j.updated_at)}`,
        to: j.has_report ? `/reports/${j.id}` : `/research/${j.id}`,
        keywords: `${j.ticker} ${j.company} ${j.query}`.toLowerCase(),
      });
    }
    return list;
  }, [companies.data, jobs.data]);

  const q = query.trim().toLowerCase();
  const matches = (q ? items.filter((i) => q.split(/\s+/).every((word) => i.keywords.includes(word))) : items).slice(0, 12);
  const known = items.some((i) => i.group === "Companies" && i.keywords.startsWith(q + " "));
  const results: Item[] = [
    ...matches,
    ...(q && TICKER.test(q) && !known
      ? [{ id: "new", group: "Actions", title: `Research ${q.toUpperCase()}`, detail: "Start a new research job for this ticker", to: `/research?new=${q.toUpperCase()}`, keywords: q }]
      : []),
  ];

  function go(item: Item | undefined) {
    if (!item) return;
    onClose();
    navigate(item.to);
  }

  let lastGroup = "";
  return (
    <dialog ref={ref} onClose={onClose} onClick={(e) => e.target === ref.current && onClose()}
      aria-label="Search" className="palette">
      <div className="flex items-center gap-3 border-b border-rule px-4 focus-within:shadow-[inset_0_-1px_0_var(--accent)]">
        <SearchIcon className="flex-none text-muted" />
        <input ref={input} value={query} aria-label="Search companies, reports and jobs"
          aria-controls="palette-results" aria-activedescendant={results[active]?.id}
          placeholder="Search companies, reports and jobs, or type a ticker…" autoComplete="off" spellCheck={false}
          className="h-12 w-full bg-transparent text-read text-ink placeholder:text-muted focus-visible:outline-none"
          onChange={(e) => { setQuery(e.target.value); setActive(0); }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, results.length - 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
            if (e.key === "Enter") { e.preventDefault(); go(results[active]); }
          }} />
        <kbd className="hidden flex-none rounded-[4px] bg-raised px-1.5 py-0.5 text-small text-muted md:inline">Esc</kbd>
      </div>
      <ul id="palette-results" role="listbox" className="max-h-[55dvh] overflow-y-auto py-2">
        {results.length === 0 && <li className="px-4 py-6 text-center text-muted">Nothing matches “{query}”.</li>}
        {results.map((item, index) => {
          const header = item.group !== lastGroup ? item.group : null;
          lastGroup = item.group;
          return (
            <li key={item.id} role="presentation">
              {header && <p className="px-4 pt-2 pb-1 text-small text-muted">{header}</p>}
              <button id={item.id} type="button" role="option" aria-selected={index === active}
                onMouseEnter={() => setActive(index)} onClick={() => go(item)}
                className={`flex w-full items-baseline justify-between gap-4 px-4 py-2 text-left ${index === active ? "bg-raised" : ""}`}>
                <span className="min-w-0 truncate" translate="no">{item.title}</span>
                <span className="flex-none text-small text-muted">{item.detail}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </dialog>
  );
}
