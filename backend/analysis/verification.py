"""Deterministic verification checks (ADR 0006): literal quotes and numeric consistency."""
import re
import unicodedata
from difflib import SequenceMatcher
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_QUOTE_CHARS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "\xa0": " "})


def normalise_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).translate(_QUOTE_CHARS).lower()
    # Table cells split "$" from its number ("$ 39,834" vs "39,834"); the symbol carries no evidence.
    value = re.sub(r"\$\s*", "", value)
    return re.sub(r"\s+", " ", value).strip()


_NUMBER_TOKEN = re.compile(r"^\(?-?[\d,]+(\.\d+)?%?\)?$")


def _is_data_row(text: str) -> bool:
    """A table row: a label and at least two figures, e.g. "AWS 11,434 17,773 33,141"."""
    tokens = text.split()
    numbers = sum(bool(_NUMBER_TOKEN.match(t)) for t in tokens)
    return numbers >= 2 and any(re.search(r"[a-z]", t) for t in tokens)


_HEADING_ONLY = re.compile(r"^(part\s+[ivx]+[,.]?\s*)?item\s*\d{1,2}[a-c]?\b[\s.:\-–—]*[a-z'’ ,&]{0,80}$")


def quote_in_source(quote: str, source: str, min_chars: int = 20, min_words: int = 6) -> bool:
    """Every ellipsis-separated part of the quote must appear verbatim (whitespace/quote-normalised).

    A section heading ("Item 1A. Risk Factors") is verbatim but supports nothing, and fragments of
    a few words prove little, so both are rejected.
    """
    haystack = normalise_text(source)
    parts = [normalise_text(p).strip(" .,;:") for p in re.split(r"\.\.\.|…|\[\.\.\.\]", quote)]
    parts = [p for p in parts if p]
    joined = " ".join(parts)
    if not parts or _HEADING_ONLY.match(joined):
        return False
    # Prose needs enough words to support anything; a table row is evidence however short it is.
    if not _is_data_row(joined) and (sum(len(p) for p in parts) < min_chars or sum(len(p.split()) for p in parts) < min_words):
        return False
    return all(part in haystack for part in parts)


_SENTENCE = re.compile(r"(?<=[.!?;])\s+|\n+")


def snap_quote(quote: str, source: str, min_similarity: float = 0.88) -> str | None:
    """The filing's own sentence that a near-verbatim quote paraphrases, or None.

    Smaller models reword quotes ("increased 27%" for "grew 27%"). If one sentence (or two adjacent ones)
    of the cited chunk is almost identical, the evidence becomes that exact text; the fact-check then
    judges what the filing really says. Anything less similar stays a failed quote.
    """
    target = normalise_text(quote)
    if len(target.split()) < 6:
        return None
    sentences = [s.strip() for s in _SENTENCE.split(source) if len(s.split()) >= 4]
    candidates = sentences + [f"{a} {b}" for a, b in zip(sentences, sentences[1:])]
    best, best_ratio = None, 0.0
    for candidate in candidates:
        normalised = normalise_text(candidate)
        if not 0.6 <= len(normalised) / max(len(target), 1) <= 1.6:
            continue
        ratio = SequenceMatcher(None, target, normalised, autojunk=False).ratio()
        if ratio > best_ratio:
            best, best_ratio = candidate, ratio
    return best if best is not None and best_ratio >= min_similarity and quote_in_source(best, source) else None


@dataclass(frozen=True)
class NumberMention:
    raw: str
    value: Decimal
    kind: str  # "percent" | "usd" | "times"


_SCALE = {"k": Decimal("1e3"), "thousand": Decimal("1e3"), "m": Decimal("1e6"), "million": Decimal("1e6"),
          "b": Decimal("1e9"), "billion": Decimal("1e9"), "bn": Decimal("1e9"), "t": Decimal("1e12"), "trillion": Decimal("1e12")}
_NUMBER = re.compile(
    r"(?P<neg>-|−)?\s*(?P<usd>\$)?\s*(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*"
    r"(?P<unit>%|percent\b|x\b|times\b|trillion\b|billion\b|million\b|thousand\b|bn\b|[kmbt]\b)?",
    re.IGNORECASE,
)


def extract_numbers(text: str) -> list[NumberMention]:
    mentions = []
    for match in _NUMBER.finditer(text):
        unit = (match.group("unit") or "").lower()
        try:
            number = Decimal(match.group("num").replace(",", ""))
        except InvalidOperation:
            continue
        if match.group("neg"):
            number = -number
        if unit in ("%", "percent"):
            mentions.append(NumberMention(match.group(0).strip(), number / 100, "percent"))
        elif unit in ("x", "times"):
            mentions.append(NumberMention(match.group(0).strip(), number, "times"))
        elif match.group("usd"):
            mentions.append(NumberMention(match.group(0).strip(), number * _SCALE.get(unit, Decimal(1)), "usd"))
        # Bare numbers (years, counts) are not checked.
    return mentions


def matches_metric(mention: NumberMention, value: Decimal, unit: str) -> bool:
    if mention.kind == "percent" and unit == "ratio":
        return abs(abs(mention.value) - abs(value)) <= Decimal("0.0015")  # within 0.15 percentage points
    if mention.kind == "times" and unit == "times":
        return abs(mention.value - value) <= max(Decimal("0.02"), abs(value) * Decimal("0.01"))
    if mention.kind == "usd" and unit == "USD":
        tolerance = max(abs(value) * Decimal("0.01"), Decimal("0.5"))
        return abs(abs(mention.value) - abs(value)) <= tolerance
    return False


def unmatched_numbers(text: str, metrics: list[tuple[Decimal, str]]) -> list[str]:
    """Numbers in a calculation claim that don't correspond to any referenced metric."""
    return [
        mention.raw
        for mention in extract_numbers(text)
        if not any(matches_metric(mention, value, unit) for value, unit in metrics)
    ]
