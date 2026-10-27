import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Link } from "react-router-dom";

import type { JobStatus } from "../api/client";
import { STATUS_LABEL, VERIFICATION_LABEL } from "../lib/format";

export function Panel({ title, aside, children, className = "", id, as: Tag = "section" }: {
  title?: ReactNode; aside?: ReactNode; children: ReactNode; className?: string; id?: string; as?: "section" | "div";
}) {
  return (
    <Tag className={`panel ${className}`} aria-labelledby={title && id ? `${id}-title` : undefined} id={id}>
      {title !== undefined && (
        <header className="flex min-h-12 items-center justify-between gap-4 px-6 pt-5 pb-3">
          <h2 id={id ? `${id}-title` : undefined} className="text-card font-semibold">{title}</h2>
          {aside && <div className="flex items-center gap-3 text-small text-muted">{aside}</div>}
        </header>
      )}
      {children}
    </Tag>
  );
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" };

const BUTTON = {
  base: "press inline-flex h-[34px] flex-none items-center justify-center gap-2 rounded-full px-4 text-body font-medium whitespace-nowrap disabled:cursor-not-allowed disabled:opacity-60",
  primary: "bg-primary text-primary-ink hover:opacity-90",
  secondary: "border border-control text-ink hover:border-muted",
  ghost: "text-soft hover:text-ink",
};

export function Button({ variant = "secondary", className = "", ...props }: ButtonProps) {
  return <button type="button" className={`${BUTTON.base} ${BUTTON[variant]} ${className}`} {...props} />;
}

export function ButtonLink({ to, variant = "secondary", children, className = "" }: {
  to: string; variant?: "primary" | "secondary" | "ghost"; children: ReactNode; className?: string;
}) {
  return <Link to={to} className={`${BUTTON.base} ${BUTTON[variant]} ${className}`}>{children}</Link>;
}

const PILL = {
  positive: "bg-[var(--pill-positive-bg)] text-[var(--pill-positive-ink)]",
  negative: "bg-[var(--pill-negative-bg)] text-[var(--pill-negative-ink)]",
  warning: "bg-[var(--pill-warning-bg)] text-[var(--pill-warning-ink)]",
  neutral: "bg-[var(--pill-neutral-bg)] text-[var(--pill-neutral-ink)]",
};

export function Pill({ tone, children }: { tone: keyof typeof PILL; children: ReactNode }) {
  return (
    <span className={`inline-flex h-5 flex-none items-center gap-1.5 rounded-full px-2 text-small font-medium whitespace-nowrap ${PILL[tone]}`}>
      {children}
    </span>
  );
}

const STATUS_TONE: Record<JobStatus, keyof typeof PILL> = {
  queued: "neutral", running: "neutral", completed: "positive", failed: "negative", cancelled: "neutral",
};

export function StatusPill({ status }: { status: JobStatus }) {
  return (
    <Pill tone={STATUS_TONE[status]}>
      {status === "running" && <span className="live-dot h-1.5 w-1.5 rounded-full bg-accent" aria-hidden="true" />}
      {STATUS_LABEL[status]}
    </Pill>
  );
}

const VERIFY_TONE: Record<string, keyof typeof PILL> = {
  supported: "positive", partially_supported: "warning", unsupported: "negative", not_verified: "neutral",
};

export function VerificationPill({ status }: { status: string }) {
  return <Pill tone={VERIFY_TONE[status] ?? "neutral"}>{VERIFICATION_LABEL[status] ?? status}</Pill>;
}

export function Empty({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mx-6 mb-6 flex min-h-[38px] flex-wrap items-center justify-between gap-3 rounded-[6px] border border-dashed border-control px-4 py-3 text-soft">
      <span>{children}</span>
      {action}
    </div>
  );
}

export function ErrorBlock({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <div role="alert" className="mx-6 mb-6 flex flex-wrap items-center gap-3 text-soft">
      <span className="h-2 w-2 flex-none rounded-full bg-negative" aria-hidden="true" />
      <span className="flex-1">{message}</span>
      {onRetry && <button type="button" className="press font-medium text-ink underline-offset-4 hover:underline" onClick={onRetry}>Retry</button>}
    </div>
  );
}

export function Notice({ children }: { children: ReactNode }) {
  return (
    <div role="status" className="rounded-[6px] bg-[var(--pill-warning-bg)] px-4 py-3 text-[var(--pill-warning-ink)]">{children}</div>
  );
}

/** Flat placeholder bar at the real size of the value it stands in for. */
export function Bar({ w = "60%", h = 12 }: { w?: string | number; h?: number }) {
  return <span className="inline-block rounded-[3px] bg-raised align-middle" style={{ width: w, height: h }} aria-hidden="true" />;
}

export function PageTitle({ title, sub, actions }: { title: ReactNode; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-[22px] leading-[28px] font-semibold md:text-title">{title}</h1>
        {sub && <p className="mt-1 max-w-[72ch] text-read text-soft">{sub}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-3">{actions}</div>}
    </div>
  );
}

export function Kv({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1.5">
      <dt className="text-muted">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}
