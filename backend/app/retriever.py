"""Small in-memory vector retrieval used before introducing Milvus."""

from dataclasses import dataclass
from math import isfinite, sqrt
from typing import Sequence

from app.chunker import Chunk


@dataclass(frozen=True)
class RetrievalHit:
    """A child chunk and its cosine similarity to the query."""

    chunk: Chunk
    score: float


class InMemoryRetriever:
    """Rank child chunks by cosine similarity without an external vector store."""

    def __init__(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]]) -> None:
        if not chunks:
            raise ValueError("至少需要一个 chunk")
        if len(chunks) != len(vectors):
            raise ValueError("chunks 和 vectors 的数量必须一致")

        self._chunks = list(chunks)
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

    def search(self, query_vector: Sequence[float], top_k: int = 5) -> list[RetrievalHit]:
        """Return up to ``top_k`` chunks sorted from most to least similar."""
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")

        query = self._validate_vector(query_vector)
        if len(query) != self.dimension:
            raise ValueError("查询向量维度与索引维度不一致")
        query_norm = sqrt(sum(value * value for value in query))

        scored = [
            (
                index,
                sum(query_value * vector_value for query_value, vector_value in zip(query, vector))
                / (query_norm * sqrt(sum(value * value for value in vector))),
            )
            for index, vector in enumerate(self._vectors)
        ]
        scored.sort(key=lambda item: (-item[1], item[0]))
        return [
            RetrievalHit(chunk=self._chunks[index], score=score)
            for index, score in scored[:top_k]
        ]
