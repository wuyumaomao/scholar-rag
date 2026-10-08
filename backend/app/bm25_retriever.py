"""Small in-memory BM25 retrieval for child chunks."""

from collections import Counter
from math import log
import re
from typing import Sequence

from app.chunker import Chunk
from app.retriever import RetrievalHit


_TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)


def _tokenize(text: str) -> list[str]:
    """Normalize text into lowercase word tokens for lexical matching."""
    return [match.group(0).casefold() for match in _TOKEN_PATTERN.finditer(text)]


class BM25Retriever:
    """Rank child chunks with the Okapi BM25 lexical scoring formula."""

    def __init__(
        self,
        chunks: Sequence[Chunk],
        *,
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        if not chunks:
            raise ValueError("至少需要一个 chunk")
        if k1 < 0:
            raise ValueError("k1 不能小于 0")
        if not 0 <= b <= 1:
            raise ValueError("b 必须在 0 到 1 之间")

        self._chunks = list(chunks)
        self.k1 = k1
        self.b = b
        self._tokenized_documents = [_tokenize(chunk.context) for chunk in self._chunks]
        self._document_lengths = [len(tokens) for tokens in self._tokenized_documents]
        self._average_document_length = sum(self._document_lengths) / len(self._chunks)

        document_frequency: Counter[str] = Counter()
        for tokens in self._tokenized_documents:
            document_frequency.update(set(tokens))
        document_count = len(self._chunks)
        self._idf = {
            token: log(1 + (document_count - frequency + 0.5) / (frequency + 0.5))
            for token, frequency in document_frequency.items()
        }

    def search(self, query: str, top_k: int = 5) -> list[RetrievalHit]:
        """Return up to ``top_k`` child chunks with a positive BM25 score."""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query 不能为空")
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")

        query_tokens = set(_tokenize(query))
        if not query_tokens:
            raise ValueError("query 必须包含可检索的词")

        scored: list[tuple[int, float]] = []
        for index, tokens in enumerate(self._tokenized_documents):
            frequencies = Counter(tokens)
            document_length = self._document_lengths[index]
            length_ratio = document_length / self._average_document_length
            score = 0.0
            for token in query_tokens:
                frequency = frequencies.get(token, 0)
                if frequency == 0:
                    continue
                numerator = frequency * (self.k1 + 1)
                denominator = frequency + self.k1 * (1 - self.b + self.b * length_ratio)
                score += self._idf[token] * numerator / denominator
            if score > 0:
                scored.append((index, score))

        scored.sort(key=lambda item: (-item[1], item[0]))
        return [
            RetrievalHit(chunk=self._chunks[index], score=score)
            for index, score in scored[:top_k]
        ]
