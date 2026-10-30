"""Second-stage reranking with a local cross-encoder (ADR 0007).

The first stage (hybrid RRF) is fast and recall-oriented: it scores the query and each passage
independently. A cross-encoder reads the query and a passage together, so it judges whether the
passage actually answers the question. It is too slow to run over every chunk, so it only
reorders the fused candidates.
"""
import logging
import math
import threading
from pathlib import Path
from typing import Protocol

from backend.core.config import settings

logger = logging.getLogger(__name__)

MODELS = {
    "minilm": "Xenova/ms-marco-MiniLM-L-6-v2",  # ~80 MB; best on our eval (ADR 0007)
    "jina-turbo": "jinaai/jina-reranker-v1-turbo-en",  # ~150 MB, 8k-token context; slower, no better here
}


class Reranker(Protocol):
    name: str

    def scores(self, query: str, passages: list[str]) -> list[float]: ...


class NoopReranker:
    """Keeps the first-stage order. Used when reranking is off or the model can't load."""

    name = "none"

    def scores(self, query: str, passages: list[str]) -> list[float]:
        return [1.0 - i / max(len(passages), 1) for i in range(len(passages))]


def windows(passage: str, size: int = 450, step: int = 300) -> list[str]:
    """Overlapping slices of a long chunk. MS MARCO cross-encoders are trained on ~60-word passages."""
    if len(passage) <= size:
        return [passage]
    return [passage[i : i + size] for i in range(0, max(len(passage) - size, 0) + step, step)]


class CrossEncoderReranker:
    """Scores each chunk by its best-matching window, so an answer late in a 2,200-char chunk still counts."""

    def __init__(self, key: str, cache_dir: str | Path):
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self.name = MODELS[key]
        self.model = TextCrossEncoder(model_name=self.name, cache_dir=str(cache_dir))
        self.lock = threading.Lock()  # ONNX sessions are thread-safe, but one at a time keeps memory flat

    def scores(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        spans = [(index, window) for index, passage in enumerate(passages) for window in windows(passage)]
        with self.lock:
            logits = list(self.model.rerank(query, [w for _, w in spans], batch_size=32))
        best = [float("-inf")] * len(passages)
        for (index, _), logit in zip(spans, logits):
            best[index] = max(best[index], float(logit))
        # Logits -> 0..1 so scores are comparable across queries and fit claim_evidence.relevance_score.
        return [1.0 / (1.0 + math.exp(-x)) for x in best]


_reranker: Reranker | None = None
_lock = threading.Lock()


def get_reranker() -> Reranker:
    """The configured reranker, loaded once per process. Never raises: falls back to no reranking."""
    global _reranker
    with _lock:
        if _reranker is None:
            if settings.reranker == "none":
                _reranker = NoopReranker()
            else:
                try:
                    _reranker = CrossEncoderReranker(
                        settings.reranker, Path(settings.data_cache_dir) / "models"
                    )
                except Exception:
                    logger.exception("reranker %s failed to load; continuing without reranking", settings.reranker)
                    _reranker = NoopReranker()
        return _reranker
