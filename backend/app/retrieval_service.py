"""Build and query an in-memory retrieval index for uploaded PDFs."""

from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Callable

from app.chunker import Chunk, create_chunks
from app.embedding import EmbeddingService
from app.pdf_parser import ParsedPdf, parse_pdf
from app.retriever import InMemoryRetriever, RetrievalHit


@dataclass(frozen=True)
class _CachedIndex:
    file_signature: tuple[int, int]
    parents: list[Chunk]
    retriever: InMemoryRetriever | None


class RetrievalService:
    """Parse, embed, and search a PDF while caching its index in memory."""

    def __init__(
        self,
        *,
        embedder: EmbeddingService | None = None,
        parser: Callable[..., ParsedPdf] = parse_pdf,
    ) -> None:
        self._embedder = embedder or EmbeddingService()
        self._parser = parser
        self._indexes: dict[str, _CachedIndex] = {}
        self._lock = RLock()

    def retrieve(
        self,
        file_id: str,
        pdf_path: Path,
        query: str,
        figure_dir: Path,
        *,
        top_k: int = 5,
        child_top_k: int | None = None,
    ) -> list[RetrievalHit]:
        """Return unique parent hits for a query over one uploaded PDF."""
        if not query.strip():
            raise ValueError("query 不能为空")
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")
        if child_top_k is not None and child_top_k <= 0:
            raise ValueError("child_top_k 必须大于 0")

        index = self._get_index(file_id, pdf_path, figure_dir)
        if index.retriever is None:
            return []

        return index.retriever.search(
            self._embedder.embed_query(query),
            top_k=top_k,
            child_top_k=child_top_k,
            expand_parents=True,
        )

    def invalidate(self, file_id: str) -> None:
        """Remove a deleted or replaced PDF's in-memory index."""
        with self._lock:
            self._indexes.pop(file_id, None)

    def _get_index(self, file_id: str, pdf_path: Path, figure_dir: Path) -> _CachedIndex:
        stat = pdf_path.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        with self._lock:
            cached = self._indexes.get(file_id)
            if cached is not None and cached.file_signature == signature:
                return cached

            parsed_pdf = self._parser(pdf_path, figure_dir=figure_dir)
            chunking = create_chunks(parsed_pdf)
            retriever = None
            if chunking.children:
                vectors = self._embedder.embed_texts(
                    [chunk.context for chunk in chunking.children]
                )
                retriever = InMemoryRetriever(
                    chunking.children,
                    vectors,
                    parents=chunking.parents,
                )

            index = _CachedIndex(
                file_signature=signature,
                parents=chunking.parents,
                retriever=retriever,
            )
            self._indexes[file_id] = index
            return index
