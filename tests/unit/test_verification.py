from decimal import Decimal as D

import pytest

from backend.analysis.verification import extract_numbers, quote_in_source, unmatched_numbers

SOURCE = """The Company’s products and services include iPhone,  Mac, iPad.
Net sales increased 2% or $8.0 billion during 2024 compared to 2023 —
driven by higher Services revenue."""


@pytest.mark.parametrize(
    "quote, expected",
    [
        ("The Company's products and services include iPhone, Mac, iPad.", True),
        ("Net sales increased 2% or $8.0 billion during 2024", True),
        ("Net sales increased 2% ... driven by higher Services revenue", True),
        ("Net sales increased 5% or $8.0 billion during 2024", False),
        ("iPhone", False),  # too short to be meaningful evidence
        ("", False),
    ],
)
def test_quote_in_source(quote, expected):
    assert quote_in_source(quote, SOURCE) is expected


def test_extract_numbers_kinds_and_scales():
    mentions = {m.raw: (m.value, m.kind) for m in extract_numbers("Margin was 44.6%, FCF $72.3 billion, coverage 41.2x and net cash -$350M in 2024.")}

    assert mentions["44.6%"] == (D("0.446"), "percent")
    assert mentions["$72.3 billion"] == (D("72300000000"), "usd")
    assert mentions["41.2x"] == (D("41.2"), "times")
    assert mentions["-$350M"] == (D("-350000000"), "usd")
    assert not any(kind for raw, (_, kind) in mentions.items() if raw.startswith("2024"))


def test_unmatched_numbers_tolerates_rounding():
    metrics = [(D("0.44617"), "ratio"), (D("72295000000"), "USD")]

    assert unmatched_numbers("Operating margin reached 44.6% with $72.3B of free cash flow.", metrics) == []
    assert unmatched_numbers("Operating margin reached 48.0%.", metrics) == ["48.0%"]
