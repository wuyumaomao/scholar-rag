from __future__ import annotations

import pytest

from app.documents.chunker import create_chunks
from app.documents.pdf_parser import ParsedElement, ParsedPdf, ParsedProvenance


def make_element(
    element_id: str,
    text: str,
    *,
    element_type: str = "paragraph",
    section_path: list[str] | None = None,
    related_ids: list[str] | None = None,
    image_path: str | None = None,
) -> ParsedElement:
    return ParsedElement(
        element_id=element_id,
        element_type=element_type,
        docling_type="TextItem",
        docling_label="text",
        text=text,
        page_num=2,
        order=1,
        bbox=(10.0, 700.0, 300.0, 650.0),
        provenance=[ParsedProvenance(page_num=2, bbox=(10.0, 700.0, 300.0, 650.0))],
        section_path=section_path or [],
        related_ids=related_ids or [],
        image_path=image_path,
    )


def test_short_element_becomes_one_parent_and_one_child_with_source_metadata() -> None:
    parsed_pdf = ParsedPdf(
        page_count=2,
        elements=[
            make_element(
                "element-000001",
                "A short paragraph.",
                section_path=["II. Methods", "A. Data"],
                related_ids=["element-000002"],
            )
        ],
    )

    result = create_chunks(parsed_pdf, chunk_size=100, chunk_overlap=5)

    assert len(result.parents) == 1
    assert len(result.children) == 1
    parent = result.parents[0]
    child = result.children[0]
    assert parent.context == "Section: II. Methods > A. Data\n\nA short paragraph."
    assert child.context == parent.context
    assert parent.chunk_id == "element-000001-parent"
    assert child.chunk_id == "element-000001-child-0"
    assert child.parent_chunk_id == parent.chunk_id
    assert child.meta["source_element_ids"] == ["element-000001"]
    assert child.meta["page_nums"] == [2]
    assert child.meta["related_element_ids"] == ["element-000002"]


def test_section_header_is_context_only_and_not_a_retrieval_chunk() -> None:
    parsed_pdf = ParsedPdf(
        page_count=1,
        elements=[
            make_element(
                "element-000001",
                "Depth Estimation from Endoscopy Images",
                element_type="section_header",
            ),
            make_element(
                "element-000002",
                "The method estimates depth from monocular endoscopy images.",
                section_path=["Depth Estimation from Endoscopy Images"],
            ),
        ],
    )

    result = create_chunks(parsed_pdf)

    assert [parent.chunk_id for parent in result.parents] == ["element-000002-parent"]
    assert [child.chunk_id for child in result.children] == ["element-000002-child-0"]
    assert "Depth Estimation from Endoscopy Images" in result.children[0].context
    assert "The method estimates" in result.children[0].context


def test_table_caption_is_skipped_when_table_text_already_contains_it() -> None:
    table_title = "TABLE I: A COMPARISON OF DIFFERENT ENDOSCOPY DATASETS."
    table = make_element(
        "element-000047",
        f"{table_title}\n\n| Dataset | Size |\n|---|---|\n| Colon | 100 |",
        element_type="table",
        related_ids=["element-000048"],
    )
    caption = make_element(
        "element-000048",
        table_title,
        element_type="caption",
        related_ids=["element-000047"],
    )

    result = create_chunks(ParsedPdf(page_count=1, elements=[table, caption]))

    assert [parent.chunk_id for parent in result.parents] == ["element-000047-parent"]
    assert [child.chunk_id for child in result.children] == ["element-000047-child-0"]
    assert result.children[0].context.count(table_title) == 1
    parent = result.parents[0]
    child = result.children[0]
    assert table.related_ids == ["element-000048"]
    assert parent.meta["related_element_ids"] == []
    assert child.meta["related_element_ids"] == []


def test_table_caption_is_kept_when_table_text_does_not_contain_it() -> None:
    table = make_element(
        "element-000047",
        "| Dataset | Size |\n|---|---|\n| Colon | 100 |",
        element_type="table",
        related_ids=["element-000048"],
    )
    caption = make_element(
        "element-000048",
        "TABLE I: Dataset sizes.",
        element_type="caption",
        related_ids=["element-000047"],
    )

    result = create_chunks(ParsedPdf(page_count=1, elements=[table, caption]))

    assert [parent.chunk_id for parent in result.parents] == [
        "element-000047-parent",
        "element-000048-parent",
    ]


