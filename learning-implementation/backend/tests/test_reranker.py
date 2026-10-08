import pytest

from app.documents.chunker import Chunk
from app.retrieval.reranker import CrossEncoderReranker
from app.retrieval.retriever import RetrievalHit


class FakeCrossEncoder:
    def __init__(self, scores: list[float]) -> None:
        self.scores = scores
        self.pairs: list[tuple[str, str]] = []

    def predict(self, pairs: list[tuple[str, str]]) -> list[float]:
        self.pairs = pairs
        return self.scores


def _hit(chunk_id: str, context: str, score: float) -> RetrievalHit:
    return RetrievalHit(
        chunk=Chunk(
            chunk_id=chunk_id,
            context=context,
            meta={},
            parent_chunk_id=None,
        ),
        score=score,
    )


def test_cross_encoder_reranks_candidates_and_limits_returned_results() -> None:
    model = FakeCrossEncoder([0.2, 0.9, 0.5])
    reranker = CrossEncoderReranker(model=model)
    candidates = [
        _hit("parent-a", "first context", 0.04),
        _hit("parent-b", "second context", 0.03),
        _hit("parent-c", "third context", 0.02),
    ]

    results = reranker.rerank("the query", candidates, top_k=2)

    assert [hit.chunk.chunk_id for hit in results] == ["parent-b", "parent-c"]
    assert [hit.score for hit in results] == [0.9, 0.5]
    assert model.pairs == [
        ("the query", "first context"),
        ("the query", "second context"),
        ("the query", "third context"),
    ]


def test_cross_encoder_rejects_a_score_count_mismatch() -> None:
    reranker = CrossEncoderReranker(model=FakeCrossEncoder([0.7]))

    with pytest.raises(ValueError, match="候选数量"):
        reranker.rerank(
            "query",
            [_hit("parent-a", "first", 0.04), _hit("parent-b", "second", 0.03)],
            top_k=1,
        )


def test_cross_encoder_rejects_non_finite_scores() -> None:
    reranker = CrossEncoderReranker(model=FakeCrossEncoder([float("nan")]))

    with pytest.raises(ValueError, match="有限数值"):
        reranker.rerank("query", [_hit("parent-a", "first", 0.04)], top_k=1)
