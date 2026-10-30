"""Deterministic verification checks (ADR 0006): literal quotes and numeric consistency."""
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_QUOTE_CHARS = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "\xa0": " "})


def normalise_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).translate(_QUOTE_CHARS).lower()
    return re.sub(r"\s+", " ", value).strip()


_HEADING_ONLY = re.compile(r"^(part\s+[ivx]+[,.]?\s*)?item\s*\d{1,2}[a-c]?\b[\s.:\-–—]*[a-z'’ ,&]{0,80}$")


def quote_in_source(quote: str, source: str, min_chars: int = 20, min_words: int = 6) -> bool:
    """Every ellipsis-separated part of the quote must appear verbatim (whitespace/quote-normalised).

    A section heading ("Item 1A. Risk Factors") is verbatim but supports nothing, and fragments of
    a few words prove little, so both are rejected.
    """
    haystack = normalise_text(source)
    parts = [normalise_text(p).strip(" .,;:") for p in re.split(r"\.\.\.|…|\[\.\.\.\]", quote)]
    parts = [p for p in parts if p]
    if not parts or sum(len(p) for p in parts) < min_chars:
        return False
    if sum(len(p.split()) for p in parts) < min_words or _HEADING_ONLY.match(" ".join(parts)):
        return False
    return all(part in haystack for part in parts)


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
