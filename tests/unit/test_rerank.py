from uuid import uuid4

import pytest

from backend.analysis.rerank import NoopReranker, windows
from backend.analysis.retrieval import RetrievedChunk, rerank_chunks


def chunk(content: str) -> RetrievedChunk:
    return RetrievedChunk(id=uuid4(), document_id=uuid4(), section="mdna", content=content, score=0.0,
                          vector_rank=None, keyword_rank=None)


class ScoreByWord:
    name = "fake"

    def __init__(self, word: str):
        self.word = word

    def scores(self, query, passages):
        return [1.0 if self.word in p else 0.0 for p in passages]


def test_windows_cover_long_passages_with_overlap():
    text = "x" * 1000
    parts = windows(text, size=450, step=300)
    assert all(len(p) <= 450 for p in parts)
    assert sum(len(p) for p in parts) >= 1000
    assert windows("short", size=450) == ["short"]


def test_noop_reranker_keeps_first_stage_order():
    candidates = [chunk(f"passage {i}") for i in range(5)]
    assert [c.id for c in rerank_chunks("q", candidates, NoopReranker(), limit=5)] == [c.id for c in candidates]


def test_fusion_promotes_the_reranker_pick_without_dropping_first_stage_leaders():
    # RRF (k=60) moves a passage the cross-encoder likes up a few places, not from last to first:
    # that restraint is what kept Recall@6 when replacing the ranking outright lost it (ADR 0007).
    candidates = [chunk(f"generic passage {i}") for i in range(3)] + [chunk("the tariffs passage")] + [
        chunk(f"generic passage {i}") for i in range(3, 6)
    ]
    ranked = rerank_chunks("tariffs", candidates, ScoreByWord("tariffs"), limit=4)

    assert [c.content for c in ranked[:2]] == ["generic passage 0", "the tariffs passage"]  # 4th -> 2nd
    assert ranked[1].rerank_score == 1.0


@pytest.mark.model
def test_real_cross_encoder_prefers_the_answering_passage():
    from backend.analysis.rerank import CrossEncoderReranker

    reranker = CrossEncoderReranker("minilm", ".cache/finresearch/models")
    scores = reranker.scores(
        "How fast is Microsoft Cloud revenue growing?",
        ["Our headquarters are located in Redmond, Washington.", "Microsoft Cloud revenue increased 27% to $214.4 billion."],
    )
    assert scores[1] > scores[0]


def test_retrieval_metrics():
    from backend.evals.retrieval import ndcg_at, recall_at, reciprocal_rank

    ranked = [False, True, False, True]
    assert recall_at(ranked, 1) == 0.0 and recall_at(ranked, 2) == 1.0
    assert reciprocal_rank(ranked) == 0.5
    assert 0 < ndcg_at(ranked, 6, total_relevant=2) < 1
    assert ndcg_at([True, True], 6, total_relevant=2) == 1.0
