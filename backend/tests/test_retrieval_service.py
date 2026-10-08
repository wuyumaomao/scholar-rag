from pathlib import Path

import pytest

from app.chunker import Chunk
from app.config import Settings
from app.pdf_parser import ParsedElement, ParsedPdf, ParsedProvenance
from app.retrieval_service import RetrievalService


class FakeEmbedder:
    def __init__(self) -> None:
        self.document_calls = 0

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.document_calls += 1
        return [
            [1.0, 0.0] if "architecture" in text.casefold() else [0.0, 1.0]
            for text in texts
        ]

    def embed_query(self, query: str) -> list[float]:
        return [1.0, 0.0] if "architecture" in query else [0.0, 1.0]


class LowSimilarityEmbedder(FakeEmbedder):
    def embed_query(self, query: str) -> list[float]:
        return [0.6, 0.8]


class HybridRankingEmbedder:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            if "dense-first" in text:
                vectors.append([1.0, 0.0])
            elif "dense-second" in text:
                vectors.append([0.9, 0.1])
            else:
                vectors.append([0.0, 1.0])
        return vectors

    def embed_query(self, query: str) -> list[float]:
        return [1.0, 0.0]


def parsed_pdf() -> ParsedPdf:
    source = ParsedElement(
        element_id="element-000001",
        element_type="paragraph",
        docling_type="TextItem",
        docling_label="text",
        text="The architecture uses a convolutional network.",
        page_num=1,
        order=1,
        bbox=(10.0, 700.0, 300.0, 650.0),
        provenance=[ParsedProvenance(1, (10.0, 700.0, 300.0, 650.0))],
        section_path=["Methods"],
    )
    return ParsedPdf(page_count=1, elements=[source])


def test_retrieval_service_returns_parent_context_and_caches_document_index(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"pdf")
    parsed_calls: list[tuple[Path, Path]] = []

    def parser(path: Path, *, figure_dir: Path) -> ParsedPdf:
        parsed_calls.append((path, figure_dir))
        return parsed_pdf()

    embedder = FakeEmbedder()
    service = RetrievalService(embedder=embedder, parser=parser)

    first = service.retrieve(
        "file-1", pdf_path, "Explain the architecture", tmp_path / "figures"
    )
    second = service.retrieve(
        "file-1", pdf_path, "Explain the architecture", tmp_path / "figures"
    )

    assert first[0].chunk.chunk_id == "element-000001-parent"
    assert first[0].chunk.context.endswith("The architecture uses a convolutional network.")
    assert first[0].chunk.meta["page_nums"] == [1]
    assert first[0].score == pytest.approx(2 / 61)
    assert second == first
    assert parsed_calls == [(pdf_path, tmp_path / "figures")]
    assert embedder.document_calls == 1


def test_retrieval_service_accepts_explicit_settings(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"pdf")
    service = RetrievalService(
        embedder=FakeEmbedder(),
        parser=lambda path, *, figure_dir: parsed_pdf(),
        settings=Settings(vlm_enabled=False),
    )

    assert service.retrieve("file-1", pdf_path, "architecture", tmp_path / "figures")


def test_retrieval_service_invalidates_cached_file_index(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"pdf")
    parse_count = 0

    def parser(path: Path, *, figure_dir: Path) -> ParsedPdf:
        nonlocal parse_count
        parse_count += 1
        return parsed_pdf()

    service = RetrievalService(embedder=FakeEmbedder(), parser=parser)
    service.retrieve("file-1", pdf_path, "architecture", tmp_path / "figures")
    service.invalidate("file-1")
    service.retrieve("file-1", pdf_path, "architecture", tmp_path / "figures")

    assert parse_count == 2


def test_retrieval_service_applies_similarity_threshold(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"pdf")
    service = RetrievalService(embedder=LowSimilarityEmbedder(), parser=lambda path, *, figure_dir: parsed_pdf())

    strict_threshold_hits = service.retrieve(
        "file-1", pdf_path, "architecture", tmp_path / "figures", min_score=0.7
    )
    permissive_threshold_hits = service.retrieve(
        "file-1", pdf_path, "architecture", tmp_path / "figures", min_score=0.5
    )

    # BM25 can retrieve the parent even when Dense filters it out; lowering the
    # Dense threshold adds a second RRF vote for that same parent.
    assert len(strict_threshold_hits) == 1
    assert strict_threshold_hits[0].score == pytest.approx(1 / 61)
    assert len(permissive_threshold_hits) == 1
    assert permissive_threshold_hits[0].score == pytest.approx(2 / 61)


def test_retrieval_service_uses_settings_for_omitted_search_defaults(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"pdf")
    service = RetrievalService(
        embedder=LowSimilarityEmbedder(),
        parser=lambda path, *, figure_dir: parsed_pdf(),
        settings=Settings(vlm_enabled=False, top_k=1, fetch_k=1, min_score=0.5),
    )

    assert len(service.retrieve("file-1", pdf_path, "architecture", tmp_path / "figures")) == 1


