import { useEffect, useState } from "react";

/** Sticky in-page index for a long report; the section in view carries the 1px accent line. */
export function SectionIndex({ sections }: { sections: { id: string; label: string }[] }) {
  const [active, setActive] = useState(sections[0]?.id);
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: "-64px 0px -60% 0px" },
    );
    for (const { id } of sections) {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [sections]);

  return (
    <nav aria-label="Report sections" className="no-print sticky top-12 z-20 -mx-4 mb-6 border-b border-rule bg-ground px-4 md:-mx-8 md:px-8 lg:top-0">
      {/* Phones get a menu instead of a strip that scrolls sideways. */}
      <label className="flex h-11 items-center gap-3 md:hidden">
        <span className="text-muted">Jump to</span>
        <select value={active} onChange={(e) => document.getElementById(e.target.value)?.scrollIntoView({ behavior: "smooth" })}
          className="h-8 flex-1 rounded-[6px] border border-control bg-surface px-2 text-ink">
          {sections.map(({ id, label }) => <option key={id} value={id}>{label}</option>)}
        </select>
      </label>
      <ul className="hidden gap-6 overflow-x-auto pr-8 md:flex">
        {sections.map(({ id, label }) => (
          <li key={id}>
            <a href={`#${id}`} data-active={active === id} aria-current={active === id ? "location" : undefined}
              className={`sel-line press flex h-11 items-center whitespace-nowrap ${active === id ? "text-ink" : "text-muted hover:text-soft"}`}>
              {label}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
