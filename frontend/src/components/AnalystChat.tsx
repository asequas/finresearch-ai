import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";

import { type ChatCitation, type ChatMessage, useAskAnalyst, useChat } from "../api/client";
import { SECTION_LABEL, date } from "../lib/format";
import { ToolCallRow } from "./AgentActivity";
import { CloseIcon, ExternalIcon } from "./icons";
import { Bar, Button, ErrorBlock, Pill } from "./ui";

function Citation({ citation, number }: { citation: ChatCitation; number: number }) {
  const [open, setOpen] = useState(false);
  return (
    <li>
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
        className="press inline-flex h-6 items-center gap-1.5 rounded-full border border-control px-2.5 text-small hover:border-muted">
        <span className="num">[{number}]</span>
        <span className={`h-1.5 w-1.5 rounded-full ${citation.verified ? "bg-positive" : "bg-negative"}`} aria-hidden="true" />
        <span>{citation.verified ? "Quote verified" : "Not found in filing"}</span>
      </button>
      {open && (
        <figure className="mt-2 mb-1 rounded-[6px] bg-raised px-4 py-3">
          <blockquote className="text-read">“{citation.quote}”</blockquote>
          <figcaption className="mt-2 flex flex-wrap items-center justify-between gap-2 text-small text-muted">
            <span>
              {citation.form ?? "Filing"}{citation.period ? <>, period ended <span className="num">{date(citation.period)}</span></> : null}
              {citation.section ? `, ${SECTION_LABEL[citation.section] ?? citation.section}` : ""}
            </span>
            {citation.url && (
              <a href={citation.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:underline">
                Open filing <ExternalIcon />
              </a>
            )}
          </figcaption>
          {!citation.verified && (
            <p className="mt-2 text-small text-[var(--pill-negative-ink)]">
              These words weren't found in the cited passage, so treat this part of the answer as unsupported.
            </p>
          )}
        </figure>
      )}
    </li>
  );
}

function Answer({ message }: { message: ChatMessage }) {
  const verified = message.citations.filter((c) => c.verified).length;
  return (
    <div>
      <p className="text-read whitespace-pre-line">{message.content}</p>
      {message.citations.length > 0 ? (
        <>
          <p className="mt-3 mb-1.5 text-small text-muted">
            Sources: <span className="num">{verified}</span> of <span className="num">{message.citations.length}</span> quotes verified against the filing
          </p>
          <ol className="flex flex-col items-start gap-1.5">
            {message.citations.map((c, i) => <Citation key={i} citation={c} number={i + 1} />)}
          </ol>
        </>
      ) : (
        <p className="mt-2"><Pill tone="warning">No sources cited</Pill></p>
      )}
      {message.tool_steps.length > 0 && (
        <details className="mt-3 text-small">
          <summary className="cursor-pointer text-muted hover:text-ink">How this was answered ({message.tool_steps.length} steps)</summary>
          <ol className="mt-1 divide-y divide-rule">{message.tool_steps.map((step, i) => <ToolCallRow key={i} call={step} />)}</ol>
        </details>
      )}
    </div>
  );
}

/** "Ask the analyst": follow-up questions answered by a tool-using agent, every cited quote checked. */
export function AnalystChat({ jobId, open, onClose }: { jobId: string; open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const end = useRef<HTMLDivElement>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const thread = useChat(jobId, open);
  const ask = useAskAnalyst(jobId);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<string | null>(null);

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
      setTimeout(() => input.current?.focus(), 0);
    }
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const messages = thread.data?.messages ?? [];
  useEffect(() => end.current?.scrollIntoView({ block: "end" }), [messages.length, pending]);

  const send = (question: string) => {
    const text = question.trim();
    if (text.length < 3 || ask.isPending) return;
    setPending(text);
    setDraft("");
    ask.mutate(text, { onSettled: () => setPending(null), onError: () => setDraft(text) });
  };
  const submit = (e: FormEvent) => { e.preventDefault(); send(draft); };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(draft); }
  };
  const turnsLeft = thread.data?.turns_left ?? 0;

  return (
    <dialog ref={ref} className="sheet" onClose={onClose} onClick={(e) => e.target === ref.current && onClose()} aria-labelledby="chat-title">
      {open && (
        <div className="flex h-full flex-col">
          <header className="flex items-start justify-between gap-4 border-b border-rule px-6 py-4">
            <div>
              <h2 id="chat-title" className="text-card font-semibold">Ask the analyst</h2>
              <p className="text-small text-muted">
                An agent answers from this report's filings and metrics. Every quote it cites is checked against the filing.
              </p>
            </div>
            <button type="button" onClick={onClose} aria-label="Close" className="press -mr-2 flex h-9 w-9 flex-none items-center justify-center rounded-full text-muted hover:text-ink">
              <CloseIcon />
            </button>
          </header>

          <div className="flex-1 overflow-y-auto px-6 py-5" aria-live="polite">
            {thread.isError ? <ErrorBlock error={thread.error} onRetry={() => thread.refetch()} />
              : thread.isPending ? <div className="space-y-3"><Bar w="60%" h={14} /><Bar w="85%" h={14} /></div>
              : (
                <ol className="space-y-6">
                  {messages.length === 0 && !pending && (
                    <li className="text-soft">
                      Ask about anything in the filings: a segment, a risk, why a margin moved.
                      {thread.data && thread.data.suggestions.length > 0 && (
                        <div className="mt-4">
                          <p className="mb-2 text-small text-muted">Open questions from the report</p>
                          <ul className="flex flex-col items-start gap-2">
                            {thread.data.suggestions.map((s) => (
                              <li key={s}>
                                <button type="button" onClick={() => send(s)}
                                  className="press rounded-[6px] border border-control px-3 py-2 text-left hover:border-muted">{s}</button>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </li>
                  )}
                  {messages.map((m) => (
                    <li key={m.id}>
                      {m.role === "user"
                        ? <p className="ml-auto max-w-[85%] rounded-[6px] bg-raised px-4 py-2.5">{m.content}</p>
                        : <Answer message={m} />}
                    </li>
                  ))}
                  {pending && (
                    <>
                      <li><p className="ml-auto max-w-[85%] rounded-[6px] bg-raised px-4 py-2.5">{pending}</p></li>
                      <li className="flex items-center gap-2 text-muted">
                        <span className="live-dot h-2 w-2 rounded-full bg-accent" aria-hidden="true" />
                        Searching the filings and checking quotes…
                      </li>
                    </>
                  )}
                </ol>
              )}
            {ask.isError && <p role="alert" className="mt-4 text-[var(--pill-negative-ink)]">{ask.error.message}</p>}
            <div ref={end} />
          </div>

          <form onSubmit={submit} className="border-t border-rule px-6 py-4">
            <label htmlFor="chat-input" className="sr-only">Your question</label>
            <textarea id="chat-input" ref={input} value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={onKey}
              rows={2} maxLength={500} disabled={turnsLeft === 0 && !!thread.data}
              placeholder={turnsLeft === 0 && thread.data ? "This report has used its questions." : "Ask a follow-up question"}
              className="w-full resize-none rounded-[6px] border border-control bg-transparent px-3 py-2 text-read placeholder:text-muted focus:border-muted focus:outline-none" />
            <div className="mt-2 flex items-center justify-between gap-3">
              <span className="text-small text-muted"><span className="num">{turnsLeft}</span> questions left. Enter sends, Shift+Enter adds a line.</span>
              <Button type="submit" variant="primary" disabled={ask.isPending || draft.trim().length < 3}>
                {ask.isPending ? "Answering…" : "Ask"}
              </Button>
            </div>
          </form>
        </div>
      )}
    </dialog>
  );
}
