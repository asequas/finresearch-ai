"""Retrieval evaluation: which strategy puts the passage that answers a question at the top?

    python -m backend.evals.retrieval [evals/retrieval_gold.json] [--k 6]

Strategies: vector only, keyword only, hybrid (RRF), hybrid + cross-encoder rerank.
A chunk is relevant when it contains one of the query's answer phrases (case-insensitive),
which keeps the labels valid across re-indexing.
"""
import json
import math
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.analysis.rerank import Reranker, get_reranker
from backend.analysis.retrieval import RetrievedChunk, hybrid_search, keyword_search, rerank_chunks, vector_search
from backend.core.config import settings
from backend.core.database import SessionLocal
from backend.models import Company, Document, DocumentChunk

DEFAULT_GOLD = Path(__file__).resolve().parents[2] / "evals" / "retrieval_gold.json"


# ---- metrics (pure) ----------------------------------------------------------

def recall_at(ranked: list[bool], k: int) -> float:
    """1 if any relevant result is in the top k (the question can be answered)."""
    return 1.0 if any(ranked[:k]) else 0.0


def reciprocal_rank(ranked: list[bool], k: int = 10) -> float:
    return next((1.0 / (i + 1) for i, hit in enumerate(ranked[:k]) if hit), 0.0)


def ndcg_at(ranked: list[bool], k: int, total_relevant: int) -> float:
    dcg = sum(1.0 / math.log2(i + 2) for i, hit in enumerate(ranked[:k]) if hit)
    ideal = sum(1.0 / math.log2(i + 2) for i in range(min(k, total_relevant)))
    return dcg / ideal if ideal else 0.0


@dataclass
class StrategyScore:
    name: str
    recall1: list[float] = field(default_factory=list)
    recall3: list[float] = field(default_factory=list)
    recall6: list[float] = field(default_factory=list)
    mrr: list[float] = field(default_factory=list)
    ndcg6: list[float] = field(default_factory=list)
    latency_ms: list[float] = field(default_factory=list)

    def add(self, ranked: list[bool], total_relevant: int, latency_ms: float) -> None:
        self.recall1.append(recall_at(ranked, 1))
        self.recall3.append(recall_at(ranked, 3))
        self.recall6.append(recall_at(ranked, 6))
        self.mrr.append(reciprocal_rank(ranked))
        self.ndcg6.append(ndcg_at(ranked, 6, total_relevant))
        self.latency_ms.append(latency_ms)

    def summary(self) -> dict:
        mean = lambda xs: round(sum(xs) / len(xs), 3) if xs else 0.0  # noqa: E731
        p50 = sorted(self.latency_ms)[len(self.latency_ms) // 2] if self.latency_ms else 0.0
        return {
            "strategy": self.name, "recall@1": mean(self.recall1), "recall@3": mean(self.recall3),
            "recall@6": mean(self.recall6), "mrr@10": mean(self.mrr), "ndcg@6": mean(self.ndcg6),
            "p50_ms": round(p50),
        }


# ---- harness -----------------------------------------------------------------

def is_relevant(content: str, answers: list[str]) -> bool:
    lowered = content.lower()
    return any(answer.lower() in lowered for answer in answers)


def _company_documents(session: Session, ticker: str) -> list[UUID]:
    return list(
        session.scalars(
            select(Document.id).join(Company, Company.id == Document.company_id)
            .where(Company.ticker == ticker, Document.indexed_at.is_not(None))
        )
    )


def _relevant_count(session: Session, document_ids: list[UUID], answers: list[str]) -> int:
    contents = session.scalars(select(DocumentChunk.content).where(DocumentChunk.document_id.in_(document_ids)))
    return sum(is_relevant(c, answers) for c in contents)


def evaluate(gold_path: Path, *, k: int, embed, reranker: Reranker, rerank_candidates: int | None = None) -> list[dict]:
    rerank_candidates = rerank_candidates or settings.rerank_candidates
    queries = json.loads(gold_path.read_text())["queries"]
    scores = {name: StrategyScore(name) for name in ("vector", "keyword", "hybrid_rrf", "hybrid_rerank")}
    embeddings = embed([q["query"] for q in queries])
    with SessionLocal() as session:
        for item, embedding in zip(queries, embeddings):
            document_ids = _company_documents(session, item["ticker"])
            company = session.scalar(select(Company).where(Company.ticker == item["ticker"]))
            names = [item["ticker"], company.name] if company else [item["ticker"]]
            total = _relevant_count(session, document_ids, item["answers"])
            if total == 0:
                raise ValueError(f"No chunk contains an answer for: {item['query']} ({item['ticker']})")

            def run(name: str, fn) -> None:
                started = time.perf_counter()
                results: list[RetrievedChunk] = fn()
                elapsed = (time.perf_counter() - started) * 1000
                scores[name].add([is_relevant(r.content, item["answers"]) for r in results[:10]], total, elapsed)

            args = dict(query_text=item["query"], query_embedding=embedding, document_ids=document_ids)
            run("vector", lambda: vector_search(session, **args, limit=10))
            run("keyword", lambda: keyword_search(session, **args, limit=10, exclude_terms=names))
            run("hybrid_rrf", lambda: hybrid_search(session, **args, limit=10, exclude_terms=names))
            run(
                "hybrid_rerank",
                lambda: rerank_chunks(
                    item["query"], hybrid_search(session, **args, limit=rerank_candidates, exclude_terms=names),
                    reranker, limit=10,
                ),
            )
    return [s.summary() for s in scores.values()]


def main(argv: list[str]) -> int:
    from backend.llm.client import get_llm_client

    gold = Path(next((a for a in argv if not a.startswith("--")), DEFAULT_GOLD))
    k = int(argv[argv.index("--k") + 1]) if "--k" in argv else 6
    client = get_llm_client()
    rows = evaluate(gold, k=k, embed=lambda texts: client.embed(texts, task="query"), reranker=get_reranker())
    header = f"{'strategy':<15}{'R@1':>7}{'R@3':>7}{'R@6':>7}{'MRR@10':>8}{'nDCG@6':>8}{'p50 ms':>8}"
    print(header)
    print("-" * len(header))
    for row in rows:
        print(
            f"{row['strategy']:<15}{row['recall@1']:>7.3f}{row['recall@3']:>7.3f}{row['recall@6']:>7.3f}"
            f"{row['mrr@10']:>8.3f}{row['ndcg@6']:>8.3f}{row['p50_ms']:>8}"
        )
    print(f"\n{len(json.loads(gold.read_text())['queries'])} queries · reranker: {get_reranker().name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
