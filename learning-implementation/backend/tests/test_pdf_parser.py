"""行为测试：将 Docling 解析结果保留为带关系的文档元素。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.documents.pdf_parser import (
    ParsedElement,
    ParsedPdf,
    extract_body_text,
    is_text_inside_picture,
    parse_pdf,
)


def provenance(page_number: int, bbox: tuple[float, float, float, float] | None = None):
    values = {"page_no": page_number}
    if bbox is not None:
        left, top, right, bottom = bbox
        values["bbox"] = SimpleNamespace(l=left, t=top, r=right, b=bottom)
    return SimpleNamespace(**values)


class TextItem:
    def __init__(
        self,
        text: str,
        page_number: int,
        *,
        label: str = "text",
        bbox: tuple[float, float, float, float] | None = None,
        self_ref: str | None = None,
        prov: list[object] | None = None,
    ) -> None:
        self.text = text
        self.label = SimpleNamespace(value=label)
        self.prov = prov if prov is not None else [provenance(page_number, bbox)]
        self.self_ref = self_ref


class SectionHeaderItem(TextItem):
    def __init__(self, text: str, page_number: int, level: int) -> None:
        super().__init__(text, page_number, label="section_header")
        self.level = level


class ListItem(TextItem):
    pass


class PictureItem:
    def __init__(
        self,
        page_number: int,
        *,
        self_ref: str,
        captions: list[str] | None = None,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> None:
        self.label = SimpleNamespace(value="picture")
        self.prov = [provenance(page_number, bbox)]
        self.self_ref = self_ref
        self.captions = [SimpleNamespace(cref=ref) for ref in captions or []]

    def export_to_markdown(self, document: object) -> str:
        return "![Fig. 1: duplicated caption](figure.png)"


class TableItem:
    def __init__(self, page_number: int, self_ref: str, captions: list[str]):
        self.label = SimpleNamespace(value="table")
        self.prov = [provenance(page_number)]
        self.self_ref = self_ref
        self.captions = [SimpleNamespace(cref=ref) for ref in captions]
        self.text = "| A | B |\n|---|---|\n| 1 | 2 |"


class FormulaItem(TextItem):
    pass


class UnknownItem(TextItem):
    pass


class FakeDocument:
    def __init__(self, items: list[object], page_count: int = 3) -> None:
        self._items = items
        self.pages = {number: object() for number in range(1, page_count + 1)}

    def iterate_items(self):
        return iter((item, 1) for item in self._items)


class FakeConverter:
    def __init__(self, document: FakeDocument) -> None:
        self.document = document
        self.converted_path: str | None = None

    def convert(self, path: str) -> SimpleNamespace:
        self.converted_path = path
        return SimpleNamespace(document=self.document)


def parse_items(tmp_path: Path, items: list[object], page_count: int = 3) -> ParsedPdf:
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"fake pdf")
    converter = FakeConverter(FakeDocument(items, page_count=page_count))
    result = parse_pdf(pdf_path, converter=converter)
    assert converter.converted_path == str(pdf_path)
    return result


def test_is_text_inside_picture_filters_short_number_with_bbox_tolerance() -> None:
    number = TextItem("250", 2, bbox=(101, 90, 103, 86))
    picture = PictureItem(2, self_ref="#/pictures/0", bbox=(20, 100, 100, 30))

    assert is_text_inside_picture(number, [picture])


def test_is_text_inside_picture_keeps_year_outside_picture_bbox() -> None:
    year = TextItem("2024", 2, bbox=(105, 90, 125, 86))
    picture = PictureItem(2, self_ref="#/pictures/0", bbox=(20, 100, 100, 30))

    assert not is_text_inside_picture(year, [picture])


def test_is_text_inside_picture_keeps_body_text_and_long_numbers() -> None:
    picture = PictureItem(2, self_ref="#/pictures/0", bbox=(20, 100, 100, 30))

    assert not is_text_inside_picture(TextItem("Depth 42", 2, bbox=(30, 90, 60, 80)), [picture])
    assert not is_text_inside_picture(TextItem("12345", 2, bbox=(30, 90, 60, 80)), [picture])


def test_is_text_inside_picture_does_not_match_other_page() -> None:
    number = TextItem("250", 2, bbox=(40, 80, 45, 75))
    picture = PictureItem(3, self_ref="#/pictures/0", bbox=(20, 100, 100, 30))

    assert not is_text_inside_picture(number, [picture])


def test_parsed_models_have_stable_empty_defaults_and_json_serialization() -> None:
    element = ParsedElement(
        element_id="element-000001",
        element_type="paragraph",
        docling_type="TextItem",
        docling_label="text",
        text="hello",
        page_num=1,
        order=1,
        bbox=None,
    )
    result = ParsedPdf(page_count=1, elements=[element])

    assert element.section_path == []
    assert element.related_ids == []
    assert json.loads(json.dumps(result.to_dict()))["elements"][0]["text"] == "hello"


def test_parse_pdf_maps_docling_types_and_preserves_layout_fields(tmp_path: Path) -> None:
    heading = SectionHeaderItem("Methods", 1, level=1)
    paragraph = TextItem("Text with Fig. 1.", 1, bbox=(1, 9, 8, 2))
    listing = ListItem("A list entry", 1, label="list_item")
    figure = PictureItem(1, self_ref="#/pictures/0", bbox=(10, 90, 90, 10))
    caption = TextItem("Fig. 1: Result", 1, label="caption", self_ref="#/texts/0")
    table = TableItem(1, "#/tables/0", ["#/texts/1"])
    table_caption = TextItem("Table 1: Values", 1, label="caption", self_ref="#/texts/1")
    formula = FormulaItem("x = 1", 1, label="formula")
    unknown = UnknownItem("Preserve this", 1, label="custom_region")

    result = parse_items(
        tmp_path,
        [heading, paragraph, listing, figure, caption, table, table_caption, formula, unknown],
    )

    assert [element.element_type for element in result.elements] == [
        "section_header",
        "paragraph",
        "list_item",
        "figure",
        "caption",
        "table",
        "caption",
        "formula",
        "unknown",
    ]
    assert result.page_count == 3
    assert result.elements[1].order == 2
    assert result.elements[1].bbox == (1.0, 9.0, 8.0, 2.0)
    assert result.elements[-1].docling_type == "UnknownItem"
    assert result.elements[-1].docling_label == "custom_region"


def test_parse_pdf_preserves_cross_page_text_as_one_element_with_all_provenance(
    tmp_path: Path,
) -> None:
    text = TextItem(
        "One paragraph continues across pages.",
        2,
        prov=[provenance(2, (1, 9, 8, 2)), provenance(3, (2, 10, 9, 3))],
    )

    result = parse_items(tmp_path, [text])

    assert len(result.elements) == 1
    element = result.elements[0]
    assert element.page_num == 2
    assert [source.page_num for source in element.provenance] == [2, 3]
    assert [source.bbox for source in element.provenance] == [
        (1.0, 9.0, 8.0, 2.0),
        (2.0, 10.0, 9.0, 3.0),
    ]


def test_parse_pdf_builds_section_paths_and_clears_sibling_headers(tmp_path: Path) -> None:
    result = parse_items(
        tmp_path,
        [
            SectionHeaderItem("1 Methods", 1, level=1),
            TextItem("Intro paragraph", 1),
            SectionHeaderItem("1.1 Data", 1, level=2),
            TextItem("Data paragraph", 1),
            SectionHeaderItem("2 Results", 1, level=1),
            TextItem("Results paragraph", 1),
        ],
    )

    assert [element.section_path for element in result.elements] == [
        ["1 Methods"],
        ["1 Methods"],
        ["1 Methods", "1.1 Data"],
        ["1 Methods", "1.1 Data"],
        ["2 Results"],
        ["2 Results"],
    ]


def test_parse_pdf_links_picture_and_caption_both_ways_without_caption_duplication(
    tmp_path: Path,
) -> None:
    paragraph = TextItem("See Fig. 1 for details.", 1)
    figure = PictureItem(1, self_ref="#/pictures/0", captions=["#/texts/0"])
    caption = TextItem(
        "Fig. 1: depth results", 1, label="caption", self_ref="#/texts/0"
    )

    result = parse_items(tmp_path, [paragraph, figure, caption])
    by_type = {element.element_type: element for element in result.elements}

    assert len(result.elements) == 3
    assert by_type["figure"].text == ""
    assert set(by_type["figure"].related_ids) == {
        by_type["paragraph"].element_id,
        by_type["caption"].element_id,
    }
    assert by_type["caption"].related_ids == [by_type["figure"].element_id]
    assert by_type["paragraph"].related_ids == [by_type["figure"].element_id]


def test_parse_pdf_links_table_caption_and_unique_body_references(tmp_path: Path) -> None:
    paragraph = TextItem("Table 1 and Table 1 summarize the values.", 1)
    table = TableItem(1, "#/tables/0", ["#/texts/0"])
    caption = TextItem(
        "Table 1: Results", 1, label="caption", self_ref="#/texts/0"
    )

    result = parse_items(tmp_path, [paragraph, table, caption])
    by_type = {element.element_type: element for element in result.elements}

    assert by_type["paragraph"].related_ids == [by_type["table"].element_id]
    assert set(by_type["table"].related_ids) == {
        by_type["paragraph"].element_id,
        by_type["caption"].element_id,
    }
    assert by_type["caption"].related_ids == [by_type["table"].element_id]


def test_parse_pdf_matches_roman_numeral_table_references(tmp_path: Path) -> None:
    paragraph = TextItem("See Table I for the comparison.", 1)
    table = TableItem(1, "#/tables/0", ["#/texts/0"])
    caption = TextItem("TABLE I: Dataset comparison", 1, label="caption", self_ref="#/texts/0")

    result = parse_items(tmp_path, [paragraph, table, caption])

    assert result.elements[0].related_ids == [result.elements[1].element_id]


def test_parse_pdf_does_not_guess_ambiguous_or_missing_reference_targets(
    tmp_path: Path,
) -> None:
    paragraph = TextItem("See Fig. 1 and Table 9.", 1)
    figure_one = PictureItem(1, self_ref="#/pictures/0", captions=["#/texts/0"])
    second_figure_one = PictureItem(
        1, self_ref="#/pictures/1", captions=["#/texts/1"]
    )
    caption_one_a = TextItem(
        "Fig. 1: first", 1, label="caption", self_ref="#/texts/0"
    )
    caption_one_b = TextItem(
        "Fig. 1: second", 1, label="caption", self_ref="#/texts/1"
    )

    result = parse_items(
        tmp_path, [paragraph, figure_one, second_figure_one, caption_one_a, caption_one_b]
    )

    assert result.elements[0].related_ids == []


def test_parse_pdf_skips_invalid_caption_refs_and_keeps_original_order_gaps(
    tmp_path: Path,
) -> None:
    filtered_number = TextItem(
        "250", 1, bbox=(95, 90, 98, 86), self_ref="#/texts/0"
    )
    figure = PictureItem(
        1,
        self_ref="#/pictures/0",
        captions=["#/texts/missing"],
        bbox=(20, 100, 100, 30),
    )
    following_text = TextItem("Year 2024", 1)

    result = parse_items(tmp_path, [filtered_number, figure, following_text])

    assert [element.order for element in result.elements] == [2, 3]
    assert result.elements[0].related_ids == []
    assert result.elements[1].text == "Year 2024"


def test_extract_body_text_skips_figures_captions_and_tables_in_docling_order(
    tmp_path: Path,
) -> None:
    result = parse_items(
        tmp_path,
        [
            TextItem("First paragraph", 1),
            PictureItem(1, self_ref="#/pictures/0"),
            TextItem("Figure caption", 1, label="caption"),
            TextItem("Second paragraph", 1),
            TableItem(1, "#/tables/0", []),
            FormulaItem("x = y", 1, label="formula"),
            TextItem("Footnote text", 1, label="footnote"),
        ],
    )

    assert extract_body_text(result) == "First paragraph\n\nSecond paragraph\n\nx = y"
    assert extract_body_text(result, include_formulas=False) == (
        "First paragraph\n\nSecond paragraph"
    )


def test_unknown_docling_item_with_page_provenance_is_preserved(tmp_path: Path) -> None:
    result = parse_items(tmp_path, [UnknownItem("custom", 1, label="new_label")])

    assert len(result.elements) == 1
    assert result.elements[0].element_type == "unknown"
    assert result.elements[0].docling_type == "UnknownItem"
    assert result.elements[0].text == "custom"


def test_parse_pdf_skips_element_without_page_provenance(tmp_path: Path) -> None:
    item = TextItem("No page information", 1, prov=[])

    result = parse_items(tmp_path, [item], page_count=2)

    assert result.page_count == 2
    assert result.elements == []
