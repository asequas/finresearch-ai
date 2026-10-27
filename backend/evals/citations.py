"""Evaluation of evidence quality (vision: citation coverage and >=95% citation correctness).

Automatic metrics need no labels:
    python -m backend.evals.citations auto <job_id> [<job_id> ...]

Human-labelled citation correctness:
    python -m backend.evals.citations export <job_id> > evals/labels/<ticker>.json
    # set "label" on each item to "correct" or "incorrect" (does the cited evidence support the claim?)
    python -m backend.evals.citations score evals/labels/*.json
"""
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.database import SessionLocal
from backend.models import Claim, ClaimEvidence, ClaimMetric, Evidence, ResearchJob

MATERIAL_TYPES = ("fact", "calculation")
TARGET_CORRECTNESS = 0.95


@dataclass
class AutoMetrics:
    job_id: str
    ticker: str
    claims: int
    material_claims: int
    citation_coverage: float  # material claims with at least one verified quote or metric
    quote_verification_rate: float  # cited quotes found verbatim in their chunk
    numeric_consistency: float  # calculation claims whose numbers match their metric
    supported_share: float
    unsupported_share: float


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def auto_metrics(session: Session, job_id: UUID) -> AutoMetrics:
    job = session.get(ResearchJob, job_id)
    claims = list(session.scalars(select(Claim).where(Claim.research_job_id == job_id)))
    claim_ids = [c.id for c in claims]
    verified_quotes: dict[UUID, int] = {}
    quotes_total = quotes_ok = 0
    for claim_id, evidence in session.execute(
        select(ClaimEvidence.claim_id, Evidence)
        .join(Evidence, Evidence.id == ClaimEvidence.evidence_id)
        .where(ClaimEvidence.claim_id.in_(claim_ids))
    ):
        quotes_total += 1
        if evidence.quote_verified:
            quotes_ok += 1
            verified_quotes[claim_id] = verified_quotes.get(claim_id, 0) + 1
    with_metric = set(session.scalars(select(ClaimMetric.claim_id).where(ClaimMetric.claim_id.in_(claim_ids))))

    material = [c for c in claims if c.claim_type in MATERIAL_TYPES]
    covered = [c for c in material if verified_quotes.get(c.id) or (c.claim_type == "calculation" and c.id in with_metric)]
    calculations = [c for c in claims if c.claim_type == "calculation"]
    consistent = [c for c in calculations if c.verification_status == "supported"]

    return AutoMetrics(
        job_id=str(job_id),
        ticker=job.ticker if job else "?",
        claims=len(claims),
        material_claims=len(material),
        citation_coverage=_ratio(len(covered), len(material)),
        quote_verification_rate=_ratio(quotes_ok, quotes_total),
        numeric_consistency=_ratio(len(consistent), len(calculations)),
        supported_share=_ratio(sum(c.verification_status == "supported" for c in claims), len(claims)),
        unsupported_share=_ratio(sum(c.verification_status == "unsupported" for c in claims), len(claims)),
    )


def export_for_labelling(session: Session, job_id: UUID) -> list[dict]:
    """One item per (claim, cited evidence or metric) for a human to judge."""
    job = session.get(ResearchJob, job_id)
    items = []
    claims = session.scalars(select(Claim).where(Claim.research_job_id == job_id).order_by(Claim.position))
    for claim in claims:
        evidence = session.scalars(
            select(Evidence).join(ClaimEvidence, ClaimEvidence.evidence_id == Evidence.id).where(ClaimEvidence.claim_id == claim.id)
        ).all()
        items.append(
            {
                "job_id": str(job_id),
                "ticker": job.ticker if job else None,
                "claim_id": str(claim.id),
                "claim_type": claim.claim_type,
                "claim": claim.claim_text,
                "system_verdict": claim.verification_status,
                "evidence": [{"quote": e.excerpt, "quote_verified": e.quote_verified, "url": e.source_url} for e in evidence],
                "label": None,
                "note": "",
            }
        )
    return items


@dataclass
class LabelScore:
    labelled: int
    correct: int
    citation_correctness: float
    meets_target: bool
    # How well the automatic verdict agrees with people: of claims the system called supported, how many were right.
    system_supported_precision: float


def score_labels(items: list[dict]) -> LabelScore:
    labelled = [i for i in items if i.get("label") in ("correct", "incorrect") and i["claim_type"] in MATERIAL_TYPES]
    correct = sum(i["label"] == "correct" for i in labelled)
    system_supported = [i for i in labelled if i["system_verdict"] == "supported"]
    correctness = _ratio(correct, len(labelled))
    return LabelScore(
        labelled=len(labelled),
        correct=correct,
        citation_correctness=correctness,
        meets_target=bool(labelled) and correctness >= TARGET_CORRECTNESS,
        system_supported_precision=_ratio(sum(i["label"] == "correct" for i in system_supported), len(system_supported)),
    )


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in ("auto", "export", "score"):
        print(__doc__)
        return 2
    command, args = argv[0], argv[1:]
    if command == "score":
        items = [item for path in args for item in json.loads(Path(path).read_text())]
        print(json.dumps(asdict(score_labels(items)), indent=2))
        return 0
    with SessionLocal() as session:
        if command == "auto":
            print(json.dumps([asdict(auto_metrics(session, UUID(a))) for a in args], indent=2))
        else:
            print(json.dumps(export_for_labelling(session, UUID(args[0])), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
