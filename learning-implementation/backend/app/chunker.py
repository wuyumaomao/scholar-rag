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


def _metadata_for(
    element: ParsedElement,
    excluded_related_ids: set[str] | None = None,
) -> dict[str, object]:
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
        "related_element_ids": [
            related_id
            for related_id in element.related_ids
            if related_id not in (excluded_related_ids or set())
        ],
        "orders": [element.order],
        "provenance": provenance,
        "image_path": element.image_path or "",
    }


def _duplicate_table_caption_ids(elements: list[ParsedElement]) -> set[str]:
    """Find table captions whose text is already included in the table element."""
    tables = {
        element.element_id: " ".join(element.text.split()).casefold()
        for element in elements
        if element.element_type == "table" and element.text.strip()
    }
    duplicate_ids: set[str] = set()
    for element in elements:
        if element.element_type != "caption" or not element.text.strip():
            continue
        caption_text = " ".join(element.text.split()).casefold()
        for related_id in element.related_ids:
            table_text = tables.get(related_id)
            if table_text and caption_text in table_text:
                duplicate_ids.add(element.element_id)
                break
    return duplicate_ids


def _figure_caption_ids(elements: list[ParsedElement]) -> set[str]:
    """Find captions consumed by an associated figure chunk."""
    by_id = {element.element_id: element for element in elements}
    return {
        related_id
        for element in elements
        if element.element_type == "figure"
        for related_id in element.related_ids
        if by_id.get(related_id, None) is not None
        and by_id[related_id].element_type == "caption"
        and by_id[related_id].text.strip()
    }


def _context_for(element: ParsedElement, elements_by_id: dict[str, ParsedElement]) -> str:
    """Build retrieval text, attaching a figure's caption to the figure."""
    prefix = _section_prefix(element)
    if element.element_type == "figure":
        captions = [
            elements_by_id[related_id].text.strip()
            for related_id in element.related_ids
            if related_id in elements_by_id
            and elements_by_id[related_id].element_type == "caption"
            and elements_by_id[related_id].text.strip()
        ]
        if not captions:
            return ""
        text = "Figure: " + " ".join(captions)
    else:
        text = element.text.strip()
    return f"{prefix}{text}" if text else ""


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
    duplicate_caption_ids = _duplicate_table_caption_ids(parsed_pdf.elements)
    figure_caption_ids = _figure_caption_ids(parsed_pdf.elements)
    excluded_caption_ids = duplicate_caption_ids | figure_caption_ids
    elements_by_id = {element.element_id: element for element in parsed_pdf.elements}
    parents: list[Chunk] = []
    children: list[Chunk] = []

    for element in sorted(parsed_pdf.elements, key=lambda candidate: candidate.order):
        if (
            not _context_for(element, elements_by_id)
            or element.element_type == "section_header"
            or element.element_id in excluded_caption_ids
        ):
            continue

        parent_id = f"{element.element_id}-parent"
        prefix = _section_prefix(element)
        context = _context_for(element, elements_by_id)
        meta = _metadata_for(element, duplicate_caption_ids)
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
