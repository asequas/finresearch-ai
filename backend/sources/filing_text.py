"""Turn a 10-K / 10-Q HTML document into clean text and named sections (stdlib only)."""
import re
from dataclasses import dataclass
from html.parser import HTMLParser

_BLOCK_TAGS = {
    "p", "div", "br", "tr", "li", "ul", "ol", "table", "section", "article",
    "h1", "h2", "h3", "h4", "h5", "h6", "hr", "title",
}
_SKIP_TAGS = {"script", "style", "head", "ix:header"}


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0
        self.hidden_depth = 0
        self._stack: list[bool] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            self.skip_depth += 1
        style = (dict(attrs).get("style") or "").replace(" ", "").lower()
        hidden = "display:none" in style
        if tag not in ("br", "hr", "img", "meta", "link", "input"):
            self._stack.append(hidden)
            if hidden:
                self.hidden_depth += 1
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append(" ")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in _SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        if tag not in ("br", "hr", "img", "meta", "link", "input") and self._stack:
            if self._stack.pop():
                self.hidden_depth -= 1
        if tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip_depth and not self.hidden_depth:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    text = "".join(parser.parts).replace("\xa0", " ")
    lines = [re.sub(r"[ \t\r\f\v]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# 10-K items we index, in document order. Pattern matches a heading at line start.
TEN_K_SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("business", "Business", r"item\s*1\s*[.:\-–—]?\s*business"),
    ("risk_factors", "Risk Factors", r"item\s*1a\s*[.:\-–—]?\s*risk\s+factors"),
    ("mdna", "Management's Discussion and Analysis", r"item\s*7\s*[.:\-–—]?\s*management.{0,3}s\s+discussion"),
    ("market_risk", "Quantitative and Qualitative Disclosures About Market Risk", r"item\s*7a\s*[.:\-–—]?\s*quantitative"),
)
TEN_Q_SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("mdna", "Management's Discussion and Analysis", r"item\s*2\s*[.:\-–—]?\s*management.{0,3}s\s+discussion"),
    ("market_risk", "Quantitative and Qualitative Disclosures About Market Risk", r"item\s*3\s*[.:\-–—]?\s*quantitative"),
    ("risk_factors", "Risk Factors", r"item\s*1a\s*[.:\-–—]?\s*risk\s+factors"),
)
_ANY_ITEM = re.compile(r"^\s*item\s*(\d{1,2})([a-c]?)\b", re.IGNORECASE | re.MULTILINE)


def _item_id(match: re.Match) -> tuple[int, str]:
    return int(match.group(1)), match.group(2).lower()


@dataclass(frozen=True)
class Section:
    key: str
    title: str
    text: str
    start: int


def split_sections(text: str, form: str = "10-K", max_chars_per_section: int = 150_000) -> list[Section]:
    """Find each item's real body: the heading occurrence followed by the longest text.

    The table of contents repeats every heading, but its "sections" are one line long.
    """
    # Filings repeat "Item 1A" as a running header on every page, so only a *different* item ends a section.
    marks = [(m.start(), _item_id(m)) for m in _ANY_ITEM.finditer(text)]
    sections = []
    for key, title, pattern in (TEN_Q_SECTIONS if form.startswith("10-Q") else TEN_K_SECTIONS):
        best: tuple[int, int] | None = None
        for match in re.finditer(r"^\s*" + pattern, text, re.IGNORECASE | re.MULTILINE):
            start = match.start()
            own = _ANY_ITEM.match(text, start)
            item = _item_id(own) if own else (0, "")
            end = next((pos for pos, other in marks if pos > start and other != item), len(text))
            if best is None or end - start > best[1] - best[0]:
                best = (start, end)
        if best and best[1] - best[0] > 500:
            body = text[best[0] : best[1]].strip()[:max_chars_per_section]
            sections.append(Section(key=key, title=title, text=body, start=best[0]))
    return sorted(sections, key=lambda section: section.start)
