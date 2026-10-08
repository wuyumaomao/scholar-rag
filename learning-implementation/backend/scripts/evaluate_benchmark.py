"""Evaluate the learning-version dense baseline or Dense+BM25+RRF retrieval."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.chunker import create_chunks
from app.bm25_retriever import BM25Retriever
from app.embedding import EmbeddingService
from app.evaluation import (
    DatasetMetrics,
    evidence_element_ids,
    evaluate_ranked_groups,
    retrieval_element_groups_from_metadata,
    retrieval_element_ids_from_metadata,
)
from app.pdf_parser import parse_pdf
from app.retriever import DEFAULT_MIN_SCORE, InMemoryRetriever
from app.reranker import CrossEncoderReranker
from app.rrf import fuse_parent_hits
from app.config import Settings


def load_cases(path: Path) -> list[dict[str, Any]]:
    """Read and validate the JSON objects in one JSONL benchmark file."""
    cases: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path.name}:{line_number} 必须是 JSON 对象")
        if not isinstance(value.get("query"), str) or not value["query"].strip():
            raise ValueError(f"{path.name}:{line_number} 缺少有效 query")
        if not isinstance(value.get("evidence"), list):
            raise ValueError(f"{path.name}:{line_number} 缺少 evidence 数组")
        cases.append(value)
    if not cases:
        raise ValueError(f"benchmark 文件为空: {path}")
    return cases


def find_pdf(pdf_dir: Path, source_pdf: str) -> Path | None:
    """Find a source PDF by exact name under the configured PDF directory."""
    direct = pdf_dir / source_pdf
    if direct.is_file():
        return direct
    matches = list(pdf_dir.rglob(source_pdf))
    return matches[0] if matches else None


def evaluate_file(
    benchmark_path: Path,
    pdf_path: Path,
    *,
    k: int,
    child_top_k: int | None,
    min_score: float,
    figure_root: Path,
    retrieval_mode: str = "dense",
    rrf_k: int = 60,
    rerank_candidate_k: int | None = None,
    reranker: CrossEncoderReranker | None = None,
    reranker_model: str | None = None,
) -> tuple[DatasetMetrics, list[dict[str, Any]]]:
    """Build an index and evaluate dense, hybrid, or hybrid-reranked retrieval."""
    if retrieval_mode not in {"dense", "hybrid", "hybrid-rerank"}:
        raise ValueError("retrieval_mode 必须是 dense、hybrid 或 hybrid-rerank")
    if rrf_k <= 0:
        raise ValueError("rrf_k 必须大于 0")
    if rerank_candidate_k is not None and rerank_candidate_k <= 0:
        raise ValueError("rerank_candidate_k 必须大于 0")
    if child_top_k is not None and child_top_k <= 0:
        raise ValueError("child_top_k 必须大于 0")
    cases = load_cases(benchmark_path)
    parsed_pdf = parse_pdf(
        pdf_path,
        figure_dir=figure_root / pdf_path.stem,
    )
    chunking = create_chunks(parsed_pdf)
    if not chunking.children:
        raise ValueError(f"没有可检索的 child chunk: {pdf_path}")

    embedder = EmbeddingService()
    vectors = embedder.embed_texts([child.context for child in chunking.children])
    retriever = InMemoryRetriever(chunking.children, vectors, parents=chunking.parents)
    is_hybrid = retrieval_mode in {"hybrid", "hybrid-rerank"}
    is_reranked = retrieval_mode == "hybrid-rerank"
    bm25_retriever = BM25Retriever(chunking.children) if is_hybrid else None
    hybrid_candidate_k = (
        child_top_k if child_top_k is not None else Settings.from_env().fetch_k
    )
    settings = Settings.from_env() if is_reranked else None
    resolved_rerank_candidate_k = (
        rerank_candidate_k
        if rerank_candidate_k is not None
        else settings.rerank_candidate_k if settings is not None else 10
    )
    active_reranker = reranker
    if is_reranked and active_reranker is None:
        active_reranker = CrossEncoderReranker(
            model_name=(
                reranker_model
                or settings.reranker_model
                if settings is not None
                else reranker_model or Settings.reranker_model
            )
        )

    case_reports: list[dict[str, Any]] = []
    scores = []
    for case in cases:
        query_vector = embedder.embed_query(case["query"])
        if retrieval_mode == "dense":
            hits = retriever.search(
                query_vector,
                top_k=k,
                child_top_k=child_top_k,
                expand_parents=True,
                min_score=min_score,
            )
        else:
            dense_hits = retriever.search(
                query_vector,
                top_k=hybrid_candidate_k,
                min_score=min_score,
            )
            assert bm25_retriever is not None
            bm25_hits = bm25_retriever.search(
                case["query"], top_k=hybrid_candidate_k
            )
            hits = fuse_parent_hits(
                dense_hits,
                bm25_hits,
                chunking.parents,
                top_k=(
                    max(k, resolved_rerank_candidate_k)
                    if is_reranked
                    else k
                ),
                rrf_k=rrf_k,
            )
            if active_reranker is not None:
                hits = active_reranker.rerank(case["query"], hits, top_k=k)
        ranked_groups = retrieval_element_groups_from_metadata(
            [hit.chunk.meta for hit in hits]
        )
        ranked_ids = retrieval_element_ids_from_metadata([hit.chunk.meta for hit in hits])
        score = evaluate_ranked_groups(
            ranked_groups,
            evidence_element_ids(case),
            k=k,
        )
        scores.append(score)
        case_reports.append(
            {
                "id": case.get("id", ""),
                "query": case["query"],
                "retrieved_element_ids": ranked_ids,
                "retrieved_element_groups": ranked_groups,
                "recall": score.recall,
                "precision": score.precision,
                "precision_returned": score.precision_returned,
                "reciprocal_rank": score.reciprocal_rank,
            }
        )

    count = len(scores)
    metrics = DatasetMetrics(
        case_count=count,
        recall=sum(score.recall for score in scores) / count,
        precision=sum(score.precision for score in scores) / count,
        precision_returned=sum(score.precision_returned for score in scores) / count,
        mrr=sum(score.reciprocal_rank for score in scores) / count,
    )
    return metrics, case_reports


def _metrics_dict(metrics: DatasetMetrics) -> dict[str, float | int]:
    return {
        "case_count": metrics.case_count,
        "recall_at_k": metrics.recall,
        "precision_at_k": metrics.precision,
        "precision_returned": metrics.precision_returned,
        "mrr": metrics.mrr,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--benchmark-dir",
        type=Path,
        default=PROJECT_DIR / "evaluation-dataset",
    )
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        default=PROJECT_DIR,
        help="包含 benchmark source_pdf 的目录，会递归查找",
    )
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--child-top-k", type=int, default=None)
    parser.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    parser.add_argument(
        "--retrieval-mode",
        choices=("dense", "hybrid", "hybrid-rerank"),
        default="dense",
        help="dense 保持旧基线；hybrid 使用 Dense+BM25+RRF；hybrid-rerank 在 RRF 后重排",
    )
    parser.add_argument("--rrf-k", type=int, default=60)
    parser.add_argument("--rerank-candidate-k", type=int, default=None)
    parser.add_argument("--reranker-model", default=None)
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_DIR / "evaluation-results.json",
    )
    args = parser.parse_args()
    if args.k <= 0:
        parser.error("--k 必须大于 0")
    if args.child_top_k is not None and args.child_top_k <= 0:
        parser.error("--child-top-k 必须大于 0")
    if args.rrf_k <= 0:
        parser.error("--rrf-k 必须大于 0")
    if args.rerank_candidate_k is not None and args.rerank_candidate_k <= 0:
        parser.error("--rerank-candidate-k 必须大于 0")
    if not -1 <= args.min_score <= 1:
        parser.error("--min-score 必须在 -1 到 1 之间")
    if not args.benchmark_dir.is_dir():
        parser.error(f"benchmark 目录不存在: {args.benchmark_dir}")
    if not args.pdf_dir.is_dir():
        parser.error(f"PDF 目录不存在: {args.pdf_dir}")

    records: list[dict[str, Any]] = []
    all_cases: list[dict[str, Any]] = []
    all_ranked_groups: list[list[list[str]]] = []
    effective_child_top_k = args.child_top_k
    if args.retrieval_mode in {"hybrid", "hybrid-rerank"} and effective_child_top_k is None:
        effective_child_top_k = Settings.from_env().fetch_k
    effective_settings = (
        Settings.from_env()
        if args.retrieval_mode in {"hybrid", "hybrid-rerank"}
        else Settings()
    )
    effective_rerank_candidate_k = args.rerank_candidate_k
    if args.retrieval_mode == "hybrid-rerank" and effective_rerank_candidate_k is None:
        effective_rerank_candidate_k = effective_settings.rerank_candidate_k
    run_reranker = None
    if args.retrieval_mode == "hybrid-rerank":
        run_reranker = CrossEncoderReranker(
            model_name=args.reranker_model or effective_settings.reranker_model
        )
    for benchmark_path in sorted(args.benchmark_dir.glob("*.jsonl")):
        cases = load_cases(benchmark_path)
        source_pdf = str(cases[0].get("source_pdf", ""))
        pdf_path = find_pdf(args.pdf_dir, source_pdf) if source_pdf else None
        if pdf_path is None:
            records.append(
                {
                    "benchmark_file": benchmark_path.name,
                    "source_pdf": source_pdf,
                    "status": "skipped_missing_pdf",
                    "case_count": len(cases),
                }
            )
            continue

        metrics, case_reports = evaluate_file(
            benchmark_path,
            pdf_path,
            k=args.k,
            child_top_k=effective_child_top_k,
            min_score=args.min_score,
            figure_root=BACKEND_DIR / "data" / "figures" / "benchmark",
            retrieval_mode=args.retrieval_mode,
            rrf_k=args.rrf_k,
            rerank_candidate_k=effective_rerank_candidate_k,
            reranker=run_reranker,
            reranker_model=args.reranker_model,
        )
        records.append(
            {
                "benchmark_file": benchmark_path.name,
                "source_pdf": source_pdf,
                "pdf_path": str(pdf_path),
                "status": "ok",
                "metrics": _metrics_dict(metrics),
                "cases": case_reports,
            }
        )
        all_cases.extend(cases)
        all_ranked_groups.extend(
            [case_report["retrieved_element_groups"] for case_report in case_reports]
        )

    overall = None
    if all_cases:
        overall_metrics = []
        for case, ranked_groups in zip(all_cases, all_ranked_groups):
            overall_metrics.append(
                evaluate_ranked_groups(
                    ranked_groups, evidence_element_ids(case), k=args.k
                )
            )
        count = len(overall_metrics)
        overall = {
            "case_count": count,
            "recall_at_k": sum(item.recall for item in overall_metrics) / count,
            "precision_at_k": sum(item.precision for item in overall_metrics) / count,
            "precision_returned": sum(
                item.precision_returned for item in overall_metrics
            )
            / count,
            "mrr": sum(item.reciprocal_rank for item in overall_metrics) / count,
        }

    report = {
        "k": args.k,
        "retrieval_mode": args.retrieval_mode,
        "child_top_k": effective_child_top_k,
        "min_score": args.min_score,
        "rrf_k": args.rrf_k if args.retrieval_mode != "dense" else None,
        "rerank_candidate_k": effective_rerank_candidate_k,
        "reranker_model": (
            args.reranker_model or effective_settings.reranker_model
            if args.retrieval_mode == "hybrid-rerank"
            else None
        ),
        "metrics_definition": {
            "recall_at_k": "命中的 gold element 数 / gold element 总数",
            "precision_at_k": "Top-k 中命中的 parent element 数 / k",
            "precision_returned": "实际返回结果中命中的 parent element 数 / 实际返回结果数",
            "mrr": "Top-k 内第一个命中 gold element 的排名倒数的宏平均",
        },
        "overall": overall,
        "datasets": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ok_count = sum(record["status"] == "ok" for record in records)
    skipped_count = len(records) - ok_count
    print(f"完成 {ok_count} 个数据集，跳过 {skipped_count} 个缺少 PDF 的数据集")
    if overall is not None:
        print(
            f"Overall ({overall['case_count']} cases): "
            f"Recall@{args.k}={overall['recall_at_k']:.4f}, "
            f"Precision@{args.k}={overall['precision_at_k']:.4f}, "
            f"Precision@returned={overall['precision_returned']:.4f}, "
            f"MRR={overall['mrr']:.4f}"
        )
    print(f"报告已写入: {args.output}")


if __name__ == "__main__":
    main()