def test_retrieval_service_fuses_dense_and_bm25_parent_rankings(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"pdf")
    parsed = ParsedPdf(
        page_count=1,
        elements=[
            ParsedElement(
                element_id=f"element-{index:06d}",
                element_type="paragraph",
                docling_type="TextItem",
                docling_label="text",
                text=text,
                page_num=1,
                order=index,
                bbox=None,
            )
            for index, text in enumerate(
                [
                    "dense-first semantic result",
                    "architecture dense-second result",
                    "architecture lexical-third result",
                ],
                start=1,
            )
        ],
    )
    service = RetrievalService(
        embedder=HybridRankingEmbedder(),
        parser=lambda path, *, figure_dir: parsed,
        settings=Settings(
            fetch_k=3,
            top_k=3,
            min_score=0.1,
            rrf_k=60,
            vlm_enabled=False,
        ),
    )

    hits = service.retrieve("file-1", pdf_path, "architecture", tmp_path / "figures")

    assert [hit.chunk.chunk_id for hit in hits] == [
        "element-000002-parent",
        "element-000001-parent",
        "element-000003-parent",
    ]
    assert hits[0].score == pytest.approx(1 / 61 + 1 / 62)
    assert hits[1].score == pytest.approx(1 / 61)
    assert hits[2].score == pytest.approx(1 / 62)


class FakeReranker:
    def __init__(self) -> None:
        self.candidate_ids: list[str] = []
        self.top_k: int | None = None

    def rerank(self, query, candidates, *, top_k):
        self.candidate_ids = [hit.chunk.chunk_id for hit in candidates]
        self.top_k = top_k
        return sorted(
            candidates,
            key=lambda hit: not hit.chunk.context.startswith("dense-first"),
        )[:top_k]


def test_retrieval_service_reranks_rrf_candidates_before_final_top_k(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"pdf")
    parsed = ParsedPdf(
        page_count=1,
        elements=[
            ParsedElement(
                element_id=f"element-{index:06d}",
                element_type="paragraph",
                docling_type="TextItem",
                docling_label="text",
                text=text,
                page_num=1,
                order=index,
                bbox=None,
            )
            for index, text in enumerate(
                [
                    "dense-first semantic result",
                    "architecture dense-second result",
                    "architecture lexical-third result",
                ],
                start=1,
            )
        ],
    )
    reranker = FakeReranker()
    service = RetrievalService(
        embedder=HybridRankingEmbedder(),
        parser=lambda path, *, figure_dir: parsed,
        reranker=reranker,
        settings=Settings(
            fetch_k=3,
            top_k=1,
            min_score=0.1,
            rrf_k=60,
            rerank_candidate_k=3,
            vlm_enabled=False,
        ),
    )

    hits = service.retrieve(
        "file-1", pdf_path, "architecture", tmp_path / "figures"
    )

    assert len(reranker.candidate_ids) == 3
    assert reranker.top_k == 1
    assert hits[0].chunk.chunk_id == "element-000001-parent"


class FakeVisionService:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, str]] = []

    def describe_image(self, image_path: Path, caption: str = "") -> str:
        self.calls.append((image_path, caption))
        return "The figure shows an encoder-decoder architecture."


def test_retrieval_service_enriches_figure_context(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"pdf")
    image_path = tmp_path / "figure.png"
    image_path.write_bytes(b"png")
    figure = ParsedElement(
        element_id="element-000010",
        element_type="figure",
        docling_type="PictureItem",
        docling_label="picture",
        text="",
        page_num=2,
        order=10,
        bbox=(10.0, 700.0, 300.0, 400.0),
        related_ids=["element-000011"],
        image_path=str(image_path),
    )
    caption = ParsedElement(
        element_id="element-000011",
        element_type="caption",
        docling_type="TextItem",
        docling_label="caption",
        text="Figure 1: Architecture",
        page_num=2,
        order=11,
        bbox=(10.0, 390.0, 300.0, 370.0),
        related_ids=["element-000010"],
    )

    vision = FakeVisionService()
    service = RetrievalService(
        embedder=FakeEmbedder(),
        vision_service=vision,
        parser=lambda path, *, figure_dir: ParsedPdf(
            page_count=2, elements=[figure, caption]
        ),
    )

    first = service.retrieve("file-1", pdf_path, "architecture", tmp_path / "figures")
    second = service.retrieve("file-1", pdf_path, "architecture", tmp_path / "figures")

    assert first[0].chunk.context.endswith(
        "Image description: The figure shows an encoder-decoder architecture."
    )
    assert first[0].chunk.meta["image_description"] == (
        "The figure shows an encoder-decoder architecture."
    )
    assert second[0].chunk.context == first[0].chunk.context
    assert vision.calls == [
        (image_path, "Figure 1: Architecture"),
        (image_path, "Figure 1: Architecture"),
    ]
