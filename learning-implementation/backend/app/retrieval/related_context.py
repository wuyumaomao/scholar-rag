"""Expand retrieved parent contexts with explicitly related figures."""

from collections.abc import Callable, Sequence
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from app.documents.chunker import Chunk
from app.retrieval.retriever import RetrievalHit


DescribeImage = Callable[[Path, str], str]


def _string_list(metadata: dict[str, object], key: str) -> list[str]:
    value = metadata.get(key, [])
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _caption_text(context: str) -> str:
    marker = "Figure:"
    if marker in context:
        return context.split(marker, maxsplit=1)[1].strip()
    return context.strip()


def expand_related_figure_context(
    hits: Sequence[RetrievalHit],
    parents: Sequence[Chunk],
    *,
    describe_image: DescribeImage | None = None,
) -> list[RetrievalHit]:
    """Append related figure evidence to ranked parent contexts.

    Related figures are resolved from a retrieved parent's ``related_element_ids``
    against the complete parent index, after ranking has selected the final hits.
    They enrich a result's context and metadata without consuming another rank.
    Each related figure is added at most once across the returned result list.
    """
    figures_by_element_id: dict[str, Chunk] = {}
    for parent in parents:
        element_types = _string_list(parent.meta, "element_types")
        if "figure" not in element_types:
            continue
        for element_id in _string_list(parent.meta, "source_element_ids"):
            figures_by_element_id[element_id] = parent

    seen_related_figures: set[str] = set()
    expanded_hits: list[RetrievalHit] = []
    for hit in hits:
        metadata = deepcopy(hit.chunk.meta)
        context = hit.chunk.context
        context_element_ids = _string_list(metadata, "context_element_ids")
        if not context_element_ids:
            context_element_ids = _string_list(metadata, "source_element_ids")

        direct_figure = "figure" in _string_list(metadata, "element_types")
        if direct_figure and describe_image is not None:
            image_path = metadata.get("image_path")
            if isinstance(image_path, str) and image_path:
                description = describe_image(
                    Path(image_path), _caption_text(context)
                )
                if description:
                    metadata["image_description"] = description
                    context = f"{context}\n\nImage description: {description}"

        expanded_ids: list[str] = []
        if not direct_figure:
            for related_id in _string_list(metadata, "related_element_ids"):
                figure = figures_by_element_id.get(related_id)
                if figure is None or related_id in seen_related_figures:
                    continue
                figure_context = figure.context.strip()
                if not figure_context:
                    continue
                seen_related_figures.add(related_id)

                context = (
                    f"{context}\n\nRelated figure evidence "
                    f"[{related_id}]:\n{figure_context}"
                )
                figure_image_path = figure.meta.get("image_path")
                if (
                    describe_image is not None
                    and isinstance(figure_image_path, str)
                    and figure_image_path
                ):
                    description = describe_image(
                        Path(figure_image_path), _caption_text(figure_context)
                    )
                    if description:
                        context = f"{context}\n\nImage description: {description}"

                figure_context_ids = _string_list(
                    figure.meta, "context_element_ids"
                ) or _string_list(figure.meta, "source_element_ids")
                for element_id in figure_context_ids:
                    if element_id not in context_element_ids:
                        context_element_ids.append(element_id)
                    if element_id not in expanded_ids:
                        expanded_ids.append(element_id)

        if expanded_ids:
            metadata["context_element_ids"] = context_element_ids
            metadata["expanded_related_element_ids"] = expanded_ids

        expanded_chunk = replace(hit.chunk, context=context, meta=metadata)
        expanded_hits.append(replace(hit, chunk=expanded_chunk))

    return expanded_hits
