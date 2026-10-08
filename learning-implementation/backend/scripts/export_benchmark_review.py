"""Export ranked retrieval results and gold evidence for manual review."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.chunker import create_chunks
from app.embedding import EmbeddingService
from app.evaluation import (
    evidence_element_ids,
    evaluate_ranked_groups,
    retrieval_element_groups_from_metadata,
    retrieval_element_ids_from_metadata,
)
from app.pdf_parser import parse_pdf
from app.retriever import DEFAULT_MIN_SCORE, InMemoryRetriever
from scripts.evaluate_benchmark import load_cases


def _fenced_text(text: str) -> str:
    """Put arbitrary extracted text in a Markdown code fence."""
    fence = "````" if "```" in text else "```"
    return f"{fence}text\n{text}\n{fence}"


def export_review(
    benchmark_path: Path,
    pdf_path: Path,
    output_path: Path,
    *,
    k: int,
    child_top_k: int | None,
    min_score: float,
) -> None:
    cases = load_cases(benchmark_path)
    parsed_pdf = parse_pdf(
        pdf_path,
        figure_dir=BACKEND_DIR / "data" / "figures" / "benchmark" / pdf_path.stem,
    )
    chunks = create_chunks(parsed_pdf)
    embedder = EmbeddingService()
    vectors = embedder.embed_texts([child.context for child in chunks.children])
    retriever = InMemoryRetriever(chunks.children, vectors, parents=chunks.parents)

    lines = [
        f"# Retrieval Review: {pdf_path.name}",
        "",
        f"- Benchmark: `{benchmark_path}`",
        f"- PDF: `{pdf_path}`",
        f"- k: `{k}`",
        f"- child_top_k: `{child_top_k}`",
        f"- min_score: `{min_score}`",
        "- 检索结果是 parent；source element ID 用于和 gold evidence 对齐。",
        "",
    ]
    all_scores = []

    for case_number, case in enumerate(cases, 1):
        hits = retriever.search(
            embedder.embed_query(case["query"]),
            top_k=k,
            child_top_k=child_top_k,
            expand_parents=True,
            min_score=min_score,
        )
        ranked_groups = retrieval_element_groups_from_metadata(
            [hit.chunk.meta for hit in hits]
        )
        ranked_ids = retrieval_element_ids_from_metadata([hit.chunk.meta for hit in hits])
        gold_ids = evidence_element_ids(case)
        score = evaluate_ranked_groups(ranked_groups, gold_ids, k=k)
        all_scores.append(score)

        lines.extend(
            [
                f"## {case_number}. {case.get('id', '')}",
                "",
                f"**Query:** {case['query']}",
                "",
                f"**Reference answer:** {case.get('reference_answer', '')}",
                "",
                "**Metrics:** "
                f"Recall@{k}={score.recall:.4f}; "
                f"Precision@{k}={score.precision:.4f}; "
                f"Precision@returned={score.precision_returned:.4f}; "
                f"RR={score.reciprocal_rank:.4f}",
                "",
                f"**Gold element IDs:** `{', '.join(sorted(gold_ids))}`",
                "",
                "### Gold evidence",
                "",
            ]
        )
        for evidence in case["evidence"]:
            ids = ", ".join(evidence.get("element_ids", []))
            lines.extend(
                [
                    f"- PDF page {evidence.get('pdf_page')}; role `{evidence.get('role', '')}`; "
                    f"element IDs `{ids}`",
                    _fenced_text(str(evidence.get("quote", ""))),
                    "",
                ]
            )

        lines.extend(["### Retrieved parents", ""])
        if not hits:
            lines.extend(["_No result passed the similarity threshold._", ""])
        for rank, hit in enumerate(hits, 1):
            metadata = hit.chunk.meta
            source_ids = metadata.get("source_element_ids", [])
            context_ids = metadata.get("context_element_ids", source_ids)
            relevant = bool(set(context_ids) & gold_ids)
            marker = "✅ relevant" if relevant else "❌ distractor"
            lines.extend(
                [
                    f"#### Rank {rank} — {marker}",
                    f"- Score: `{hit.score:.6f}`",
                    f"- Chunk: `{hit.chunk.chunk_id}`",
                    f"- Source element IDs: `{', '.join(source_ids)}`",
                    f"- Context element IDs: `{', '.join(context_ids)}`",
                    f"- Element types: `{', '.join(metadata.get('element_types', []))}`",
                    f"- Pages: `{metadata.get('page_nums', [])}`",
                    "",
                    _fenced_text(hit.chunk.context),
                    "",
                ]
            )

    count = len(all_scores)
    lines[5:5] = [
        f"- Overall Recall@{k}: `{sum(item.recall for item in all_scores) / count:.4f}`",
        f"- Overall Precision@{k}: `{sum(item.precision for item in all_scores) / count:.4f}`",
        f"- Overall Precision@returned: `{sum(item.precision_returned for item in all_scores) / count:.4f}`",
        f"- Overall MRR: `{sum(item.reciprocal_rank for item in all_scores) / count:.4f}`",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"已导出 {len(cases)} 个问题的人工核验报告: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--benchmark",
        type=Path,
        default=PROJECT_DIR / "evaluation-dataset" / "1710.11216v3.jsonl",
    )
    parser.add_argument(
        "--pdf",
        type=Path,
        default=PROJECT_DIR / "1710.11216v3.pdf",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_DIR / "benchmark-review-1710.11216v3.md",
    )
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--child-top-k", type=int, default=None)
    parser.add_argument("--min-score", type=float, default=DEFAULT_MIN_SCORE)
    args = parser.parse_args()
    if not args.benchmark.is_file():
        parser.error(f"benchmark 文件不存在: {args.benchmark}")
    if not args.pdf.is_file():
        parser.error(f"PDF 文件不存在: {args.pdf}")
    if args.k <= 0:
        parser.error("--k 必须大于 0")
    if args.child_top_k is not None and args.child_top_k <= 0:
        parser.error("--child-top-k 必须大于 0")
    if not -1 <= args.min_score <= 1:
        parser.error("--min-score 必须在 -1 到 1 之间")

    export_review(
        args.benchmark,
        args.pdf,
        args.output,
        k=args.k,
        child_top_k=args.child_top_k,
        min_score=args.min_score,
    )


if __name__ == "__main__":
    main()
