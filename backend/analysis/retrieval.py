"""Hybrid retrieval in Postgres: pgvector cosine + full-text, fused with RRF (ADR 0006)."""
from dataclasses import dataclass
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PG_UUID
from sqlalchemy.orm import Session

from backend.models.document_chunk import EMBEDDING_DIMENSION

RRF_K = 60

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
        SELECT c.id, row_number() OVER (ORDER BY ts_rank_cd(c.search_vector, k.q) DESC) AS rank
        FROM document_chunks c, keyword_query k
        WHERE c.document_id = ANY(:document_ids) AND k.q IS NOT NULL AND c.search_vector @@ k.q
        ORDER BY ts_rank_cd(c.search_vector, k.q) DESC
        LIMIT :candidates
    )
    SELECT c.id, c.document_id, c.section, c.content,
           COALESCE(1.0 / (:rrf_k + v.rank), 0) + COALESCE(1.0 / (:rrf_k + k.rank), 0) AS score,
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


@dataclass(frozen=True)
class RetrievedChunk:
    id: UUID
    document_id: UUID
    section: str | None
    content: str
    score: float
    vector_rank: int | None
    keyword_rank: int | None


def hybrid_search(
    session: Session,
    *,
    query_text: str,
    query_embedding: list[float],
    document_ids: list[UUID],
    limit: int = 6,
    candidates: int = 40,
) -> list[RetrievedChunk]:
    if not document_ids:
        return []
    rows = session.execute(
        _HYBRID_SQL,
        {
            "query_text": query_text,
            "query_embedding": query_embedding,
            "document_ids": document_ids,
            "candidates": candidates,
            "limit": limit,
            "rrf_k": RRF_K,
        },
    )
    return [RetrievedChunk(**row._mapping) for row in rows]
