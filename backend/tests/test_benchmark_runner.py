import json
from pathlib import Path

from app.documents.pdf_parser import ParsedElement, ParsedPdf
from scripts import evaluate_benchmark


class RankingEmbedder:
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


def test_hybrid_benchmark_mode_scores_rrf_parent_order_against_dense_baseline(
    tmp_path: Path, monkeypatch
) -> None:
    elements = [
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
    ]
    monkeypatch.setattr(
        evaluate_benchmark,
        "parse_pdf",
        lambda _path, *, figure_dir: ParsedPdf(page_count=1, elements=elements),
    )
    monkeypatch.setattr(evaluate_benchmark, "EmbeddingService", RankingEmbedder)
    benchmark_path = tmp_path / "benchmark.jsonl"
    benchmark_path.write_text(
        json.dumps(
            {
                "id": "q001",
                "query": "architecture",
                "evidence": [{"element_ids": ["element-000002"]}],
            }
        ),
        encoding="utf-8",
    )
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"paper")

    dense_metrics, dense_cases = evaluate_benchmark.evaluate_file(
        benchmark_path,
        pdf_path,
        k=2,
        child_top_k=3,
        min_score=0.1,
        figure_root=tmp_path / "figures",
        cache_dir=tmp_path / "cache",
    )
    hybrid_metrics, hybrid_cases = evaluate_benchmark.evaluate_file(
        benchmark_path,
        pdf_path,
        k=2,
        child_top_k=3,
        min_score=0.1,
        figure_root=tmp_path / "figures",
        cache_dir=tmp_path / "cache",
        retrieval_mode="hybrid",
        rrf_k=60,
    )

    assert dense_cases[0]["retrieved_element_ids"][:2] == [
        "element-000001",
        "element-000002",
    ]
    assert dense_metrics.mrr == 0.5
    assert hybrid_cases[0]["retrieved_element_ids"][:2] == [
        "element-000002",
        "element-000003",
    ]
    assert hybrid_metrics.mrr == 1.0


def test_benchmark_counts_related_figure_evidence_added_to_body_context(
    tmp_path: Path, monkeypatch
) -> None:
    elements = [
        ParsedElement(
            element_id="element-000001",
            element_type="figure",
            docling_type="PictureItem",
            docling_label="picture",
            text="",
            page_num=1,
            order=2,
            bbox=None,
            related_ids=["element-000003", "element-000002"],
        ),
        ParsedElement(
            element_id="element-000002",
            element_type="paragraph",
            docling_type="TextItem",
            docling_label="text",
            text="dense-first The architecture is shown in Figure 5.",
            page_num=1,
            order=1,
            bbox=None,
            related_ids=["element-000001"],
        ),
        ParsedElement(
            element_id="element-000003",
            element_type="caption",
            docling_type="TextItem",
            docling_label="caption",
            text="Figure 5: Depth estimation architecture",
            page_num=1,
            order=3,
            bbox=None,
            related_ids=["element-000001"],
        ),
    ]
    monkeypatch.setattr(
        evaluate_benchmark,
        "parse_pdf",
        lambda _path, *, figure_dir: ParsedPdf(page_count=1, elements=elements),
    )
    monkeypatch.setattr(evaluate_benchmark, "EmbeddingService", RankingEmbedder)
    benchmark_path = tmp_path / "benchmark.jsonl"
    benchmark_path.write_text(
        json.dumps(
            {
                "id": "q-figure-5",
                "query": "architecture",
                "evidence": [
                    {"element_ids": ["element-000001", "element-000003"]}
                ],
            }
        ),
        encoding="utf-8",
    )
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"paper")

    metrics, cases = evaluate_benchmark.evaluate_file(
        benchmark_path,
        pdf_path,
        k=1,
        child_top_k=3,
        min_score=0.1,
        figure_root=tmp_path / "figures",
        cache_dir=tmp_path / "cache",
        retrieval_mode="hybrid-rerank",
        rrf_k=60,
        rerank_candidate_k=3,
        reranker=FakeReranker(),
    )

    assert cases[0]["retrieved_element_ids"] == [
        "element-000002",
        "element-000001",
        "element-000003",
    ]
    assert cases[0]["retrieved_element_groups"] == [
        ["element-000002", "element-000001", "element-000003"]
    ]
    assert metrics.recall == 1.0
    assert metrics.precision == 1.0
    assert metrics.mrr == 1.0


class FakeReranker:
    def rerank(self, query, candidates, *, top_k):
        return sorted(
            candidates,
            key=lambda hit: hit.chunk.chunk_id != "element-000002-parent",
        )[:top_k]


