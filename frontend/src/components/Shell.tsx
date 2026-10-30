import { type ComponentType, type ReactNode, useEffect, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";

import { useMeta } from "../api/client";
import { CommandPalette } from "./CommandPalette";
import { CompanyIcon, Mark, OverviewIcon, ReportIcon, ResearchIcon, SearchIcon, SettingsIcon } from "./icons";

const NAV: { to: string; label: string; icon: ComponentType<{ size?: number }>; end?: boolean }[] = [
  { to: "/", label: "Overview", icon: OverviewIcon, end: true },
  { to: "/research", label: "Research", icon: ResearchIcon },
  { to: "/reports", label: "Reports", icon: ReportIcon },
  { to: "/companies", label: "Companies", icon: CompanyIcon },
];

const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform);

function SideLink({ to, label, icon: Icon, end, badge }: (typeof NAV)[number] & { badge?: ReactNode }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `press flex h-9 items-center gap-3 rounded-[6px] px-3 ${isActive ? "bg-raised text-ink" : "text-muted hover:bg-raised/60 hover:text-soft"}`
      }
    >
      {({ isActive }) => (
        <>
          <Icon size={16} />
          {/* The style's one move: the selection is a 1px accent line under the label, as wide as it. */}
          <span className="sel-line" data-active={isActive}>{label}</span>
          {badge}
        </>
      )}
    </NavLink>
  );
}

function TabLink({ to, label, icon: Icon, end }: (typeof NAV)[number]) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) =>
        `press relative flex min-h-[52px] flex-1 flex-col items-center justify-center gap-1 text-[11px] ${isActive ? "text-ink" : "text-muted"}`
      }
    >
      {({ isActive }) => (
        <>
          {isActive && <span className="absolute top-0 left-1/4 right-1/4 h-px bg-accent" aria-hidden="true" />}
          <Icon size={18} />
          {label}
        </>
      )}
    </NavLink>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const meta = useMeta();
  const setupNeeded = meta.data && (!meta.data.gemini_configured || !meta.data.sec_configured);
  const running = meta.data?.queue.running ?? 0;
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const typing = event.target instanceof HTMLElement && /^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName);
      if ((event.key === "k" && (event.metaKey || event.ctrlKey)) || (event.key === "/" && !typing)) {
        event.preventDefault();
        setPaletteOpen(true);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="min-h-dvh">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-4 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2">
        Skip to content
      </a>

      <aside className="no-print fixed inset-y-0 left-0 z-30 hidden w-[232px] flex-col border-r border-border bg-ground px-3 pb-4 lg:flex">
        <NavLink to="/" className="flex h-16 items-center gap-2.5 px-3" aria-label="FinResearch, overview">
          <Mark size={22} />
          <span className="text-card font-semibold tracking-[-0.01em]">FinResearch</span>
        </NavLink>

        <button type="button" onClick={() => setPaletteOpen(true)}
          className="press mb-5 flex h-9 items-center gap-2.5 rounded-[6px] border border-border px-3 text-muted hover:border-control hover:text-soft">
          <SearchIcon size={15} />
          <span className="flex-1 text-left">Search</span>
          <kbd className="text-small">{isMac ? "⌘K" : "Ctrl K"}</kbd>
        </button>

        <nav aria-label="Primary" className="grid gap-0.5">
          {NAV.map((item) => (
            <SideLink key={item.to} {...item}
              badge={item.to === "/research" && running > 0
                ? <span className="num ml-auto text-small text-accent" aria-label={`${running} running`}>{running}</span>
                : undefined} />
          ))}
        </nav>

        <div className="mt-auto grid gap-0.5">
          <SideLink to="/settings" label="Settings" icon={SettingsIcon}
            badge={setupNeeded ? <span className="ml-auto h-1.5 w-1.5 rounded-full bg-warning" aria-label="Setup needed" /> : undefined} />
          <div className="mt-3 border-t border-rule px-3 pt-3">
            <p className="text-small text-soft">Personal workspace</p>
            <p className="truncate text-small text-muted">dev@finresearch.local</p>
          </div>
        </div>
      </aside>

      <header className="no-print sticky top-0 z-30 flex h-12 items-center justify-between border-b border-border bg-ground px-4 lg:hidden">
        <NavLink to="/" className="flex items-center gap-2 font-semibold">
          <Mark size={22} /> FinResearch
        </NavLink>
        <div className="flex">
          <button type="button" aria-label="Search" onClick={() => setPaletteOpen(true)} className="flex h-11 w-11 items-center justify-center text-muted">
            <SearchIcon size={18} />
          </button>
          <NavLink to="/settings" aria-label={setupNeeded ? "Settings, setup needed" : "Settings"} className="relative flex h-11 w-11 items-center justify-center text-muted">
            <SettingsIcon size={18} />
            {setupNeeded && <span className="absolute top-3 right-3 h-1.5 w-1.5 rounded-full bg-warning" aria-hidden="true" />}
          </NavLink>
        </div>
      </header>

      <main id="main" key={pathname} className="px-4 pt-5 pb-24 md:px-8 md:pt-8 lg:ml-[232px] lg:pb-12">
        <div className="mx-auto max-w-[1320px]">{children}</div>
      </main>

      <nav aria-label="Primary" className="no-print fixed inset-x-0 bottom-0 z-30 flex border-t border-border bg-ground pb-[env(safe-area-inset-bottom)] lg:hidden">
        {NAV.map((item) => <TabLink key={item.to} {...item} />)}
      </nav>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
