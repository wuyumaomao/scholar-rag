from __future__ import annotations

import pytest

from app.chunker import Chunk
from app.retriever import InMemoryRetriever


def make_chunk(
    chunk_id: str,
    *,
    parent_chunk_id: str | None = None,
    meta: dict[str, object] | None = None,
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        context=chunk_id,
        meta=meta or {},
        parent_chunk_id=parent_chunk_id,
    )


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


def test_search_filters_results_below_default_similarity_threshold() -> None:
    chunks = [make_chunk("high"), make_chunk("medium"), make_chunk("low")]
    retriever = InMemoryRetriever(
        chunks,
        [[1.0, 0.0], [0.8, 0.6], [0.6, 0.8]],
    )

    hits = retriever.search([1.0, 0.0], top_k=5)

    assert [hit.chunk.chunk_id for hit in hits] == ["high", "medium"]
    assert all(hit.score >= 0.7 for hit in hits)


def test_search_can_return_no_results_when_threshold_is_too_high() -> None:
    retriever = InMemoryRetriever([make_chunk("only")], [[1.0, 0.0]])

    hits = retriever.search([1.0, 0.0], top_k=5, min_score=1.01)

    assert hits == []


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


def test_search_expands_child_hits_to_unique_parents() -> None:
    parents = [make_chunk("parent-a"), make_chunk("parent-b")]
    children = [
        make_chunk("child-a-0", parent_chunk_id="parent-a"),
        make_chunk("child-a-1", parent_chunk_id="parent-a"),
        make_chunk("child-b-0", parent_chunk_id="parent-b"),
    ]
    retriever = InMemoryRetriever(
        children,
        [[1.0, 0.0], [0.99, 0.1], [0.8, 0.6]],
        parents=parents,
    )

    hits = retriever.search(
        [1.0, 0.0], top_k=2, child_top_k=3, expand_parents=True
    )

    assert [hit.chunk.chunk_id for hit in hits] == ["parent-a", "parent-b"]
    assert hits[0].score == pytest.approx(1.0)


def test_parent_expansion_preserves_parent_metadata() -> None:
    parent = make_chunk(
        "figure-parent",
        meta={"element_types": ["figure"], "image_path": "figures/page2.png"},
    )
    child = make_chunk("figure-child", parent_chunk_id="figure-parent")
    retriever = InMemoryRetriever([child], [[1.0, 0.0]], parents=[parent])

    hits = retriever.search([1.0, 0.0], top_k=1, expand_parents=True)

    assert hits[0].chunk.meta["image_path"] == "figures/page2.png"


def test_parent_expansion_requires_parent_chunks() -> None:
    retriever = InMemoryRetriever([make_chunk("child")], [[1.0, 0.0]])

    with pytest.raises(ValueError, match="parents"):
        retriever.search([1.0, 0.0], expand_parents=True)
