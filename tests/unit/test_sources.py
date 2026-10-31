from datetime import date
from decimal import Decimal

import pytest

from backend.analysis.chunking import chunk_text
from backend.sources.filing_text import html_to_text, split_sections
from backend.sources.sec import Filing, is_financial_sector
from backend.sources.xbrl import UnsupportedFinancialsError, extract_annual_periods, fiscal_year_for


def flow(val, start, end, filed, form="10-K", accn=None, fp="FY"):
    return {"val": val, "start": start, "end": end, "filed": filed, "form": form, "fp": fp, "accn": accn or f"a-{filed}"}


def instant(val, end, filed, form="10-K"):
    return {"val": val, "end": end, "filed": filed, "form": form, "accn": f"a-{filed}"}


def facts(**concepts):
    return {"facts": {"us-gaap": {name: {"units": units} for name, units in concepts.items()}}}


COMPANY_FACTS = facts(
    RevenueFromContractWithCustomerExcludingAssessedTax={
        "USD": [
            flow(100, "2021-10-01", "2022-09-30", "2022-11-01"),
            flow(120, "2022-10-01", "2023-09-30", "2023-11-01"),
            flow(118, "2022-10-01", "2023-09-30", "2024-11-01"),  # restated in the FY2024 10-K
            flow(150, "2023-10-01", "2024-09-30", "2024-11-01"),
            flow(40, "2024-07-01", "2024-09-30", "2024-11-01"),  # quarter: ignored
            flow(155, "2023-10-01", "2024-09-30", "2024-08-01", form="10-Q"),  # wrong form: ignored
        ]
    },
    NetIncomeLoss={"USD": [flow(30, "2023-10-01", "2024-09-30", "2024-11-01")]},
    Revenues={"USD": [flow(999, "2021-10-01", "2022-09-30", "2022-11-01")]},  # fallback concept, lower priority
    PaymentsToAcquirePropertyPlantAndEquipment={"USD": [flow(12, "2023-10-01", "2024-09-30", "2024-11-01")]},
    EarningsPerShareDiluted={"USD/shares": [flow(1.5, "2023-10-01", "2024-09-30", "2024-11-01")]},
    Assets={"USD": [instant(500, "2024-09-30", "2024-11-01"), instant(450, "2023-09-30", "2023-11-01")]},
    LongTermDebtNoncurrent={"USD": [instant(80, "2024-09-30", "2024-11-01")]},
)


def test_extracts_annual_values_keyed_by_period_end():
    extraction = extract_annual_periods(COMPANY_FACTS)

    assert [p.fiscal_year for p in extraction.periods] == [2022, 2023, 2024]
    fy24 = extraction.periods[-1]
    assert fy24.values["revenue"] == Decimal("150")
    assert fy24.values["net_income"] == Decimal("30")
    assert fy24.values["capital_expenditure"] == Decimal("12")
    assert fy24.values["eps"] == Decimal("1.5")
    assert fy24.values["total_assets"] == Decimal("500")
    assert fy24.values["debt"] == Decimal("80")


def test_latest_filed_value_wins_for_restatements():
    fy23 = extract_annual_periods(COMPANY_FACTS).periods[1]

    assert fy23.values["revenue"] == Decimal("118")
    assert fy23.provenance["revenue"]["filed"] == "2024-11-01"


def test_concept_priority_order():
    fy22 = extract_annual_periods(COMPANY_FACTS).periods[0]

    assert fy22.values["revenue"] == Decimal("100")
    assert fy22.provenance["revenue"]["concept"] == "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"


def test_provenance_records_concept_filing_and_unit():
    provenance = extract_annual_periods(COMPANY_FACTS).periods[-1].provenance["eps"]

    assert provenance == {
        "concept": "us-gaap:EarningsPerShareDiluted",
        "accession": "a-2024-11-01",
        "form": "10-K",
        "filed": "2024-11-01",
        "unit": "USD/shares",
        "period_start": "2023-10-01",
        "period_end": "2024-09-30",
    }


def test_missing_fields_reported_per_year():
    missing = extract_annual_periods(COMPANY_FACTS).missing

    assert missing["net_income"] == [2022, 2023]
    assert 2024 in missing["operating_income"]


def test_limits_to_requested_years():
    assert [p.fiscal_year for p in extract_annual_periods(COMPANY_FACTS, years=2).periods] == [2023, 2024]


def test_non_usd_reporter_is_unsupported():
    with pytest.raises(UnsupportedFinancialsError, match="currency"):
        extract_annual_periods(facts(Revenues={"EUR": [flow(1, "2023-01-01", "2023-12-31", "2024-03-01")]}))


def test_no_annual_data_is_unsupported():
    with pytest.raises(UnsupportedFinancialsError):
        extract_annual_periods(facts())


@pytest.mark.parametrize(
    "end, year",
    [(date(2024, 9, 28), 2024), (date(2025, 1, 26), 2025), (date(2023, 1, 1), 2022), (date(2024, 12, 31), 2024)],
)
def test_fiscal_year_labels(end, year):
    assert fiscal_year_for(end) == year


def test_financial_sector_detection():
    assert is_financial_sector("6021")
    assert is_financial_sector("6798")
    assert not is_financial_sector("3571")
    assert not is_financial_sector(None)


