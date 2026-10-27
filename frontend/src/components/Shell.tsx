import type { ComponentType, ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";

import { useMeta } from "../api/client";
import { CompanyIcon, Mark, OverviewIcon, ReportIcon, ResearchIcon, SettingsIcon } from "./icons";

const NAV: { to: string; label: string; icon: ComponentType<{ size?: number }>; end?: boolean }[] = [
  { to: "/", label: "Overview", icon: OverviewIcon, end: true },
  { to: "/research", label: "Research", icon: ResearchIcon },
  { to: "/reports", label: "Reports", icon: ReportIcon },
  { to: "/companies", label: "Companies", icon: CompanyIcon },
];

function RailLink({ to, label, icon: Icon, end }: (typeof NAV)[number]) {
  return (
    <NavLink
      to={to}
      end={end}
      aria-label={label}
      title={label}
      className={({ isActive }) =>
        `press group relative flex h-11 w-full items-center justify-center ${isActive ? "text-ink" : "text-muted hover:text-soft"}`
      }
    >
      {({ isActive }) => (
        <>
          <Icon size={18} />
          {/* The style's one move: the selection is a 1px accent line on the rail's edge. */}
          {isActive && <span className="absolute top-2.5 right-0 bottom-2.5 w-px bg-accent" aria-hidden="true" />}
          <span className="pointer-events-none absolute left-full z-20 ml-2 rounded-[4px] bg-raised px-2 py-1 text-small whitespace-nowrap text-ink opacity-0 shadow-[var(--shadow)] group-hover:opacity-100 group-focus-visible:opacity-100">
            {label}
          </span>
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

  return (
    <div className="min-h-dvh">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-16 focus:z-50 focus:rounded focus:bg-surface focus:px-3 focus:py-2">
        Skip to content
      </a>
      <nav aria-label="Primary" className="no-print fixed inset-y-0 left-0 z-30 hidden w-14 flex-col items-center border-r border-border bg-ground md:flex">
        <NavLink to="/" aria-label="FinResearch home" className="flex h-16 w-full items-center justify-center">
          <Mark size={24} />
        </NavLink>
        <div className="mx-auto mb-3 h-px w-5 bg-border" aria-hidden="true" />
        <div className="flex w-full flex-col">
          {NAV.map((item) => <RailLink key={item.to} {...item} />)}
        </div>
        <div className="mt-auto mb-3 w-full">
          <div className="relative">
            <RailLink to="/settings" label={setupNeeded ? "Settings (setup needed)" : "Settings"} icon={SettingsIcon} />
            {setupNeeded && <span className="pointer-events-none absolute top-2.5 right-3.5 h-1.5 w-1.5 rounded-full bg-warning" aria-hidden="true" />}
          </div>
        </div>
      </nav>

      <header className="no-print sticky top-0 z-30 flex h-12 items-center justify-between border-b border-border bg-ground px-4 md:hidden">
        <NavLink to="/" className="flex items-center gap-2 font-semibold">
          <Mark size={22} /> FinResearch
        </NavLink>
        <NavLink to="/settings" aria-label="Settings" className="relative flex h-11 w-11 items-center justify-center text-muted">
          <SettingsIcon size={18} />
          {setupNeeded && <span className="absolute top-3 right-3 h-1.5 w-1.5 rounded-full bg-warning" aria-hidden="true" />}
        </NavLink>
      </header>

      <main id="main" key={pathname} className="px-4 pt-5 pb-24 md:ml-14 md:px-8 md:pt-8 md:pb-12">
        <div className="mx-auto max-w-[1360px]">{children}</div>
      </main>

      <nav aria-label="Primary" className="no-print fixed inset-x-0 bottom-0 z-30 flex border-t border-border bg-ground md:hidden">
        {NAV.map((item) => <TabLink key={item.to} {...item} />)}
      </nav>
    </div>
  );
}
