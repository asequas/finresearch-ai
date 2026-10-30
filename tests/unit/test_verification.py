from decimal import Decimal as D

import pytest

from backend.analysis.verification import extract_numbers, quote_in_source, unmatched_numbers

SOURCE = """PART I Item 1. Business\nItem 1A. Risk Factors\nThe Company’s products and services include iPhone,  Mac, iPad.
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
        ("Item 1A. Risk Factors", False),  # a heading is verbatim but supports nothing
        ("PART I Item 1. Business", False),
        ("products and services include iPhone", False),  # five words: too thin
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


CHUNK = """Microsoft Cloud revenue increased 27% to $214.4 billion, driven by Azure and other cloud services.
Server products and cloud services revenue increased 32%. Gaming revenue decreased 4%."""


def test_snap_quote_recovers_the_filings_exact_wording():
    from backend.analysis.verification import snap_quote

    paraphrase = "Microsoft Cloud revenue grew 27% to $214.4 billion, driven by Azure and other cloud services."
    assert snap_quote(paraphrase, CHUNK) == "Microsoft Cloud revenue increased 27% to $214.4 billion, driven by Azure and other cloud services."


def test_snap_quote_refuses_loose_matches():
    from backend.analysis.verification import snap_quote

    assert snap_quote("Microsoft's cloud business is the main driver of its future margin expansion.", CHUNK) is None
    assert snap_quote("Gaming revenue increased 40% this year overall", CHUNK) is None
    assert snap_quote("Item 1A. Risk Factors", CHUNK) is None


TABLE = """Segment results
North America 9,872 10,483 AWS 11,434 17,773 33,141 48,555
Consolidated 68,593 79,975"""


@pytest.mark.parametrize(
    "quote, expected",
    [
        ("AWS 11,434 17,773 33,141 48,555", True),  # a data row is evidence even though it's short
        ("Consolidated $ 68,593 $ 79,975", True),  # currency symbols split into their own cells
        ("AWS 11,434 99,999", False),  # figures that aren't in the filing
        ("Segment results", False),  # a label without figures
    ],
)
def test_table_rows_count_as_evidence(quote, expected):
    assert quote_in_source(quote, TABLE) is expected
