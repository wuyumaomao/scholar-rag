from pathlib import Path

from app.chunker import ChunkingResult
from app.pdf_parser import ParsedElement, ParsedPdf
from app.benchmark_cache import load_or_create_index


class CountingEmbedder:
    def __init__(self, model_name: str = "test-embedding-model") -> None:
        self.model_name = model_name
        self.calls = 0

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return [[float(index + 1), 1.0] for index, _ in enumerate(texts)]


def make_parsed_pdf() -> ParsedPdf:
    return ParsedPdf(
        page_count=1,
        elements=[
            ParsedElement(
                element_id="element-000001",
                element_type="paragraph",
                docling_type="TextItem",
                docling_label="text",
                text="A small cached paragraph.",
                page_num=1,
                order=1,
                bbox=None,
            )
        ],
    )


def test_cache_hit_reuses_parsed_document_and_document_vectors(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"pdf contents")
    parser_calls = 0

    def parser(path: Path, *, figure_dir: Path) -> ParsedPdf:
        nonlocal parser_calls
        parser_calls += 1
        return make_parsed_pdf()

    embedder = CountingEmbedder()
    kwargs = {
        "pdf_path": pdf_path,
        "figure_dir": tmp_path / "figures",
        "cache_dir": tmp_path / "cache",
        "embedder": embedder,
        "parser": parser,
    }

    first = load_or_create_index(**kwargs)
    second = load_or_create_index(**kwargs)

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert parser_calls == 1
    assert embedder.calls == 1
    assert isinstance(second.chunking, ChunkingResult)
    assert second.chunking.children[0].context == "A small cached paragraph."
    assert second.vectors == [[1.0, 1.0]]


def test_cache_rebuilds_when_pdf_content_or_embedding_model_changes(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"first pdf")
    parser_calls = 0

    def parser(path: Path, *, figure_dir: Path) -> ParsedPdf:
        nonlocal parser_calls
        parser_calls += 1
        return make_parsed_pdf()

    def load(model_name: str):
        return load_or_create_index(
            pdf_path,
            figure_dir=tmp_path / "figures",
            cache_dir=tmp_path / "cache",
            embedder=CountingEmbedder(model_name),
            parser=parser,
        )

    assert load("model-a").cache_hit is False
    pdf_path.write_bytes(b"changed pdf")
    assert load("model-a").cache_hit is False
    assert load("model-b").cache_hit is False
    assert parser_calls == 3


def test_corrupt_cache_is_rebuilt_instead_of_breaking_evaluation(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"pdf contents")
    parser_calls = 0

    def parser(path: Path, *, figure_dir: Path) -> ParsedPdf:
        nonlocal parser_calls
        parser_calls += 1
        return make_parsed_pdf()

    kwargs = {
        "pdf_path": pdf_path,
        "figure_dir": tmp_path / "figures",
        "cache_dir": tmp_path / "cache",
        "embedder": CountingEmbedder(),
        "parser": parser,
    }
    load_or_create_index(**kwargs)
    cache_file = next((tmp_path / "cache").glob("*.json.gz"))
    cache_file.write_bytes(b"not a gzip cache")

    result = load_or_create_index(**kwargs)

    assert result.cache_hit is False
    assert parser_calls == 2


def test_disabling_cache_always_rebuilds_without_writing_cache(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"pdf contents")
    parser_calls = 0

    def parser(path: Path, *, figure_dir: Path) -> ParsedPdf:
        nonlocal parser_calls
        parser_calls += 1
        return make_parsed_pdf()

    kwargs = {
        "pdf_path": pdf_path,
        "figure_dir": tmp_path / "figures",
        "cache_dir": tmp_path / "cache",
        "embedder": CountingEmbedder(),
        "parser": parser,
        "use_cache": False,
    }

    assert load_or_create_index(**kwargs).cache_hit is False
    assert load_or_create_index(**kwargs).cache_hit is False
    assert parser_calls == 2
    assert not (tmp_path / "cache").exists()
