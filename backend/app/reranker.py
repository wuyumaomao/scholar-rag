"""Cross-encoder ranking for a small set of retrieved parent chunks."""

from __future__ import annotations

from dataclasses import replace
import math
from typing import Protocol, Sequence

from app.retriever import RetrievalHit


class _CrossEncoderModel(Protocol):
    def predict(self, pairs: list[tuple[str, str]]) -> Sequence[float]: ...


class CrossEncoderReranker:
    """Rerank candidates using query-text relevance scores.

    The sentence-transformers model is loaded lazily so importing the app or
    constructing a disabled retrieval service does not download model files.
    """

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        *,
        model: _CrossEncoderModel | None = None,
    ) -> None:
        if not model_name.strip():
            raise ValueError("reranker model 名称不能为空")
        self._model_name = model_name
        self._model = model

    def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievalHit],
        *,
        top_k: int,
    ) -> list[RetrievalHit]:
        """Return the highest-scoring candidates, preserving stable ties."""
        if not query.strip():
            raise ValueError("query 不能为空")
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")
        if not candidates:
            return []

        scores = self._get_model().predict(
            [(query, candidate.chunk.context) for candidate in candidates]
        )
        if len(scores) != len(candidates):
            raise ValueError("reranker 分数数量必须与候选数量一致")

        scored = []
        for original_position, (candidate, raw_score) in enumerate(
            zip(candidates, scores, strict=True)
        ):
            score = float(raw_score)
            if not math.isfinite(score):
                raise ValueError("reranker 分数必须是有限数值")
            scored.append((original_position, replace(candidate, score=score)))
        scored.sort(key=lambda item: (-item[1].score, item[0]))
        return [hit for _, hit in scored[:top_k]]

    def _get_model(self) -> _CrossEncoderModel:
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(self._model_name)
        return self._model
