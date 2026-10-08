"""Small in-memory vector retrieval used before introducing Milvus."""

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Sequence

from app.chunker import Chunk
from app.retrieval_filters import FilterInput, coerce_filters, matches_filters


DEFAULT_MIN_SCORE = 0.8


@dataclass(frozen=True)
class RetrievalHit:
    """A retrieved chunk and its cosine similarity to the query."""

    chunk: Chunk
    score: float


class InMemoryRetriever:
    """Rank child chunks and optionally expand hits to unique parents."""

    def __init__(
        self,
        chunks: Sequence[Chunk],
        vectors: Sequence[Sequence[float]],
        *,
        parents: Sequence[Chunk] | None = None,
    ) -> None:
        if not chunks:
            raise ValueError("至少需要一个 chunk")
        if len(chunks) != len(vectors):
            raise ValueError("chunks 和 vectors 的数量必须一致")

        self._chunks = list(chunks)
        self._parents_by_id = (
            {parent.chunk_id: parent for parent in parents}
            if parents is not None
            else None
        )
        self._vectors = [self._validate_vector(vector) for vector in vectors]
        self.dimension = len(self._vectors[0])
        if any(len(vector) != self.dimension for vector in self._vectors):
            raise ValueError("所有向量的维度必须一致")

    @staticmethod
    def _validate_vector(vector: Sequence[float]) -> tuple[float, ...]:
        values = tuple(float(value) for value in vector)
        if not values:
            raise ValueError("向量不能为空")
        if any(not isfinite(value) for value in values):
            raise ValueError("向量不能包含 NaN 或无穷大")
        norm = sqrt(sum(value * value for value in values))
        if norm == 0:
            raise ValueError("不能使用零向量")
        return values

    def search(
        self,
        query_vector: Sequence[float],
        top_k: int = 5,
        *,
        child_top_k: int | None = None,
        expand_parents: bool = False,
        min_score: float = DEFAULT_MIN_SCORE,
        filters: FilterInput = None,
    ) -> list[RetrievalHit]:
        """Search children, optionally returning unique parent chunks.

        ``top_k`` is the maximum final result count. Results below ``min_score``
        are discarded, so fewer than ``top_k`` results may be returned. When
        ``expand_parents`` is true,
        ``child_top_k`` controls how many child candidates are considered before
        duplicate parents are removed; by default it considers twice ``top_k``.
        """
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")
        if child_top_k is not None and child_top_k <= 0:
            raise ValueError("child_top_k 必须大于 0")
        if not isfinite(min_score):
            raise ValueError("min_score 必须是有限数字")
        if expand_parents and self._parents_by_id is None:
            raise ValueError("展开 parent 需要传入 parents")

        query = self._validate_vector(query_vector)
        if len(query) != self.dimension:
            raise ValueError("查询向量维度与索引维度不一致")
        query_norm = sqrt(sum(value * value for value in query))

        resolved_filters = coerce_filters(filters)
        if (
            resolved_filters.element_types
            or resolved_filters.page_from is not None
            or resolved_filters.page_to is not None
            or resolved_filters.section_path_prefix
        ):
            eligible_indices = [
                index
                for index, chunk in enumerate(self._chunks)
                if matches_filters(chunk.meta, resolved_filters)
            ]
        else:
            eligible_indices = range(len(self._chunks))
        scored = [
            (
                index,
                sum(
                    query_value * vector_value
                    for query_value, vector_value in zip(query, self._vectors[index])
                )
                / (
                    query_norm
                    * sqrt(sum(value * value for value in self._vectors[index]))
                ),
            )
            for index in eligible_indices
        ]
        scored.sort(key=lambda item: (-item[1], item[0]))
        child_hits = [
            RetrievalHit(chunk=self._chunks[index], score=score)
            for index, score in scored
            if score >= min_score
        ][: self._candidate_limit(top_k, child_top_k, expand_parents)]
        if not expand_parents:
            return child_hits[:top_k]
        return self._expand_to_parents(child_hits, top_k)

    @staticmethod
    def _candidate_limit(
        top_k: int,
        child_top_k: int | None,
        expand_parents: bool,
    ) -> int:
        if child_top_k is not None:
            return child_top_k
        return top_k * 2 if expand_parents else top_k

    def _expand_to_parents(
        self,
        child_hits: Sequence[RetrievalHit],
        top_k: int,
    ) -> list[RetrievalHit]:
        """Replace child hits with their parents and remove duplicate parents."""
        assert self._parents_by_id is not None
        expanded: list[RetrievalHit] = []
        seen_parent_ids: set[str] = set()

        for hit in child_hits:
            parent_id = hit.chunk.parent_chunk_id
            parent = self._parents_by_id.get(parent_id) if parent_id else None
            result_chunk = parent or hit.chunk
            if result_chunk.chunk_id in seen_parent_ids:
                continue
            seen_parent_ids.add(result_chunk.chunk_id)
            expanded.append(RetrievalHit(chunk=result_chunk, score=hit.score))
            if len(expanded) >= top_k:
                break

        return expanded
