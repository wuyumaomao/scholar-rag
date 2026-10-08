from __future__ import annotations

import pytest

from app.bm25_retriever import BM25Retriever
from app.chunker import Chunk


def make_chunk(chunk_id: str, context: str) -> Chunk:
    return Chunk(chunk_id=chunk_id, context=context, meta={})


def test_search_ranks_documents_by_lexical_query_match() -> None:
    chunks = [
        make_chunk("figure", "Depth estimation from endoscopy images"),
        make_chunk("depth", "Depth estimation uses a convolutional network"),
        make_chunk("unrelated", "The dataset contains synthetic colon images"),
    ]
    retriever = BM25Retriever(chunks)

    hits = retriever.search("endoscopy depth", top_k=2)

    assert [hit.chunk.chunk_id for hit in hits] == ["figure", "depth"]
    assert hits[0].score > hits[1].score > 0


def test_search_tokenization_ignores_case_and_punctuation() -> None:
    retriever = BM25Retriever(
        [
            make_chunk("match", "CNN-CRF depth estimation."),
            make_chunk("other", "A different method."),
        ]
    )

    hits = retriever.search("cnn crf", top_k=1)

    assert [hit.chunk.chunk_id for hit in hits] == ["match"]


def test_search_rejects_empty_query_and_invalid_top_k() -> None:
    retriever = BM25Retriever([make_chunk("one", "one document")])

    with pytest.raises(ValueError, match="query"):
        retriever.search("   ")
    with pytest.raises(ValueError, match="top_k"):
        retriever.search("document", top_k=0)


def test_search_returns_empty_for_query_without_known_terms() -> None:
    retriever = BM25Retriever([make_chunk("one", "one document")])

    assert retriever.search("unknown term", top_k=5) == []
