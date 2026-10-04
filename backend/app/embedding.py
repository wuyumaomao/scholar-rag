"""Generate dense vectors for retrieval text and user queries."""

from typing import Any


DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


class EmbeddingService:
    """Small adapter around Sentence Transformers for document and query text."""

    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL, *, model: Any = None) -> None:
        if not model_name.strip():
            raise ValueError("model_name 不能为空")
        self.model_name = model_name
        self._model = model

    @property
    def model(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "使用真实嵌入模型前，请安装 sentence-transformers"
                ) from exc
            self._model = SentenceTransformer(self.model_name)
        return self._model

    @property
    def dimension(self) -> int:
        dimension = self.model.get_sentence_embedding_dimension()
        if not isinstance(dimension, int) or dimension <= 0:
            raise RuntimeError("嵌入模型没有返回有效的向量维度")
        return dimension

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed a non-empty batch and return one normalized vector per text."""
        if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("texts 不能为空，且不能包含空文本")

        encoded = self.model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        vectors = encoded.tolist() if hasattr(encoded, "tolist") else encoded
        if len(vectors) != len(texts):
            raise RuntimeError("嵌入模型返回的向量数量与输入文本数量不一致")
        return [[float(value) for value in vector] for vector in vectors]

    def embed_query(self, query: str) -> list[float]:
        """Embed one non-empty user query."""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query 不能为空")
        vectors = self.embed_texts([query])
        return vectors[0]
