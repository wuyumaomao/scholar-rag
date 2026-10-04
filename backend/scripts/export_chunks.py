"""Export parent/child chunks for manual inspection with the sample paper."""

from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.chunker import Chunk, create_chunks
from app.pdf_parser import parse_pdf


PDF_PATH = BACKEND_DIR.parent / "1710.11216v3.pdf"
OUTPUT_PATH = BACKEND_DIR / "docling-inspection" / "chunks_preview.md"


def _format_chunk(chunk: Chunk) -> list[str]:
    return [
        f"### `{chunk.chunk_id}`",
        "",
        f"- Parent ID: `{chunk.parent_chunk_id or '—'}`",
        f"- Metadata: `{chunk.meta}`",
        "",
        chunk.context,
        "",
    ]


def main() -> None:
    if not PDF_PATH.is_file():
        raise FileNotFoundError(f"PDF 文件不存在: {PDF_PATH}")

    parsed_pdf = parse_pdf(PDF_PATH)
    result = create_chunks(parsed_pdf)
    split_parent_ids = {
        child.parent_chunk_id
        for child in result.children
        if child.meta.get("child_index", 0) > 0
    }
    lines = [
        "# 学习版 PDF Parent/Child Chunk 预览",
        "",
        f"- PDF：`{PDF_PATH}`",
        "- 切分器：LangChain `RecursiveCharacterTextSplitter`",
        "- chunk_size：500 字符",
        "- chunk_overlap：50 字符",
        f"- Parent 数：{len(result.parents)}",
        f"- Child 数：{len(result.children)}",
        f"- 被拆分的 Parent 数：{len(split_parent_ids)}",
        "- 规则：不合并不同结构化元素；长段落、列表项和公式可拆分；表格和图注保持完整；章节标题只作为正文章节上下文。",
        "- Parent 与 Child 分节展示；每个 Child 保留来源元素 ID、页码、章节路径和相关元素 ID。",
        "",
        "## Parents",
        "",
    ]
    for parent in result.parents:
        lines.extend(_format_chunk(parent))

    lines.extend(["## Children", ""])
    for child in result.children:
        lines.extend(_format_chunk(child))

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(
        f"已导出 {len(result.parents)} 个 parent、{len(result.children)} 个 child "
        f"（{len(split_parent_ids)} 个 parent 被拆分）到：{OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
