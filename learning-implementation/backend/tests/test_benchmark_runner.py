import json
from pathlib import Path

from app.pdf_parser import ParsedElement, ParsedPdf
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

    dense_metrics, dense_cases = evaluate_benchmark.evaluate_file(
        benchmark_path,
        tmp_path / "paper.pdf",
        k=2,
        child_top_k=3,
        min_score=0.1,
        figure_root=tmp_path / "figures",
    )
    hybrid_metrics, hybrid_cases = evaluate_benchmark.evaluate_file(
        benchmark_path,
        tmp_path / "paper.pdf",
        k=2,
        child_top_k=3,
        min_score=0.1,
        figure_root=tmp_path / "figures",
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
        tmp_path / "paper.pdf",
        k=1,
        child_top_k=3,
        min_score=0.1,
        figure_root=tmp_path / "figures",
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

    metrics, cases = evaluate_benchmark.evaluate_file(
        benchmark_path,
        tmp_path / "paper.pdf",
        k=1,
        child_top_k=3,
        min_score=0.1,
        figure_root=tmp_path / "figures",
        retrieval_mode="hybrid-rerank",
        rrf_k=60,
        rerank_candidate_k=3,
        reranker=FakeReranker(),
    )

    assert cases[0]["retrieved_element_ids"] == ["element-000002"]
    assert metrics.mrr == 1.0
