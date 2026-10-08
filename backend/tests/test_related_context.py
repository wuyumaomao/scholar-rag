from pathlib import Path

from app.documents.chunker import Chunk
from app.retrieval.related_context import expand_related_figure_context
from app.retrieval.retriever import RetrievalHit


def test_related_figure_is_added_to_parent_context_without_a_new_ranked_result(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "figure-5.png"
    body = Chunk(
        chunk_id="element-body-parent",
        context="The method is summarized in Figure 5.",
        meta={
            "source_element_ids": ["element-body"],
            "element_types": ["paragraph"],
            "related_element_ids": ["element-figure"],
        },
    )
    figure = Chunk(
        chunk_id="element-figure-parent",
        context="Figure: Figure 5: Depth estimation architecture",
        meta={
            "source_element_ids": ["element-figure"],
            "context_element_ids": ["element-figure", "element-caption"],
            "element_types": ["figure"],
            "image_path": str(image_path),
        },
    )
    vision_calls: list[tuple[Path, str]] = []

    def describe_image(path: Path, caption: str) -> str:
        vision_calls.append((path, caption))
        return "The diagram shows image input, a CNN, and predicted depth."

    expanded = expand_related_figure_context(
        [RetrievalHit(body, 0.92)],
        [body, figure],
        describe_image=describe_image,
    )

    assert len(expanded) == 1
    assert expanded[0].chunk.chunk_id == "element-body-parent"
    assert expanded[0].score == 0.92
    assert "Figure 5: Depth estimation architecture" in expanded[0].chunk.context
    assert "CNN, and predicted depth" in expanded[0].chunk.context
    assert expanded[0].chunk.meta["context_element_ids"] == [
        "element-body",
        "element-figure",
        "element-caption",
    ]
    assert expanded[0].chunk.meta["expanded_related_element_ids"] == [
        "element-figure",
        "element-caption",
    ]
    assert vision_calls == [
        (image_path, "Figure 5: Depth estimation architecture")
    ]
