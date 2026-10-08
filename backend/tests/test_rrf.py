from __future__ import annotations

import pytest

from app.chunker import Chunk
from app.retriever import RetrievalHit
from app.rrf import fuse_parent_hits


def make_chunk(chunk_id: str, parent_chunk_id: str | None = None) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        context=chunk_id,
        meta={},
        parent_chunk_id=parent_chunk_id,
    )


def test_rrf_deduplicates_children_before_fusing_parent_rankings() -> None:
    parents = [make_chunk("parent-a"), make_chunk("parent-b")]
    dense_hits = [
        RetrievalHit(make_chunk("a-child-0", "parent-a"), 0.9),
        RetrievalHit(make_chunk("a-child-1", "parent-a"), 0.8),
        RetrievalHit(make_chunk("b-child-0", "parent-b"), 0.7),
    ]
    bm25_hits = [
        RetrievalHit(make_chunk("b-child-0", "parent-b"), 3.0),
        RetrievalHit(make_chunk("a-child-0", "parent-a"), 2.0),
    ]

    results = fuse_parent_hits(dense_hits, bm25_hits, parents, top_k=2, rrf_k=60)

    assert [hit.chunk.chunk_id for hit in results] == ["parent-a", "parent-b"]
    assert results[0].score == pytest.approx(1 / 61 + 1 / 62)
    assert results[1].score == pytest.approx(1 / 63 + 1 / 61)


def test_rrf_limits_final_parent_results() -> None:
    parents = [make_chunk("parent-a"), make_chunk("parent-b")]
    dense_hits = [RetrievalHit(make_chunk("a-child", "parent-a"), 0.9)]
    bm25_hits = [RetrievalHit(make_chunk("b-child", "parent-b"), 3.0)]

    results = fuse_parent_hits(dense_hits, bm25_hits, parents, top_k=1)

    assert len(results) == 1


def test_rrf_weight_can_increase_bm25_influence() -> None:
    parents = [make_chunk("parent-a"), make_chunk("parent-b")]
    dense_hits = [
        RetrievalHit(make_chunk("a-child", "parent-a"), 0.9),
        RetrievalHit(make_chunk("b-child", "parent-b"), 0.8),
    ]
    bm25_hits = [
        RetrievalHit(make_chunk("b-child", "parent-b"), 3.0),
        RetrievalHit(make_chunk("a-child", "parent-a"), 2.0),
    ]

    results = fuse_parent_hits(
        dense_hits,
        bm25_hits,
        parents,
        top_k=2,
        rrf_k=1,
        bm25_weight=1.25,
    )

    assert [hit.chunk.chunk_id for hit in results] == ["parent-b", "parent-a"]
    assert results[0].score == pytest.approx(1 / 3 + 1.25 / 2)


def test_rrf_rejects_invalid_parameters() -> None:
    parents = [make_chunk("parent-a")]
    with pytest.raises(ValueError, match="top_k"):
        fuse_parent_hits([], [], parents, top_k=0)
    with pytest.raises(ValueError, match="rrf_k"):
        fuse_parent_hits([], [], parents, rrf_k=0)
    with pytest.raises(ValueError, match="bm25_weight"):
        fuse_parent_hits([], [], parents, bm25_weight=0)
