"""Reading a job's DCF valuation and running what-ifs on its stored inputs (ADR 0010). No model calls."""
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.research_job import ResearchJob
from backend.models.valuation import Valuation
from backend.schemas.valuation import AssumptionOut, ValuationOut, WhatIfRequest
from backend.services.errors import BadRequestError, NotFoundError
from backend.valuation.dcf import DcfInputs, InvalidAssumptions, ValuationSkipped, apply_overrides, value_firm

# (field, label, unit, editable in a what-if)
ASSUMPTIONS = [
    ("base_ebit", "Operating income, base year", "USD", False),
    ("effective_tax_rate", "Effective tax rate", "ratio", False),
    ("marginal_tax_rate", "Marginal tax rate (stable)", "ratio", False),
    ("high_growth", "High-growth rate", "ratio", True),
    ("high_growth_years", "High-growth years", "years", True),
    ("transition_years", "Transition years", "years", True),
    ("return_on_capital", "Return on new capital", "ratio", True),
    ("stable_growth", "Stable growth rate", "ratio", True),
    ("stable_return_on_capital", "Stable return on capital", "ratio", True),
    ("risk_free_rate", "Risk-free rate", "ratio", False),
    ("equity_risk_premium", "Equity risk premium", "ratio", True),
    ("unlevered_beta", "Unlevered beta", "number", False),
    ("debt_to_capital", "Debt ratio D/(D+E)", "ratio", True),
    ("default_spread", "Default spread", "ratio", False),
    ("stable_beta", "Stable beta", "number", False),
    ("cash", "Cash", "USD", False),
    ("non_operating_assets", "Short-term investments", "USD", False),
    ("debt", "Debt", "USD", False),
    ("lease_liabilities", "Lease liabilities", "USD", False),
    ("minority_interest", "Minority interest", "USD", False),
    ("shares", "Diluted shares", "shares", False),
]


def _range(sensitivity: dict, base_growth: str) -> tuple[Decimal | None, Decimal | None]:
    growths = [Decimal(g) for g in sensitivity["stable_growths"]]
    base = Decimal(base_growth)
    cols = [i for i, g in enumerate(growths) if abs(g - base) <= Decimal("0.005")]
    cells = [Decimal(v) for row in sensitivity["value_per_share"][1:4] for i, v in enumerate(row) if i in cols and v is not None]
    return (min(cells), max(cells)) if cells else (None, None)


def to_out(job_id: UUID, valuation: Valuation, result: dict | None = None, *, overridden: list[str] | None = None) -> ValuationOut:
    if valuation.status != "valued":
        return ValuationOut(job_id=job_id, status=valuation.status, skip_reason=valuation.skip_reason, method=valuation.method,
                            calculation_version=valuation.calculation_version, created_at=valuation.created_at)
    result = result or {**valuation.result, "inputs": valuation.inputs, "warnings": valuation.warnings or []}
    inputs = result["inputs"]
    sources = inputs.get("sources", {})
    derived = result["derived"]
    assumptions = []
    for key, label, unit, editable in ASSUMPTIONS:
        value = inputs.get(key)
        source = sources.get(key, "")
        if key == "stable_return_on_capital" and value is None:
            value, source = derived["stable_return_on_capital"], "= stable cost of capital (no excess returns forever)"
        if value is None:
            continue
        assumptions.append(AssumptionOut(key=key, label=label, value=Decimal(str(value)), unit=unit, source=source, editable=editable))
    low, high = _range(result["sensitivity"], inputs["stable_growth"])
    return ValuationOut(
        job_id=job_id, status="valued", method=valuation.method, calculation_version=result.get("calculation_version", valuation.calculation_version),
        industry=valuation.industry, base_year=inputs["base_year"], value_per_share=Decimal(result["bridge"]["value_per_share"]),
        range_low=low, range_high=high, equity_value=Decimal(result["bridge"]["equity_value"]),
        operating_value=Decimal(result["bridge"]["operating_value"]), assumptions=assumptions, derived=derived,
        projection=result["projection"], terminal=result["terminal"], bridge=result["bridge"], sensitivity=result["sensitivity"],
        warnings=result.get("warnings", []), what_if=overridden is not None, overridden=overridden or [],
        created_at=valuation.created_at,
    )


class ValuationService:
    def _load(self, session: Session, job_id: UUID, user_id: UUID) -> Valuation:
        job = session.scalar(select(ResearchJob).where(ResearchJob.id == job_id, ResearchJob.user_id == user_id))
        if job is None:
            raise NotFoundError("Research job not found")
        valuation = session.scalar(select(Valuation).where(Valuation.research_job_id == job_id))
        if valuation is None:
            raise NotFoundError("This job has no valuation yet")
        return valuation

    def get(self, session: Session, *, job_id: UUID, user_id: UUID) -> ValuationOut:
        return to_out(job_id, self._load(session, job_id, user_id))

    def what_if(self, session: Session, *, job_id: UUID, user_id: UUID, request: WhatIfRequest) -> ValuationOut:
        """Recompute from the stored inputs with some assumptions changed. Nothing is saved."""
        valuation = self._load(session, job_id, user_id)
        if valuation.status != "valued":
            raise BadRequestError(f"There is no valuation to vary: {valuation.skip_reason}")
        overrides = request.model_dump(exclude_none=True)
        inputs = apply_overrides(DcfInputs.from_json(valuation.inputs), overrides)
        try:
            result = value_firm(inputs)
        except (InvalidAssumptions, ValuationSkipped) as exc:
            raise BadRequestError(str(exc)) from exc
        return to_out(job_id, valuation, result, overridden=sorted(overrides))
