"""SEC SIC code → Damodaran industry (ADR 0010).

Damodaran classifies firms by Capital IQ industry and publishes no SIC mapping, so this table is ours. When ranges
overlap, the narrowest one that contains the code wins (an exact code beats a range). Anything unmapped falls back
to the market average without financials, and the valuation says so.
"""
from dataclasses import dataclass

from backend.valuation.reference import FALLBACK_INDUSTRY, industries

# (first SIC, last SIC, Damodaran industry). Overlaps resolve to the narrowest range.
_SIC_MAP: list[tuple[int, int, str]] = [
    # Technology
    (3570, 3579, "Computers/Peripherals"),
    (3670, 3679, "Semiconductor"),
    (3559, 3559, "Semiconductor Equip"),
    (3661, 3669, "Telecom. Equipment"),
    (3651, 3652, "Electronics (Consumer & Office)"),
    (3600, 3699, "Electronics (General)"),
    (3810, 3829, "Electronics (General)"),
    (7370, 7371, "Software (System & Application)"),
    (7372, 7372, "Software (System & Application)"),
    (7373, 7373, "Computer Services"),
    (7374, 7374, "Software (Internet)"),
    (7375, 7379, "Computer Services"),
    (4899, 4899, "Telecom. Services"),
    (4812, 4812, "Telecom (Wireless)"),
    (4813, 4813, "Telecom. Services"),
    (4841, 4841, "Cable TV"),
    (4830, 4833, "Broadcasting"),
    # Retail and consumer
    (5961, 5961, "Retail (General)"),  # catalog, mail-order and online retail (Damodaran has no online category)
    (5331, 5331, "Retail (General)"),
    (5311, 5399, "Retail (General)"),
    (5400, 5499, "Retail (Grocery and Food)"),
    (5200, 5299, "Retail (Building Supply)"),
    (5500, 5599, "Retail (Automotive)"),
    (5810, 5819, "Restaurant/Dining"),
    (5600, 5999, "Retail (Special Lines)"),
    (5000, 5199, "Retail (Distributors)"),
    (2080, 2085, "Beverage (Alcoholic)"),
    (2086, 2087, "Beverage (Soft)"),
    (2100, 2199, "Tobacco"),
    (2000, 2099, "Food Processing"),
    (2300, 2399, "Apparel"),
    (3140, 3149, "Shoe"),
    (2840, 2844, "Household Products"),
    (2500, 2599, "Furn/Home Furnishings"),
    (3940, 3949, "Recreation"),
    (7000, 7099, "Hotel/Gaming"),
    (7900, 7999, "Entertainment"),
    (7800, 7899, "Entertainment"),
    (2700, 2799, "Publishing & Newspapers"),
    (7310, 7319, "Advertising"),
    (8200, 8299, "Education"),
    # Health care
    (2834, 2834, "Drugs (Pharmaceutical)"),
    (2833, 2836, "Drugs (Biotechnology)"),
    (3841, 3851, "Healthcare Products"),
    (8000, 8049, "Healthcare Support Services"),
    (8050, 8099, "Hospitals/Healthcare Facilities"),
    (6324, 6324, "Healthcare Support Services"),
    # Industrials and materials
    (3720, 3729, "Aerospace/Defense"),
    (3760, 3769, "Aerospace/Defense"),
    (3711, 3711, "Auto & Truck"),
    (3713, 3716, "Auto & Truck"),
    (3714, 3714, "Auto Parts"),
    (3000, 3099, "Rubber& Tires"),
    (3500, 3569, "Machinery"),
    (3580, 3599, "Machinery"),
    (3700, 3799, "Transportation"),
    (3300, 3329, "Steel"),
    (1000, 1099, "Metals & Mining"),
    (1040, 1049, "Precious Metals"),
    (2800, 2829, "Chemical (Basic)"),
    (2850, 2899, "Chemical (Specialty)"),
    (2600, 2699, "Paper/Forest Products"),
    (3200, 3299, "Building Materials"),
    (1500, 1799, "Engineering/Construction"),
    (1520, 1531, "Homebuilding"),
    (3410, 3412, "Packaging & Container"),
    (4955, 4955, "Environmental & Waste Services"),
    (4950, 4959, "Environmental & Waste Services"),
    (8700, 8799, "Business & Consumer Services"),
    (7300, 7399, "Business & Consumer Services"),
    # Energy and utilities
    (1311, 1311, "Oil/Gas (Production and Exploration)"),
    (1381, 1389, "Oilfield Svcs/Equip."),
    (2911, 2911, "Oil/Gas (Integrated)"),
    (4920, 4925, "Oil/Gas Distribution"),
    (4911, 4911, "Power"),
    (4931, 4939, "Utility (General)"),
    (4940, 4941, "Utility (Water)"),
    (1200, 1299, "Coal & Related Energy"),
    # Transport
    (4011, 4013, "Transportation (Railroads)"),
    (4210, 4219, "Trucking"),
    (4500, 4599, "Air Transport"),
    (4400, 4499, "Shipbuilding & Marine"),
    (4000, 4799, "Transportation"),
    # Financials (not valued with FCFF in v1, mapped for completeness)
    (6000, 6099, "Banks (Regional)"),
    (6200, 6299, "Brokerage & Investment Banking"),
    (6300, 6411, "Insurance (General)"),
    (6500, 6599, "Real Estate (General/Diversified)"),
    (6798, 6798, "R.E.I.T."),
]


@dataclass(frozen=True)
class IndustryMatch:
    industry: str
    sic: str | None
    fallback: bool


def industry_for_sic(sic: str | None) -> IndustryMatch:
    known = industries()
    if sic and sic.isdigit():
        code = int(sic)
        for low, high, name in sorted(_SIC_MAP, key=lambda row: row[1] - row[0]):
            if low <= code <= high and name in known:
                return IndustryMatch(industry=name, sic=sic, fallback=False)
    return IndustryMatch(industry=FALLBACK_INDUSTRY, sic=sic, fallback=True)
