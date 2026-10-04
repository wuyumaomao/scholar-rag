from __future__ import annotations

import pytest

from app.embedding import EmbeddingService


class FakeEmbeddingModel:
    def get_sentence_embedding_dimension(self) -> int:
        return 3

    def encode(
        self,
        texts: list[str],
        *,
        normalize_embeddings: bool,
        convert_to_numpy: bool,
    ) -> list[list[float]]:
        assert normalize_embeddings is True
        assert convert_to_numpy is True
        return [[float(len(text)), 1.0, 0.0] for text in texts]


def test_embed_texts_returns_one_normalized_vector_per_text() -> None:
    service = EmbeddingService(model=FakeEmbeddingModel())

    vectors = service.embed_texts(["first chunk", "second chunk"])

    assert vectors == [[11.0, 1.0, 0.0], [12.0, 1.0, 0.0]]
    assert service.dimension == 3


def test_embed_query_returns_one_vector() -> None:
    service = EmbeddingService(model=FakeEmbeddingModel())

    vector = service.embed_query("what is rag?")

    assert vector == [12.0, 1.0, 0.0]


@pytest.mark.parametrize("texts", [[], [""], ["  "]])
def test_embed_texts_rejects_empty_input(texts: list[str]) -> None:
    service = EmbeddingService(model=FakeEmbeddingModel())

    with pytest.raises(ValueError):
        service.embed_texts(texts)


def test_embed_query_rejects_blank_input() -> None:
    service = EmbeddingService(model=FakeEmbeddingModel())

    with pytest.raises(ValueError):
        service.embed_query("  ")
