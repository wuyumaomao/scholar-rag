from app.chunker import Chunk
from app.retrieval_filters import RetrievalFilters, matches_filters


def test_filters_match_element_type_and_overlapping_page_range() -> None:
    chunk = Chunk(
        chunk_id="figure",
        context="Figure caption",
        meta={"element_types": ["figure"], "page_nums": [3, 4]},
    )

    filters = RetrievalFilters(element_types=("figure", "table"), page_from=4, page_to=6)

    assert matches_filters(chunk.meta, filters)


def test_filters_require_all_filter_groups_and_match_section_path_prefix() -> None:
    chunk = Chunk(
        chunk_id="paragraph",
        context="A result",
        meta={
            "element_types": ["paragraph"],
            "page_nums": [5],
            "section_path": ["Methods", "Experiments", "Results"],
        },
    )

    assert matches_filters(
        chunk.meta,
        RetrievalFilters(
            element_types=("paragraph",),
            page_from=4,
            page_to=5,
            section_path_prefix=("Methods", "Experiments"),
        ),
    )
    assert not matches_filters(
        chunk.meta,
        RetrievalFilters(section_path_prefix=("Methods", "Dataset")),
    )


def test_empty_filters_match_metadata_without_optional_fields() -> None:
    assert matches_filters({}, RetrievalFilters())


def test_filters_reject_invalid_page_ranges_and_empty_values() -> None:
    import pytest

    with pytest.raises(ValueError, match="page"):
        RetrievalFilters(page_from=0)
    with pytest.raises(ValueError, match="page"):
        RetrievalFilters(page_from=5, page_to=4)
    with pytest.raises(ValueError, match="element_types"):
        RetrievalFilters(element_types=("",))
