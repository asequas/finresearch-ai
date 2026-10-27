import { type ReactNode, useEffect, useState } from "react";

import { useMeta } from "../api/client";
import { CheckIcon, CrossIcon } from "../components/icons";
import { Bar, ErrorBlock, Kv, PageTitle, Panel } from "../components/ui";

type Theme = "system" | "dark" | "light";

function readTheme(): Theme {
  try {
    const stored = localStorage.getItem("finresearch.theme");
    return stored === "dark" || stored === "light" ? stored : "system";
  } catch {
    return "system";
  }
}

function applyTheme(theme: Theme) {
  const resolved = theme === "system" ? (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark") : theme;
  document.documentElement.dataset.theme = resolved;
  try {
    if (theme === "system") localStorage.removeItem("finresearch.theme");
    else localStorage.setItem("finresearch.theme", theme);
  } catch {
    /* storage unavailable: the choice lasts for this visit */
  }
}

function Check({ ok, children, fix }: { ok: boolean | undefined; children: string; fix: string }) {
  return (
    <li className="grid grid-cols-[20px_1fr] gap-x-3 py-3">
      <span className={`mt-0.5 ${ok ? "text-positive" : "text-warning"}`} aria-hidden="true">{ok ? <CheckIcon /> : <CrossIcon />}</span>
      <span>
        {children} <span className="sr-only">{ok ? "configured" : "not configured"}</span>
        <span className="block text-small text-muted">{ok ? "Configured in the backend's .env." : fix}</span>
      </span>
    </li>
  );
}

export function Settings() {
  const meta = useMeta();
  const [theme, setTheme] = useState<Theme>(readTheme);
  useEffect(() => applyTheme(theme), [theme]);

  return (
    <>
      <PageTitle title="Settings" sub="Appearance for this browser, and the backend's research configuration." />
      <div className="grid grid-cols-1 gap-8">
        <Area title="Appearance" description="Dark is the default. System follows your operating system. Saved in this browser only.">
          <Panel>
            <div className="px-6 py-5">
              <div role="radiogroup" aria-label="Theme" className="flex gap-5 border-b border-rule">
                {(["system", "dark", "light"] as const).map((value) => (
                  <button key={value} type="button" role="radio" aria-checked={theme === value} aria-pressed={theme === value}
                    onClick={() => setTheme(value)}
                    className={`sel-line press h-9 capitalize ${theme === value ? "text-ink" : "text-muted hover:text-soft"}`}>
                    {value}
                  </button>
                ))}
              </div>
            </div>
          </Panel>
        </Area>

        <Area title="Research setup" description="Both keys live in the backend's .env file and are never sent to this browser. Restart the worker after changing them.">
          <Panel>
            {meta.isError ? <div className="pt-6"><ErrorBlock error={meta.error} onRetry={() => meta.refetch()} /></div> : (
              <ul className="divide-y divide-rule px-6 py-2">
                {meta.isPending ? <li className="py-3"><Bar w="70%" h={14} /></li> : (
                  <>
                    <Check ok={meta.data.gemini_configured} fix="Add GEMINI_API_KEY to .env (free key from Google AI Studio).">Gemini API key</Check>
                    <Check ok={meta.data.sec_configured} fix="Add SEC_USER_AGENT to .env: an app name and your contact email. SEC EDGAR rejects anonymous requests.">
                      SEC EDGAR user agent
                    </Check>
                  </>
                )}
              </ul>
            )}
          </Panel>
        </Area>

        <Area title="Models and pipeline" description="A fast model for routine steps and fact-checking, a stronger one for drafting and the final report. All arithmetic is done in code.">
          <Panel>
            <dl className="px-6 py-4">
              <Kv label="Pipeline">{meta.data?.pipeline === "stub" ? "Stub (no external calls)" : "SEC EDGAR + Gemini"}</Kv>
              <Kv label="Routine steps"><span className="num">{meta.data?.models.fast ?? "—"}</span></Kv>
              <Kv label="Drafting and synthesis"><span className="num">{meta.data?.models.strong ?? "—"}</span></Kv>
              <Kv label="Embeddings"><span className="num">{meta.data?.models.embedding ?? "—"}</span> <span className="text-muted">· 768-d</span></Kv>
            </dl>
          </Panel>
        </Area>

        <Area title="Worker and queue" description={<>Start a worker with <code className="num text-soft">python -m backend.worker.main</code>. Run several for parallel jobs; each job is claimed by exactly one.</>}>
          <Panel>
            <dl className="px-6 py-4">
              <Kv label="Lease"><span className="num">{meta.data ? `${meta.data.lease_seconds}s` : "—"}</span></Kv>
              <Kv label="Attempts per job"><span className="num">{meta.data?.max_attempts ?? "—"}</span></Kv>
              <Kv label="Queued now"><span className="num">{meta.data?.queue.queued ?? "—"}</span></Kv>
              <Kv label="Running now"><span className="num">{meta.data?.queue.running ?? "—"}</span></Kv>
            </dl>
          </Panel>
        </Area>
      </div>
    </>
  );
}

function Area({ title, description, children }: { title: string; description: ReactNode; children: ReactNode }) {
  return (
    <section className="grid grid-cols-1 gap-3 md:grid-cols-[280px_minmax(0,1fr)] md:gap-8" aria-label={title}>
      <div>
        <h2 className="text-card font-semibold">{title}</h2>
        <p className="mt-1 text-muted">{description}</p>
      </div>
      {children}
    </section>
  );
}
