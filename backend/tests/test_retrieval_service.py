from pathlib import Path

from app.chunker import Chunk
from app.pdf_parser import ParsedElement, ParsedPdf, ParsedProvenance
from app.retrieval_service import RetrievalService


class FakeEmbedder:
    def __init__(self) -> None:
        self.document_calls = 0

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.document_calls += 1
        return [[1.0, 0.0] if "architecture" in text else [0.0, 1.0] for text in texts]

    def embed_query(self, query: str) -> list[float]:
        return [1.0, 0.0] if "architecture" in query else [0.0, 1.0]


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
    assert first[0].score == 1.0
    assert second == first
    assert parsed_calls == [(pdf_path, tmp_path / "figures")]
    assert embedder.document_calls == 1


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
