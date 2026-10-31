"""Reading a job's fair value, checking it against the share price, and running what-ifs (ADR 0012). No model calls."""
from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.models.research_job import ResearchJob
from backend.models.valuation import Valuation
from backend.schemas.valuation import AssumptionOut, MarketPriceOut, PriceCheckOut, ValuationOut, WhatIfRequest
from backend.services.errors import BadRequestError, NotFoundError
from backend.valuation.fair_value import (
    FairValueInputs,
    InvalidAssumptions,
    ValuationSkipped,
    apply_overrides,
    implied_growth,
    value,
)
from backend.valuation.price import MarketPrice, latest_price

# (field, label, unit, editable in a what-if)
ASSUMPTIONS = [
    ("base_fcf", "Free cash flow, normalised", "USD", False),
    ("initial_growth", "Growth, first years", "ratio", True),
    ("high_growth_years", "Years at that growth", "years", True),
    ("fade_years", "Years fading to long-run growth", "years", True),
    ("stable_growth", "Long-run growth", "ratio", True),
    ("normalised_operating_income", "Normalised operating income", "USD", False),
    ("tax_rate", "Tax rate", "ratio", False),
    ("risk_free_rate", "Risk-free rate", "ratio", False),
    ("equity_risk_premium", "Equity risk premium", "ratio", True),
    ("unlevered_beta", "Unlevered beta", "number", False),
    ("debt_to_capital", "Debt ratio D/(D+E)", "ratio", True),
    ("default_spread", "Default spread", "ratio", False),
    ("cash", "Cash", "USD", False),
    ("non_operating_assets", "Short-term investments", "USD", False),
    ("debt", "Debt", "USD", False),
    ("minority_interest", "Minority interest", "USD", False),
    ("shares", "Diluted shares", "shares", False),
]

PriceFetcher = Callable[[str], MarketPrice | None]


def default_price_fetcher(ticker: str) -> MarketPrice | None:
    return latest_price(ticker, settings.data_cache_dir, source=settings.price_source)


def to_out(job_id: UUID, valuation: Valuation, result: dict | None = None, *, overridden: list[str] | None = None) -> ValuationOut:
    if valuation.status != "valued":
        return ValuationOut(job_id=job_id, status=valuation.status, skip_reason=valuation.skip_reason, method=valuation.method,
                            calculation_version=valuation.calculation_version, created_at=valuation.created_at)
    result = result or {**valuation.result, "inputs": valuation.inputs, "warnings": valuation.warnings or []}
    inputs = result["inputs"]
    sources = inputs.get("sources", {})
    assumptions = [
        AssumptionOut(key=key, label=label, value=Decimal(str(inputs[key])), unit=unit, source=sources.get(key, ""), editable=editable)
        for key, label, unit, editable in ASSUMPTIONS if inputs.get(key) is not None
    ]
    return ValuationOut(
        job_id=job_id, status="valued", method=valuation.method,
        calculation_version=result.get("calculation_version", valuation.calculation_version), industry=valuation.industry,
        base_year=inputs["base_year"], fair_value=Decimal(result["fair_value"]), range_low=Decimal(result["range_low"]),
        range_high=Decimal(result["range_high"]), methods_used=result["methods_used"], assumptions=assumptions,
        cost_of_capital=result["cost_of_capital"], fcf_history=inputs.get("history", []), dcf=result.get("dcf"),
        epv=result.get("epv"), sensitivity=result.get("sensitivity"), warnings=result.get("warnings", []),
        what_if=overridden is not None, overridden=overridden or [], created_at=valuation.created_at,
    )


def price_check(inputs: FairValueInputs, out: ValuationOut, price: Decimal, record_growth: Decimal) -> PriceCheckOut:
    low, high, fair = out.range_low, out.range_high, out.fair_value
    position = "below_range" if price < low else "above_range" if price > high else "within_range"
    gap = fair / price - 1
    implied = implied_growth(inputs, price)
    if position == "below_range":
        lead = f"The price is below the fair-value range: on these assumptions the shares look undervalued (fair value {gap:.0%} above the price)."
    elif position == "above_range":
        lead = f"The price is above the fair-value range: on these assumptions the shares look overvalued (fair value {-gap:.0%} below the price)."
    else:
        lead = "The price is within the fair-value range: on these assumptions the shares look roughly fairly valued."
    if implied is not None:
        tail = (f" To justify this price, free cash flow would need to grow about {implied:.1%} a year for "
                f"{inputs.high_growth_years} years (the revenue record suggests {record_growth:.1%}).")
    elif "dcf" in out.methods_used:
        tail = " No growth rate between 0% and 60% makes the cash-flow DCF match this price."
    else:
        tail = ""
    return PriceCheckOut(price=price, fair_value=fair, range_low=low, range_high=high, gap=gap.quantize(Decimal("0.0001")),
                         position=position, implied_growth=implied, explanation=lead + tail)


class ValuationService:
    def __init__(self, price_fetcher: PriceFetcher | None = None):
        self.price_fetcher = price_fetcher or default_price_fetcher

    def _load(self, session: Session, job_id: UUID, user_id: UUID) -> tuple[ResearchJob, Valuation]:
        job = session.scalar(select(ResearchJob).where(ResearchJob.id == job_id, ResearchJob.user_id == user_id))
        if job is None:
            raise NotFoundError("Research job not found")
        valuation = session.scalar(select(Valuation).where(Valuation.research_job_id == job_id))
        if valuation is None:
            raise NotFoundError("This job has no valuation yet")
        return job, valuation

    def _with_price(self, out: ValuationOut, inputs: FairValueInputs | None, ticker: str, typed: Decimal | None,
                    record_growth: Decimal | None = None) -> ValuationOut:
        if out.status != "valued" or inputs is None:
            return out
        if typed is not None:
            out.market_price = MarketPriceOut(price=typed, as_of=None, source="entered by you")
        else:
            quote = self.price_fetcher(ticker)
            if quote is not None:
                out.market_price = MarketPriceOut(price=quote.price, as_of=quote.as_of, source=quote.source)
        if out.market_price is not None:
            growth = record_growth if record_growth is not None else inputs.initial_growth
            out.price_check = price_check(inputs, out, out.market_price.price, growth)
        return out

    def get(self, session: Session, *, job_id: UUID, user_id: UUID) -> ValuationOut:
        job, valuation = self._load(session, job_id, user_id)
        out = to_out(job_id, valuation)
        inputs = FairValueInputs.from_json(valuation.inputs) if valuation.inputs else None
        return self._with_price(out, inputs, job.ticker, None)

    def what_if(self, session: Session, *, job_id: UUID, user_id: UUID, request: WhatIfRequest) -> ValuationOut:
        """Recompute from the stored inputs with some assumptions changed. Nothing is saved."""
        job, valuation = self._load(session, job_id, user_id)
        if valuation.status != "valued":
            raise BadRequestError(f"There is no valuation to vary: {valuation.skip_reason}")
        overrides = request.model_dump(exclude_none=True)
        typed = overrides.pop("market_price", None)
        stored = FairValueInputs.from_json(valuation.inputs)
        inputs = apply_overrides(stored, overrides)
        try:
            out = to_out(job_id, valuation, value(inputs), overridden=sorted(overrides)) if overrides else to_out(job_id, valuation)
            return self._with_price(out, inputs, job.ticker, typed, stored.initial_growth)
        except (InvalidAssumptions, ValuationSkipped) as exc:
            raise BadRequestError(str(exc)) from exc
