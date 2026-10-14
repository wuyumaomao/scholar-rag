"""Use the same evidence numbering for model prompts and client source cards."""

from collections.abc import Iterator, Sequence

from app.retrieval.retriever import RetrievalHit


def numbered_evidence(hits: Sequence[RetrievalHit]) -> Iterator[tuple[int, RetrievalHit]]:
    """Skip empty passages before assigning S1, S2, ... labels."""
    return enumerate((hit for hit in hits if hit.chunk.context.strip()), start=1)


def build_sources(
    hits: Sequence[RetrievalHit], file_id: str, filename: str
) -> list[dict[str, object]]:
    """Expose only source-card fields, never arbitrary metadata/local paths."""
    sources = []
    for number, hit in numbered_evidence(hits):
        meta = hit.chunk.meta
        sources.append({
            "source_id": f"S{number}",
            "file_id": file_id,
            "filename": filename,
            "chunk_id": hit.chunk.chunk_id,
            "page_nums": [
                page for page in meta.get("page_nums", [])
                if isinstance(page, int) and not isinstance(page, bool) and page > 0
            ],
            "section_path": [str(part) for part in meta.get("section_path", [])],
            "text": hit.chunk.context.strip(),
        })
    return sources
