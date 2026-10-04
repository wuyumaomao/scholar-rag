"""Convert structured PDF elements into parent and retrieval child chunks."""

from copy import deepcopy
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.pdf_parser import ParsedElement, ParsedPdf


@dataclass(frozen=True)
class Chunk:
    """Text prepared for retrieval and its source metadata."""

    chunk_id: str
    context: str
    meta: dict[str, object]
    parent_chunk_id: str | None = None


@dataclass(frozen=True)
class ChunkingResult:
    """Original element-sized parent chunks and retrieval child chunks."""

    parents: list[Chunk]
    children: list[Chunk]


_SPLITTABLE_TYPES = {"paragraph", "list_item", "formula"}
_SEPARATORS = ["\n\n", "\n", ".", "?", "!", ";", " "]


def _section_prefix(element: ParsedElement) -> str:
    """Format chapter context to prepend to retrieval text."""
    if element.section_path and element.element_type != "section_header":
        return f"Section: {' > '.join(element.section_path)}\n\n"
    return ""


def _metadata_for(element: ParsedElement) -> dict[str, object]:
    """Copy source and layout information into a JSON-friendly metadata map."""
    provenance = [
        {"page_num": source.page_num, "bbox": source.bbox}
        for source in element.provenance
    ]
    page_nums = list(dict.fromkeys(source.page_num for source in element.provenance))
    if not page_nums:
        page_nums = [element.page_num]
    return {
        "source_element_ids": [element.element_id],
        "element_types": [element.element_type],
        "page_nums": page_nums,
        "section_path": list(element.section_path),
        "related_element_ids": list(element.related_ids),
        "orders": [element.order],
        "provenance": provenance,
    }


def create_chunks(
    parsed_pdf: ParsedPdf,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> ChunkingResult:
    """Create one parent per text element and split long prose into children.

    Elements are processed independently, so separate paragraphs, captions, and
    tables never get merged. Tables, captions, and headings remain whole; long
    paragraphs, list items, and formulas are split with LangChain's recursive
    character splitter. Character length is used, matching the original project.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size 必须大于 0")
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap 必须大于等于 0 且小于 chunk_size")

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=_SEPARATORS,
        keep_separator="end",
    )
    parents: list[Chunk] = []
    children: list[Chunk] = []

    for element in sorted(parsed_pdf.elements, key=lambda candidate: candidate.order):
        if not element.text.strip() or element.element_type == "section_header":
            continue

        parent_id = f"{element.element_id}-parent"
        prefix = _section_prefix(element)
        context = f"{prefix}{element.text.strip()}"
        meta = _metadata_for(element)
        parents.append(Chunk(chunk_id=parent_id, context=context, meta=deepcopy(meta)))

        if element.element_type in _SPLITTABLE_TYPES and len(context) > chunk_size:
            content_budget = chunk_size - len(prefix)
            if prefix and content_budget > 0:
                content_splitter = RecursiveCharacterTextSplitter(
                    chunk_size=content_budget,
                    chunk_overlap=min(chunk_overlap, content_budget - 1),
                    separators=_SEPARATORS,
                    keep_separator="end",
                )
                child_contexts = [
                    f"{prefix}{piece}" for piece in content_splitter.split_text(element.text.strip())
                ]
            else:
                child_contexts = splitter.split_text(context)
        else:
            child_contexts = [context]

        for child_index, child_context in enumerate(child_contexts):
            child_meta = deepcopy(meta)
            child_meta["child_index"] = child_index
            children.append(
                Chunk(
                    chunk_id=f"{element.element_id}-child-{child_index}",
                    context=child_context,
                    meta=child_meta,
                    parent_chunk_id=parent_id,
                )
            )

    return ChunkingResult(parents=parents, children=children)
