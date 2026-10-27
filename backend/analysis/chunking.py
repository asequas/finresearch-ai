"""Paragraph-aware chunking with overlap, keeping section labels for citations."""
import re
from dataclasses import dataclass

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\"'])")


@dataclass(frozen=True)
class Chunk:
    section: str
    index: int
    content: str


def _pieces(paragraph: str, target: int) -> list[str]:
    """Split an over-long paragraph on sentence boundaries (hard-split as a last resort)."""
    if len(paragraph) <= target:
        return [paragraph]
    pieces, current = [], ""
    for sentence in _SENTENCE_END.split(paragraph):
        while len(sentence) > target:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:target])
            sentence = sentence[target:]
        if current and len(current) + 1 + len(sentence) > target:
            pieces.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        pieces.append(current)
    return pieces


def chunk_text(section: str, text: str, *, target_chars: int = 1400, overlap_chars: int = 200, start_index: int = 0) -> list[Chunk]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if len(p.strip()) > 1]
    pieces = [piece for paragraph in paragraphs for piece in _pieces(paragraph, target_chars)]

    chunks: list[Chunk] = []
    current: list[str] = []
    length = 0
    for piece in pieces:
        if current and length + len(piece) + 1 > target_chars:
            chunks.append(Chunk(section, start_index + len(chunks), "\n".join(current)))
            # Carry the tail forward so facts spanning a boundary appear whole in one chunk.
            tail, tail_length = [], 0
            for previous in reversed(current):
                if tail_length + len(previous) > overlap_chars:
                    break
                tail.insert(0, previous)
                tail_length += len(previous) + 1
            current, length = tail, tail_length
        current.append(piece)
        length += len(piece) + 1
    if current:
        chunks.append(Chunk(section, start_index + len(chunks), "\n".join(current)))
    return chunks