def test_hybrid_hyde_benchmark_keeps_original_query_for_bm25_and_reranking(
    tmp_path: Path, monkeypatch
) -> None:
    elements = [
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
    ]
    monkeypatch.setattr(
        evaluate_benchmark,
        "parse_pdf",
        lambda _path, *, figure_dir: ParsedPdf(page_count=1, elements=elements),
    )
    embedder_instances = []

    class RecordingEmbedder(RankingEmbedder):
        def __init__(self) -> None:
            self.queries: list[str] = []
            embedder_instances.append(self)

        def embed_query(self, query: str) -> list[float]:
            self.queries.append(query)
            return super().embed_query(query)

    monkeypatch.setattr(evaluate_benchmark, "EmbeddingService", RecordingEmbedder)
    original_bm25 = evaluate_benchmark.BM25Retriever
    bm25_queries: list[str] = []

    class RecordingBM25:
        def __init__(self, chunks) -> None:
            self.retriever = original_bm25(chunks)

        def search(self, query: str, *, top_k: int):
            bm25_queries.append(query)
            return self.retriever.search(query, top_k=top_k)

    monkeypatch.setattr(evaluate_benchmark, "BM25Retriever", RecordingBM25)
    benchmark_path = tmp_path / "benchmark.jsonl"
    benchmark_path.write_text(
        json.dumps(
            {
                "id": "q001",
                "query": "architecture",
                "evidence": [{"element_ids": ["element-000002"]}],
            }
        ),
        encoding="utf-8",
    )
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"paper")

    class FakeHyDE:
        def generate(self, query: str) -> str:
            assert query == "architecture"
            return "dense-first hypothetical paper passage"

    class RecordingReranker(FakeReranker):
        def __init__(self) -> None:
            self.queries: list[str] = []

        def rerank(self, query, candidates, *, top_k):
            self.queries.append(query)
            return super().rerank(query, candidates, top_k=top_k)

    reranker = RecordingReranker()
    evaluate_benchmark.evaluate_file(
        benchmark_path,
        pdf_path,
        k=1,
        child_top_k=3,
        min_score=0.1,
        figure_root=tmp_path / "figures",
        cache_dir=tmp_path / "cache",
        retrieval_mode="hybrid-rerank",
        rerank_candidate_k=3,
        reranker=reranker,
        use_hyde=True,
        hyde_generator=FakeHyDE(),
    )

    assert embedder_instances[0].queries == ["dense-first hypothetical paper passage"]
    assert bm25_queries == ["architecture"]
    assert reranker.queries == ["architecture"]


def test_evaluation_parser_has_explicit_hyde_switch() -> None:
    args = evaluate_benchmark.build_parser().parse_args(["--use-hyde"])

    assert args.use_hyde is True


def test_evaluation_parser_can_disable_persistent_cache() -> None:
    args = evaluate_benchmark.build_parser().parse_args(["--no-cache"])

    assert args.no_cache is True


def test_evaluate_file_reuses_persistent_parse_and_embedding_cache(
    tmp_path: Path, monkeypatch
) -> None:
    elements = [
        ParsedElement(
            element_id="element-000001",
            element_type="paragraph",
            docling_type="TextItem",
            docling_label="text",
            text="A cached benchmark paragraph.",
            page_num=1,
            order=1,
            bbox=None,
        )
    ]
    parser_calls = 0

    def parser(_path: Path, *, figure_dir: Path) -> ParsedPdf:
        nonlocal parser_calls
        parser_calls += 1
        return ParsedPdf(page_count=1, elements=elements)

    embed_calls = 0

    class CountingEmbedder(RankingEmbedder):
        model_name = "test-embedding-model"

        def embed_texts(self, texts: list[str]) -> list[list[float]]:
            nonlocal embed_calls
            embed_calls += 1
            return super().embed_texts(texts)

    monkeypatch.setattr(evaluate_benchmark, "parse_pdf", parser)
    monkeypatch.setattr(evaluate_benchmark, "EmbeddingService", CountingEmbedder)
    benchmark_path = tmp_path / "benchmark.jsonl"
    benchmark_path.write_text(
        json.dumps(
            {
                "id": "q001",
                "query": "cached benchmark",
                "evidence": [{"element_ids": ["element-000001"]}],
            }
        ),
        encoding="utf-8",
    )
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"paper")
    common = {
        "benchmark_path": benchmark_path,
        "pdf_path": tmp_path / "paper.pdf",
        "k": 1,
        "child_top_k": 1,
        "min_score": 0,
        "figure_root": tmp_path / "figures",
        "cache_dir": tmp_path / "cache",
    }
    Path(common["pdf_path"]).write_bytes(b"stable pdf")

    first_metrics, _ = evaluate_benchmark.evaluate_file(**common)
    second_metrics, _ = evaluate_benchmark.evaluate_file(**common)

    assert first_metrics == second_metrics
    assert parser_calls == 1
    assert embed_calls == 1


def test_hybrid_rerank_benchmark_mode_uses_reranked_parent_order(
    tmp_path: Path, monkeypatch
) -> None:
    elements = [
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
    ]
    monkeypatch.setattr(
        evaluate_benchmark,
        "parse_pdf",
        lambda _path, *, figure_dir: ParsedPdf(page_count=1, elements=elements),
    )
    monkeypatch.setattr(evaluate_benchmark, "EmbeddingService", RankingEmbedder)
    benchmark_path = tmp_path / "benchmark.jsonl"
    benchmark_path.write_text(
        json.dumps(
            {
                "id": "q001",
                "query": "architecture",
                "evidence": [{"element_ids": ["element-000002"]}],
            }
        ),
        encoding="utf-8",
    )
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"paper")

    metrics, cases = evaluate_benchmark.evaluate_file(
        benchmark_path,
        pdf_path,
        k=1,
        child_top_k=3,
        min_score=0.1,
        figure_root=tmp_path / "figures",
        cache_dir=tmp_path / "cache",
        retrieval_mode="hybrid-rerank",
        rrf_k=60,
        rerank_candidate_k=3,
        reranker=FakeReranker(),
    )

    assert cases[0]["retrieved_element_ids"] == ["element-000002"]
    assert metrics.mrr == 1.0