def test_figure_uses_caption_as_context_and_skips_caption_chunk() -> None:
    figure = make_element(
        "element-000036",
        "",
        element_type="figure",
        related_ids=["element-000037"],
        image_path="data/figures/paper/page2_order36.png",
    )
    caption = make_element(
        "element-000037",
        "Fig. 2: The overall architecture for depth estimation.",
        element_type="caption",
        related_ids=["element-000036"],
    )

    result = create_chunks(ParsedPdf(page_count=2, elements=[figure, caption]))

    assert [parent.chunk_id for parent in result.parents] == ["element-000036-parent"]
    assert [child.chunk_id for child in result.children] == ["element-000036-child-0"]
    assert result.parents[0].context == (
        "Figure: Fig. 2: The overall architecture for depth estimation."
    )
    assert result.children[0].context == result.parents[0].context
    assert result.parents[0].meta["image_path"] == "data/figures/paper/page2_order36.png"
    assert result.children[0].meta["image_path"] == "data/figures/paper/page2_order36.png"
    assert result.parents[0].meta["context_element_ids"] == [
        "element-000036",
        "element-000037",
    ]
    assert result.children[0].meta["context_element_ids"] == [
        "element-000036",
        "element-000037",
    ]


def test_caption_without_figure_remains_a_caption_chunk() -> None:
    caption = make_element(
        "element-000037",
        "Fig. 2: Caption without a parsed figure.",
        element_type="caption",
    )

    result = create_chunks(ParsedPdf(page_count=1, elements=[caption]))

    assert [parent.chunk_id for parent in result.parents] == ["element-000037-parent"]


def test_long_paragraph_splits_into_children_without_merging_elements() -> None:
    first = "Alpha sentence. " * 10
    second = "Beta sentence. " * 10
    parsed_pdf = ParsedPdf(
        page_count=2,
        elements=[
            make_element("element-000001", first, section_path=["A. Methods"]),
            make_element("element-000002", second, section_path=["A. Methods"]),
        ],
    )

    result = create_chunks(parsed_pdf, chunk_size=45, chunk_overlap=5)

    first_children = [child for child in result.children if child.parent_chunk_id == "element-000001-parent"]
    second_children = [child for child in result.children if child.parent_chunk_id == "element-000002-parent"]
    assert len(result.parents) == 2
    assert len(first_children) > 1
    assert len(second_children) > 1
    assert all(child.context.startswith("Section: A. Methods\n\n") for child in first_children)
    assert all(child.context.startswith("Section: A. Methods\n\n") for child in second_children)
    assert all(
        child.context.split("\n\n", 1)[1].endswith(".")
        and not child.context.split("\n\n", 1)[1].startswith(".")
        for child in first_children + second_children
    )
    assert all("Beta sentence." not in child.context for child in first_children)
    assert all("Alpha sentence." not in child.context for child in second_children)
    assert all(child.meta["source_element_ids"] == ["element-000001"] for child in first_children)


def test_table_is_kept_as_a_single_chunk_even_when_it_exceeds_target_size() -> None:
    table_text = "| value |\n|---|\n" + ("| data |\n" * 30)
    parsed_pdf = ParsedPdf(
        page_count=2,
        elements=[make_element("element-000003", table_text, element_type="table")],
    )

    result = create_chunks(parsed_pdf, chunk_size=30, chunk_overlap=5)

    assert len(result.parents) == 1
    assert len(result.children) == 1
    assert result.children[0].context.strip().endswith(table_text.strip())


@pytest.mark.parametrize(
    ("chunk_size", "chunk_overlap"),
    [(0, 0), (10, -1), (10, 10)],
)
def test_invalid_splitter_sizes_are_rejected(chunk_size: int, chunk_overlap: int) -> None:
    with pytest.raises(ValueError):
        create_chunks(ParsedPdf(page_count=0, elements=[]), chunk_size, chunk_overlap)
