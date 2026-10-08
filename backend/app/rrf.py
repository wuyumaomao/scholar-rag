"""Rank fusion for dense and lexical child retrieval results."""

from typing import Sequence

from app.chunker import Chunk
from app.retriever import RetrievalHit


def _best_parent_ranks(
    hits: Sequence[RetrievalHit],
    parents_by_id: dict[str, Chunk],
) -> dict[str, tuple[int, Chunk]]:
    """Keep the best child rank for each parent in one retrieval channel."""
    best: dict[str, tuple[int, Chunk]] = {}
    for rank, hit in enumerate(hits, start=1):
        parent_id = hit.chunk.parent_chunk_id or hit.chunk.chunk_id
        parent = parents_by_id.get(parent_id, hit.chunk)
        if parent_id not in best:
            best[parent_id] = (rank, parent)
    return best


def fuse_parent_hits(
    dense_hits: Sequence[RetrievalHit],
    bm25_hits: Sequence[RetrievalHit],
    parents: Sequence[Chunk],
    *,
    top_k: int = 10,
    rrf_k: int = 60,
    bm25_weight: float = 1.0,
) -> list[RetrievalHit]:
    """Fuse dense and BM25 child rankings into unique parent hits with RRF.

    Each channel contributes at most one rank per parent. Dense contributes
    ``1 / (rrf_k + rank)`` and BM25 contributes the same value multiplied by
    ``bm25_weight``.
    """
    if top_k <= 0:
        raise ValueError("top_k 必须大于 0")
    if rrf_k <= 0:
        raise ValueError("rrf_k 必须大于 0")
    if bm25_weight <= 0:
        raise ValueError("bm25_weight 必须大于 0")

    parents_by_id = {parent.chunk_id: parent for parent in parents}
    channel_ranks = [
        (_best_parent_ranks(dense_hits, parents_by_id), 1.0),
        (_best_parent_ranks(bm25_hits, parents_by_id), bm25_weight),
    ]

    scores: dict[str, float] = {}
    result_chunks: dict[str, Chunk] = {}
    first_seen_order: dict[str, int] = {}
    order = 0
    for ranks, weight in channel_ranks:
        for parent_id, (rank, parent) in ranks.items():
            if parent_id not in first_seen_order:
                first_seen_order[parent_id] = order
                order += 1
            result_chunks[parent_id] = parent
            scores[parent_id] = (
                scores.get(parent_id, 0.0) + weight / (rrf_k + rank)
            )

    ranked_parent_ids = sorted(
        scores,
        key=lambda parent_id: (-scores[parent_id], first_seen_order[parent_id]),
    )
    return [
        RetrievalHit(chunk=result_chunks[parent_id], score=scores[parent_id])
        for parent_id in ranked_parent_ids[:top_k]
    ]
