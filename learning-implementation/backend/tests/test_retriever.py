from __future__ import annotations

import pytest

from app.chunker import Chunk
from app.retriever import InMemoryRetriever


def make_chunk(chunk_id: str) -> Chunk:
    return Chunk(chunk_id=chunk_id, context=chunk_id, meta={})


def test_search_returns_chunks_sorted_by_cosine_similarity() -> None:
    chunks = [make_chunk("first"), make_chunk("second"), make_chunk("third")]
    vectors = [[1.0, 0.0], [0.0, 1.0], [0.6, 0.8]]
    retriever = InMemoryRetriever(chunks, vectors)

    hits = retriever.search([0.8, 0.6], top_k=2)

    assert [hit.chunk.chunk_id for hit in hits] == ["third", "first"]
    assert hits[0].score == pytest.approx(0.96)
    assert hits[1].score == pytest.approx(0.8)


def test_search_limits_results_to_available_chunks() -> None:
    retriever = InMemoryRetriever([make_chunk("only")], [[1.0, 0.0]])

    hits = retriever.search([1.0, 0.0], top_k=10)

    assert len(hits) == 1
    assert hits[0].chunk.chunk_id == "only"


def test_constructor_rejects_mismatched_chunks_and_vectors() -> None:
    with pytest.raises(ValueError, match="数量"):
        InMemoryRetriever([make_chunk("one")], [])


def test_search_rejects_wrong_dimension_and_invalid_top_k() -> None:
    retriever = InMemoryRetriever([make_chunk("one")], [[1.0, 0.0]])

    with pytest.raises(ValueError, match="维度"):
        retriever.search([1.0], top_k=1)
    with pytest.raises(ValueError, match="top_k"):
        retriever.search([1.0, 0.0], top_k=0)


def test_retriever_rejects_zero_vectors() -> None:
    with pytest.raises(ValueError, match="零向量"):
        InMemoryRetriever([make_chunk("one")], [[0.0, 0.0]])
