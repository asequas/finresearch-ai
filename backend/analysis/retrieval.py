"""Hybrid retrieval in Postgres: pgvector cosine + full-text, fused with RRF (ADR 0006),
then an optional cross-encoder rerank of the fused candidates (ADR 0007)."""
import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PG_UUID
from sqlalchemy.orm import Session

from backend.models.document_chunk import EMBEDDING_DIMENSION

RRF_K = 60
# Tuned on evals/retrieval_gold.json (ADR 0007): keyword evidence counts half as much as vector evidence.
VECTOR_WEIGHT = 1.0
KEYWORD_WEIGHT = 0.5

# Words that appear in nearly every chunk of one company's filings, so they carry no signal for full-text search.
_FILLER = {"how", "what", "which", "why", "does", "do", "did", "is", "are", "was", "its", "the", "and", "much", "could", "affect"}


def keyword_query_text(question: str, exclude: Iterable[str] = ()) -> str:
    """Drop the company's own name/ticker and question filler before full-text search.

    "How do tariffs affect Costco?" should match passages about tariffs; in Costco's own 10-K,
    "Costco" matches every chunk and drowns the useful term.
    """
    excluded = {w.lower() for name in exclude for w in re.findall(r"\w+", name)}
    words = re.findall(r"[\w&+.'’-]+", question)
    kept = [w for w in words if re.sub(r"['’]s?$", "", w.lower()) not in excluded and w.lower() not in _FILLER]
    return " ".join(kept) or question

_HYBRID_SQL = text(
    """
    WITH vector_hits AS (
        SELECT id, row_number() OVER (ORDER BY embedding <=> :query_embedding) AS rank
        FROM document_chunks
        WHERE document_id = ANY(:document_ids) AND embedding IS NOT NULL
        ORDER BY embedding <=> :query_embedding
        LIMIT :candidates
    ),
    keyword_query AS (
        -- OR the query terms: a question rarely contains every word of the passage.
        SELECT NULLIF(replace(plainto_tsquery('english', :query_text)::text, '&', '|'), '')::tsquery AS q
    ),
    keyword_hits AS (
        -- Normalisation 32 (rank / (rank + 1)) keeps long chunks from winning on length alone.
        SELECT c.id, row_number() OVER (ORDER BY ts_rank_cd(c.search_vector, k.q, 32) DESC) AS rank
        FROM document_chunks c, keyword_query k
        WHERE c.document_id = ANY(:document_ids) AND k.q IS NOT NULL AND c.search_vector @@ k.q
        ORDER BY ts_rank_cd(c.search_vector, k.q, 32) DESC
        LIMIT :candidates
    )
    SELECT c.id, c.document_id, c.section, c.content,
           COALESCE(:vector_weight / (:rrf_k + v.rank), 0) + COALESCE(:keyword_weight / (:rrf_k + k.rank), 0) AS score,
           v.rank AS vector_rank, k.rank AS keyword_rank
    FROM document_chunks c
    LEFT JOIN vector_hits v ON v.id = c.id
    LEFT JOIN keyword_hits k ON k.id = c.id
    WHERE v.id IS NOT NULL OR k.id IS NOT NULL
    ORDER BY score DESC, c.id
    LIMIT :limit
    """
).bindparams(
    bindparam("query_embedding", type_=Vector(EMBEDDING_DIMENSION)),
    bindparam("document_ids", type_=ARRAY(PG_UUID(as_uuid=True))),
)


_VECTOR_SQL = text(
    """
    SELECT id, document_id, section, content, 1 - (embedding <=> :query_embedding) AS score,
           row_number() OVER (ORDER BY embedding <=> :query_embedding) AS vector_rank, NULL::bigint AS keyword_rank
    FROM document_chunks
    WHERE document_id = ANY(:document_ids) AND embedding IS NOT NULL
    ORDER BY embedding <=> :query_embedding
    LIMIT :limit
    """
).bindparams(
    bindparam("query_embedding", type_=Vector(EMBEDDING_DIMENSION)),
    bindparam("document_ids", type_=ARRAY(PG_UUID(as_uuid=True))),
)