def test_filing_url():
    filing = Filing("0000320193", "0000320193-24-000123", "10-K", date(2024, 11, 1), None, "aapl-20240928.htm", None)

    assert filing.url == "https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm"


HTML = """
<html><head><title>10-K</title><style>.x{}</style></head><body>
<div style="display:none"><ix:header>hidden xbrl junk</ix:header></div>
<p>TABLE OF CONTENTS</p>
<p>Item 1. Business</p><p>Item 1A. Risk Factors</p><p>Item 7. Management&#8217;s Discussion and Analysis</p>
<p>Item 1. Business</p>
<p>We design&nbsp;phones. </p>""" + "<p>Our products sell worldwide.</p>" * 40 + """
<p>Item 1A. Risk Factors</p>
""" + "<p>Supply chain disruption could hurt margins.</p>" * 40 + """
<p>Item 1B. Unresolved Staff Comments</p><p>None.</p>
<p>Item 7. Management's Discussion and Analysis of Financial Condition</p>
""" + "<p>Revenue increased 2% driven by services.</p>" * 40 + """
<p>Item 8. Financial Statements</p>
<table><tr><td>Revenue</td><td>391,035</td></tr></table>
</body></html>
"""


def test_html_to_text_strips_hidden_and_markup():
    text = html_to_text(HTML)

    assert "hidden xbrl junk" not in text
    assert ".x{}" not in text
    assert "We design phones." in text
    assert "Management’s Discussion" in text
    assert "Revenue 391,035" in text


def test_split_sections_skips_table_of_contents():
    sections = {s.key: s for s in split_sections(html_to_text(HTML))}

    assert set(sections) == {"business", "risk_factors", "mdna"}
    assert sections["business"].text.startswith("Item 1. Business")
    assert "We design phones." in sections["business"].text
    assert "Supply chain" not in sections["business"].text
    assert "Unresolved Staff" not in sections["risk_factors"].text
    assert "391,035" not in sections["mdna"].text


def test_chunking_respects_size_and_overlaps():
    text = "\n".join(f"Paragraph {i} " + "word " * 40 for i in range(30))

    chunks = chunk_text("mdna", text, target_chars=600, overlap_chars=250)

    assert all(len(c.content) <= 600 for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    first_tail = chunks[0].content.split("\n")[-1]
    assert chunks[1].content.startswith(first_tail)
    joined = "\n".join(c.content for c in chunks)
    assert all(f"Paragraph {i} " in joined for i in range(30))


def test_chunking_splits_long_paragraph_on_sentences():
    paragraph = " ".join(f"Sentence number {i} is here." for i in range(200))

    chunks = chunk_text("risk_factors", paragraph, target_chars=500, overlap_chars=0)

    assert len(chunks) > 1
    assert all(len(c.content) <= 500 for c in chunks)
    assert all(c.content.rstrip().endswith(".") for c in chunks)


def test_running_page_headers_do_not_end_a_section():
    # Real 10-Ks (e.g. Microsoft's) repeat "Item 1A" at the top of every page of that item.
    page = "<p>Supply constraints could reduce our margins in many markets.</p>" * 10
    html = (
        "<p>Item 1. Business</p><p>Item 1A. Risk Factors</p>"
        "<p>ITEM 1. BUSINESS</p>" + page + "<p>Item 1</p>" + page
        + "<p>Item 1A</p><p>ITEM 1A. RISK FACTORS</p>" + page + "<p>Item 1A</p>" + page + "<p>Item 1A</p>" + page
        + "<p>ITEM 1B. UNRESOLVED STAFF COMMENTS</p><p>None.</p>"
    )

    sections = {s.key: s for s in split_sections(html_to_text(html))}

    assert sections["business"].text.count("Supply constraints") == 20
    assert sections["risk_factors"].text.count("Supply constraints") == 30
    assert "UNRESOLVED" not in sections["risk_factors"].text


def test_extracts_the_dcf_inputs_with_concept_fallbacks():
    """D&A, taxes and the bridge items come from their own concepts; later fallbacks fill gaps (ADR 0010)."""
    company_facts = facts(
        Revenues={"USD": [flow(1000, "2023-10-01", "2024-09-30", "2024-11-01")]},
        DepreciationAndAmortization={"USD": [flow(55, "2023-10-01", "2024-09-30", "2024-11-01")]},
        IncomeTaxExpenseBenefit={"USD": [flow(40, "2023-10-01", "2024-09-30", "2024-11-01")]},
        IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest={
            "USD": [flow(200, "2023-10-01", "2024-09-30", "2024-11-01")]
        },
        MarketableSecuritiesCurrent={"USD": [instant(70, "2024-09-30", "2024-11-01")]},
        OperatingLeaseLiability={"USD": [instant(90, "2024-09-30", "2024-11-01")]},
    )

    [period] = extract_annual_periods(company_facts).periods

    assert period.values["depreciation_amortization"] == Decimal("55")
    assert period.provenance["depreciation_amortization"]["concept"] == "us-gaap:DepreciationAndAmortization"
    assert period.values["income_tax_expense"] == Decimal("40")
    assert period.values["pretax_income"] == Decimal("200")
    assert period.values["short_term_investments"] == Decimal("70")
    assert period.values["lease_liabilities"] == Decimal("90")
    assert "minority_interest" not in period.values
