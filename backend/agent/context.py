"""Keep a researcher's context small without losing what it can cite (ADR 0009).

A tool loop re-sends every earlier tool result on every turn, so a researcher's input grows quadratically with its
tool calls; in live runs researchers were 85-90% of a job's input tokens. Clearing old results outright would also
erase the passage handles a researcher must cite. Instead, all but the latest few search/read results are shrunk to
each passage's handle, label and opening words: still citable, and read_passage brings any of them back in full.
Only what is sent to the model changes; the agent's own state, and the draft's evidence, are untouched.
"""
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

COMPACTABLE = {"search_filings", "read_passage"}
KEEP_LATEST = 2
GIST_CHARS = 160
MARKER = "(earlier result, shortened; read_passage restores any passage in full)"


def compact_result(content: str) -> str:
    """'[P:1a2b3c4d] 10-K … · mdna\\nLong passage…' becomes the header plus its first ~160 characters."""
    if MARKER in content:
        return content
    blocks = []
    for block in content.split("\n\n["):
        block = block if block.startswith("[") else f"[{block}"
        header, _, body = block.partition("\n")
        gist = " ".join(body.split())
        blocks.append(f"{header}\n{gist[:GIST_CHARS]}{'…' if len(gist) > GIST_CHARS else ''}")
    return MARKER + "\n" + "\n\n".join(blocks)


def compact_messages(messages: list, keep: int = KEEP_LATEST) -> list:
    positions = [i for i, m in enumerate(messages) if isinstance(m, ToolMessage) and m.name in COMPACTABLE]
    old = set(positions[:-keep] if keep else positions)
    out = []
    for i, message in enumerate(messages):
        if i in old and isinstance(message.content, str) and message.content.startswith("[P:"):
            message = message.model_copy(update={"content": compact_result(message.content)})
        out.append(message)
    return out


class CompactToolResults(AgentMiddleware):
    def wrap_model_call(self, request, handler):
        return handler(request.override(messages=compact_messages(list(request.messages))))