_KEYWORD_SQL = text(
    """
    WITH keyword_query AS (
        SELECT NULLIF(replace(plainto_tsquery('english', :query_text)::text, '&', '|'), '')::tsquery AS q
    )
    SELECT c.id, c.document_id, c.section, c.content, ts_rank_cd(c.search_vector, k.q, 32) AS score,
           NULL::bigint AS vector_rank, row_number() OVER (ORDER BY ts_rank_cd(c.search_vector, k.q, 32) DESC) AS keyword_rank
    FROM document_chunks c, keyword_query k
    WHERE c.document_id = ANY(:document_ids) AND k.q IS NOT NULL AND c.search_vector @@ k.q
    ORDER BY ts_rank_cd(c.search_vector, k.q, 32) DESC, c.id
    LIMIT :limit
    """
).bindparams(bindparam("document_ids", type_=ARRAY(PG_UUID(as_uuid=True))))


@dataclass(frozen=True)
class RetrievedChunk:
    id: UUID
    document_id: UUID
    section: str | None
    content: str
    score: float
    vector_rank: int | None
    keyword_rank: int | None
    rerank_score: float | None = None


def hybrid_search(
    session: Session,
    *,
    query_text: str,
    query_embedding: list[float],
    document_ids: list[UUID],
    limit: int = 6,
    candidates: int = 40,
    exclude_terms: Iterable[str] = (),
) -> list[RetrievedChunk]:
    if not document_ids:
        return []
    rows = session.execute(
        _HYBRID_SQL,
        {
            "query_text": keyword_query_text(query_text, exclude_terms),
            "vector_weight": VECTOR_WEIGHT,
            "keyword_weight": KEYWORD_WEIGHT,
            "query_embedding": query_embedding,
            "document_ids": document_ids,
            "candidates": candidates,
            "limit": limit,
            "rrf_k": RRF_K,
        },
    )
    return [RetrievedChunk(**row._mapping) for row in rows]


def vector_search(
    session: Session, *, query_text: str, query_embedding: list[float], document_ids: list[UUID], limit: int = 6
) -> list[RetrievedChunk]:
    """Dense retrieval only (kept for evaluation and comparison)."""
    if not document_ids:
        return []
    rows = session.execute(
        _VECTOR_SQL, {"query_embedding": query_embedding, "document_ids": document_ids, "limit": limit}
    )
    return [RetrievedChunk(**row._mapping) for row in rows]


def keyword_search(
    session: Session, *, query_text: str, query_embedding: list[float], document_ids: list[UUID], limit: int = 6,
    exclude_terms: Iterable[str] = (),
) -> list[RetrievedChunk]:
    """Full-text retrieval only (kept for evaluation and comparison)."""
    if not document_ids:
        return []
    rows = session.execute(
        _KEYWORD_SQL,
        {"query_text": keyword_query_text(query_text, exclude_terms), "document_ids": document_ids, "limit": limit},
    )
    return [RetrievedChunk(**row._mapping) for row in rows]


# Equal weight for the cross-encoder's ranking and the first-stage ranking (ADR 0007): replacing the
# first stage outright raised Recall@1 but lost relevant passages from the top 6.
RERANK_WEIGHT = 1.0


def rerank_chunks(query: str, candidates: list[RetrievedChunk], reranker, *, limit: int) -> list[RetrievedChunk]:
    """Fuse the cross-encoder's ranking with the first-stage ranking (RRF); ties keep first-stage order."""
    if not candidates:
        return []
    scores = reranker.scores(query, [c.content for c in candidates])
    rerank_rank = {i: rank for rank, i in enumerate(sorted(range(len(candidates)), key=lambda i: -scores[i]), start=1)}
    fused = sorted(
        range(len(candidates)),
        key=lambda i: (-(1 / (RRF_K + i + 1) + RERANK_WEIGHT / (RRF_K + rerank_rank[i])), i),
    )
    return [replace(candidates[i], rerank_score=scores[i]) for i in fused[:limit]]


def retrieve(
    session: Session,
    *,
    query_text: str,
    query_embedding: list[float],
    document_ids: list[UUID],
    reranker,
    limit: int = 6,
    rerank_candidates: int = 30,
    exclude_terms: Iterable[str] = (),
) -> list[RetrievedChunk]:
    """Production path: hybrid RRF for recall, then the cross-encoder for precision."""
    fused = hybrid_search(
        session, query_text=query_text, query_embedding=query_embedding, document_ids=document_ids,
        limit=rerank_candidates, exclude_terms=exclude_terms,
    )
    return rerank_chunks(query_text, fused, reranker, limit=limit)
