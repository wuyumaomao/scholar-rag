"""Inspect scholar-rag's Docling PDF parsing output without indexing anything."""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


def make_preview(text: str, limit: int = 240) -> str:
    return " ".join(text.split())[:limit]


def parse_pdf(pdf_path: Path, output_path: Path | None, preview_count: int) -> None:
    try:
        from rag.integration import PDFParser
    except ModuleNotFoundError as error:
        if error.name == "docling":
            raise RuntimeError(
                "Docling is not installed in this Python environment. "
                "Install scholar-rag dependencies with: "
                "python -m pip install -r backend/requirements.txt"
            ) from error
        raise

    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    print(f"PDF: {pdf_path}")
    print("[1/2] Parsing with scholar-rag PDFParser (Docling)...")
    started_at = time.perf_counter()
    nodes = PDFParser().parse(str(pdf_path), paper_id=pdf_path.stem)
    elapsed = time.perf_counter() - started_at

    type_counts = Counter(node.node_type for node in nodes)
    page_count = max((node.page_num for node in nodes), default=0)
    text_chars = sum(len(node.text) for node in nodes)

    print(f"[2/2] Parsed {len(nodes)} nodes in {elapsed:.1f}s")
    print(f"Pages represented: {page_count}")
    print(f"Extracted characters: {text_chars}")
    print("Node types:")
    for node_type, count in sorted(type_counts.items()):
        print(f"  {node_type}: {count}")

    print(f"\nFirst {min(preview_count, len(nodes))} nodes:")
    for index, node in enumerate(nodes[:preview_count], start=1):
        section = " > ".join(node.section_path) or "(no section)"
        print(
            f"\n[{index}] {node.node_type} | page={node.page_num} | "
            f"section={section}\n{make_preview(node.text)}"
        )

    report = {
        "source_pdf": str(pdf_path.resolve()),
        "parse_seconds": round(elapsed, 3),
        "node_count": len(nodes),
        "page_count": page_count,
        "text_characters": text_chars,
        "node_type_counts": dict(type_counts),
        "nodes": [
            {
                "index": index,
                "node_id": node.node_id,
                "node_type": node.node_type,
                "page_num": node.page_num,
                "order": node.order,
                "section_path": node.section_path,
                "bbox": node.bbox,
                "related_ids": node.related_ids,
                "image_path": node.image_path,
                "text": node.text,
            }
            for index, node in enumerate(nodes)
        ],
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nReport written to: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test scholar-rag's Docling-based PDF parser."
    )
    parser.add_argument("pdf", type=Path, help="Path to the PDF to inspect")
    parser.add_argument(
        "--preview-count",
        type=int,
        default=20,
        help="How many parsed nodes to print (default: 20)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON report path. Omit this to only print results.",
    )
    args = parser.parse_args()
    parse_pdf(args.pdf, args.output, args.preview_count)
