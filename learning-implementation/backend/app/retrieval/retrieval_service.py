"""Build and query an in-memory retrieval index for uploaded PDFs."""

from dataclasses import dataclass
import logging
from pathlib import Path
from threading import RLock
from typing import Callable

from app.documents.chunker import Chunk, create_chunks
from app.retrieval.bm25_retriever import BM25Retriever
from app.config import Settings
from app.retrieval.embedding import EmbeddingService
from app.retrieval.hyde import HyDEGenerator
from app.documents.pdf_parser import ParsedPdf, parse_pdf
from app.retrieval.retriever import InMemoryRetriever, RetrievalHit
from app.retrieval.retrieval_filters import FilterInput, coerce_filters
from app.retrieval.related_context import expand_related_figure_context
from app.retrieval.reranker import CrossEncoderReranker
from app.retrieval.rrf import fuse_parent_hits
from app.retrieval.vlm import VLMError, VisionService


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _CachedIndex:
    file_signature: tuple[int, int]
    parents: list[Chunk]
    dense_retriever: InMemoryRetriever | None
    bm25_retriever: BM25Retriever | None


class RetrievalService:
    """Parse, embed, and search a PDF while caching its index in memory."""

    def __init__(
        self,
        *,
        embedder: EmbeddingService | None = None,
        parser: Callable[..., ParsedPdf] = parse_pdf,
        vision_service: VisionService | None = None,
        reranker: CrossEncoderReranker | None = None,
        hyde_generator: HyDEGenerator | None = None,
        settings: Settings | None = None,
    ) -> None:
        if vision_service is not None and settings is not None:
            # An injected vision service already owns its configuration.
            # Accepting both would make the source of truth ambiguous.
            raise ValueError("vision_service 和 settings 不能同时传入")
        self._settings = settings or Settings.from_env()
        self._embedder = embedder or EmbeddingService(settings=self._settings)
        self._parser = parser
        self._vision_service = vision_service or VisionService(settings=self._settings)
        self._reranker = reranker
        self._hyde_generator = hyde_generator or HyDEGenerator(settings=self._settings)
        if self._reranker is None and self._settings.reranker_enabled:
            self._reranker = CrossEncoderReranker(
                model_name=self._settings.reranker_model
            )
        self._indexes: dict[str, _CachedIndex] = {}
        self._lock = RLock()

    def retrieve(
        self,
        file_id: str,
        pdf_path: Path,
        query: str,
        figure_dir: Path,
        *,
        top_k: int | None = None,
        child_top_k: int | None = None,
        min_score: float | None = None,
        use_hyde: bool = False,
        filters: FilterInput = None,
    ) -> list[RetrievalHit]:
        """Return unique parent hits for a query over one uploaded PDF."""
        resolved_top_k = self._settings.top_k if top_k is None else top_k
        resolved_child_top_k = (
            self._settings.fetch_k if child_top_k is None else child_top_k
        )
        resolved_min_score = (
            self._settings.min_score if min_score is None else min_score
        )
        if not query.strip():
            raise ValueError("query 不能为空")
        if resolved_top_k <= 0:
            raise ValueError("top_k 必须大于 0")
        if resolved_child_top_k <= 0:
            raise ValueError("child_top_k 必须大于 0")

        dense_query = query
        if use_hyde:
            if not self._settings.llm_enabled:
                raise ValueError("启用 HyDE 需要设置 LLM_ENABLED=true")
            if not self._settings.llm_base_url:
                raise ValueError("启用 HyDE 需要配置 LLM_BASE_URL")
            if not self._settings.llm_model:
                raise ValueError("启用 HyDE 需要配置 LLM_MODEL")
            try:
                dense_query = self._hyde_generator.generate(query)
            except Exception as exc:
                logger.warning("HyDE generation failed; using original query: %s", exc)
                dense_query = query

        index = self._get_index(file_id, pdf_path, figure_dir)
        if index.dense_retriever is None or index.bm25_retriever is None:
            return []

        dense_hits = index.dense_retriever.search(
            self._embedder.embed_query(dense_query),
            top_k=resolved_child_top_k,
            min_score=resolved_min_score,
            filters=filters,
        )
        bm25_hits = index.bm25_retriever.search(
            query,
            top_k=resolved_child_top_k,
            filters=filters,
        )
        parent_candidate_k = resolved_top_k
        if self._reranker is not None:
            parent_candidate_k = max(
                resolved_top_k, self._settings.rerank_candidate_k
            )
        hits = fuse_parent_hits(
            dense_hits,
            bm25_hits,
            index.parents,
            top_k=parent_candidate_k,
            rrf_k=self._settings.rrf_k,
            bm25_weight=self._settings.bm25_weight,
        )
        if self._reranker is not None:
            hits = self._reranker.rerank(query, hits, top_k=resolved_top_k)
        return expand_related_figure_context(
            hits,
            index.parents,
            describe_image=self._describe_image,
        )

    def _describe_image(self, image_path: Path, caption: str) -> str:
        """Return a best-effort VLM description without breaking text retrieval."""
        try:
            return self._vision_service.describe_image(image_path, caption)
        except (OSError, VLMError) as exc:
            logger.warning("VLM figure description skipped for %s: %s", image_path, exc)
            return ""

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
            dense_retriever = None
            bm25_retriever = None
            if chunking.children:
                vectors = self._embedder.embed_texts(
                    [chunk.context for chunk in chunking.children]
                )
                dense_retriever = InMemoryRetriever(
                    chunking.children,
                    vectors,
                )
                bm25_retriever = BM25Retriever(chunking.children)

            index = _CachedIndex(
                file_signature=signature,
                parents=chunking.parents,
                dense_retriever=dense_retriever,
                bm25_retriever=bm25_retriever,
            )
            self._indexes[file_id] = index
            return index
