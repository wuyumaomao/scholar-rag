"""将 Docling PDF 结果转换为保留布局和关系的结构化元素。"""

from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
import re
from typing import Any


@dataclass(frozen=True)
class ParsedProvenance:
    """一个元素在 PDF 某一页上的来源和版面位置。"""

    page_num: int
    bbox: tuple[float, float, float, float] | None


@dataclass(frozen=True)
class ParsedElement:
    """Docling 文档中的一个元素及其学习版关系。"""

    element_id: str
    element_type: str
    docling_type: str
    docling_label: str | None
    text: str
    page_num: int
    order: int
    bbox: tuple[float, float, float, float] | None
    image_path: str | None = None
    provenance: list[ParsedProvenance] = field(default_factory=list)
    section_path: list[str] = field(default_factory=list)
    related_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedPdf:
    """一次 PDF 解析的结果；正文视图可从 ``elements`` 派生。"""

    page_count: int
    elements: list[ParsedElement]

    def to_dict(self) -> dict[str, Any]:
        """递归转换为可 JSON 序列化的普通字典。"""
        return asdict(self)


_CAPTION_LABEL_RE = re.compile(
    r"^\s*(fig(?:ure)?|table)s?\.?\s*([0-9]+|[ivxlcdm]+)\b", re.I
)
_BODY_REFERENCE_RE = re.compile(
    r"\b(fig(?:ure)?|table)s?\.?\s*([0-9]+|[ivxlcdm]+)\b", re.I
)
_BODY_ELEMENT_TYPES = {"paragraph", "list_item", "section_header", "formula"}


def _item_bbox(item: Any) -> tuple[float, float, float, float] | None:
    """读取元素第一个 provenance bbox，统一返回 (left, top, right, bottom)。"""
    provenance = getattr(item, "prov", None) or []
    bbox = getattr(provenance[0], "bbox", None) if provenance else None
    if bbox is None:
        bbox = getattr(item, "bbox", None)
    if bbox is None:
        return None

    try:
        left, top, right, bottom = bbox.l, bbox.t, bbox.r, bbox.b
        return float(left), float(top), float(right), float(bottom)
    except (AttributeError, TypeError, ValueError):
        return None


def _page_number(item: Any) -> int | None:
    provenance = getattr(item, "prov", None) or []
    if not provenance:
        return None

    page_number = getattr(provenance[0], "page_no", None)
    return page_number if isinstance(page_number, int) and page_number > 0 else None


def is_text_inside_picture(
    text_item: Any,
    picture_items: list[Any],
    margin: float = 4.0,
) -> bool:
    """判断短纯数字文本是否位于同页图片 bbox 内（含少量坐标容差）。"""
    text = getattr(text_item, "text", None) or getattr(text_item, "orig", None) or ""
    if not re.fullmatch(r"\d{1,4}", str(text).strip()):
        return False

    text_page = _page_number(text_item)
    text_bbox = _item_bbox(text_item)
    if text_page is None or text_bbox is None:
        return False

    text_left, text_top, text_right, text_bottom = text_bbox
    for picture_item in picture_items:
        if _page_number(picture_item) != text_page:
            continue

        picture_bbox = _item_bbox(picture_item)
        if picture_bbox is None:
            continue
        picture_left, picture_top, picture_right, picture_bottom = picture_bbox

        if (
            text_left >= min(picture_left, picture_right) - margin
            and text_right <= max(picture_left, picture_right) + margin
            and text_bottom >= min(picture_top, picture_bottom) - margin
            and text_top <= max(picture_top, picture_bottom) + margin
        ):
            return True

    return False


def _create_converter() -> Any:
    """创建关闭 OCR 的 Docling PDF 转换器。"""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False
    # Windows 上关闭 torch.compile，避免首次解析时编译模型失败。
    pipeline_options.layout_options.engine_options.compile_model = False
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )


def _item_text(item: Any, document: Any, element_type: str) -> str:
    """读取元素自身文本；图片不使用会展开图注的 Markdown fallback。"""
    text = getattr(item, "text", None) or getattr(item, "orig", None)
    if not text and element_type != "figure":
        export_to_markdown = getattr(item, "export_to_markdown", None)
        if callable(export_to_markdown):
            try:
                text = export_to_markdown(document)
            except TypeError:
                text = ""
    return str(text).strip() if text else ""


def _extract_figure_images(
    pdf_path: Path,
    elements: list[ParsedElement],
    figure_dir: Path,
) -> list[ParsedElement]:
    """按 Docling bbox 裁剪图片，并把保存路径写回 figure 元素。"""
    if not any(
        element.element_type == "figure" and element.bbox and element.page_num > 0
        for element in elements
    ):
        return elements

    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError(
            "需要安装 PyMuPDF 才能裁剪图片：uv pip install pymupdf"
        ) from exc

    figure_dir.mkdir(parents=True, exist_ok=True)
    with fitz.open(pdf_path) as pdf:
        updated: list[ParsedElement] = []
        for element in elements:
            if element.element_type != "figure" or not element.bbox:
                updated.append(element)
                continue

            page_index = element.page_num - 1
            if page_index < 0 or page_index >= len(pdf):
                updated.append(element)
                continue

            page = pdf[page_index]
            page_height = page.rect.height
            left, top, right, bottom = element.bbox
            rect = fitz.Rect(left, page_height - top, right, page_height - bottom)
            rect = rect + fitz.Rect(-4, -4, 4, 4)
            rect &= page.rect
            if rect.is_empty or rect.is_infinite:
                updated.append(element)
                continue

            image_path = figure_dir / f"page{element.page_num}_order{element.order}.png"
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), clip=rect)
            pixmap.save(str(image_path))
            updated.append(replace(element, image_path=str(image_path)))

    return updated


def _item_label(item: Any) -> str | None:
    label = getattr(item, "label", None)
    value = getattr(label, "value", label)
    return str(value) if value is not None else None


def _element_type(item: Any, docling_label: str | None) -> str:
    """把 Docling class/label 映射为学习版稳定类型。"""
    class_name = type(item).__name__
    if class_name == "SectionHeaderItem":
        return "section_header"
    if class_name == "ListItem":
        return "list_item"
    if class_name == "PictureItem":
        return "figure"
    if class_name == "TableItem":
        return "table"
    if class_name == "FormulaItem":
        return "formula"

    label_mapping = {
        "title": "section_header",
        "section_header": "section_header",
        "text": "paragraph",
        "paragraph": "paragraph",
        "list_item": "list_item",
        "picture": "figure",
        "table": "table",
        "formula": "formula",
        "caption": "caption",
        "footnote": "footnote",
    }
    return label_mapping.get(docling_label or "", "unknown")


def _bbox_from_provenance(provenance: Any) -> tuple[float, float, float, float] | None:
    bbox = getattr(provenance, "bbox", None)
    if bbox is None:
        return None
    try:
        return float(bbox.l), float(bbox.t), float(bbox.r), float(bbox.b)
    except (AttributeError, TypeError, ValueError):
        return None


def _parsed_provenance(item: Any) -> list[ParsedProvenance]:
    parsed: list[ParsedProvenance] = []
    for source in getattr(item, "prov", None) or []:
        page_number = getattr(source, "page_no", None)
        if isinstance(page_number, int) and page_number > 0:
            parsed.append(
                ParsedProvenance(
                    page_num=page_number,
                    bbox=_bbox_from_provenance(source),
                )
            )
    return parsed


def _page_count(document: Any, elements: list[ParsedElement]) -> int:
    document_pages = getattr(document, "pages", None)
    try:
        count = len(document_pages) if document_pages is not None else 0
    except TypeError:
        count = 0
    return max(count, max((element.page_num for element in elements), default=0))


def _ref_id(reference: Any) -> str | None:
    value = getattr(reference, "cref", reference)
    return str(value) if value is not None else None


def _normalize_reference_number(number: str) -> str:
    """将阿拉伯或罗马数字编号归一化，便于图表提及匹配。"""
    if number.isdigit():
        return str(int(number))

    roman_values = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    total = 0
    previous = 0
    for character in reversed(number.lower()):
        value = roman_values[character]
        total += -value if value < previous else value
        previous = max(previous, value)
    return str(total)


def _caption_kind_and_number(text: str) -> tuple[str, str] | None:
    match = _CAPTION_LABEL_RE.search(text)
    if match is None:
        return None
    prefix = match.group(1).lower()
    kind = "table" if prefix.startswith("table") else "figure"
    return kind, _normalize_reference_number(match.group(2))


def _link_elements(
    parsed_items: list[tuple[Any, ParsedElement]],
) -> list[ParsedElement]:
    """以 Docling 原生 caption ref 和唯一编号建立双向相关关系。"""
    by_ref = {
        ref_id: element.element_id
        for item, element in parsed_items
        if (ref_id := _ref_id(getattr(item, "self_ref", None))) is not None
    }
    elements_by_id = {element.element_id: element for _, element in parsed_items}
    related: dict[str, set[str]] = {element.element_id: set() for _, element in parsed_items}

    for item, element in parsed_items:
        if element.element_type not in {"figure", "table"}:
            continue
        for reference in getattr(item, "captions", None) or []:
            caption_id = by_ref.get(_ref_id(reference) or "")
            if caption_id is None or elements_by_id[caption_id].element_type != "caption":
                continue
            related[element.element_id].add(caption_id)
            related[caption_id].add(element.element_id)

    targets: dict[tuple[str, str], set[str]] = {}
    for _, element in parsed_items:
        if element.element_type not in {"figure", "table"}:
            continue
        for caption_id in related[element.element_id]:
            caption = elements_by_id[caption_id]
            caption_identity = _caption_kind_and_number(caption.text)
            if caption_identity is not None and caption_identity[0] == element.element_type:
                targets.setdefault(caption_identity, set()).add(element.element_id)

    for _, element in parsed_items:
        if element.element_type not in {"paragraph", "list_item"}:
            continue
        for match in _BODY_REFERENCE_RE.finditer(element.text):
            prefix = match.group(1).lower()
            kind = "table" if prefix.startswith("table") else "figure"
            candidate_ids = targets.get(
                (kind, _normalize_reference_number(match.group(2))), set()
            )
            if len(candidate_ids) == 1:
                target_id = next(iter(candidate_ids))
                related[element.element_id].add(target_id)
                related[target_id].add(element.element_id)

    return [
        replace(
            element,
            related_ids=[
                candidate.element_id
                for _, candidate in parsed_items
                if candidate.element_id in related[element.element_id]
            ],
        )
        for _, element in parsed_items
    ]


def parse_pdf(
    pdf_path: str | Path,
    converter: Any | None = None,
    *,
    figure_dir: str | Path | None = None,
) -> ParsedPdf:
    """使用 Docling 解析 PDF，返回带类型、位置和关系的结构化元素。"""
    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF 文件不存在: {path}")

    if converter is None:
        converter = _create_converter()
    conversion_result = converter.convert(str(path))
    document = conversion_result.document
    items_with_levels = list(document.iterate_items())
    items = [item for item, _ in items_with_levels]
    picture_items = [item for item in items if type(item).__name__ == "PictureItem"]

    section_levels: dict[int, str] = {}
    parsed_items: list[tuple[Any, ParsedElement]] = []
    for order, (item, _) in enumerate(items_with_levels, start=1):
        if is_text_inside_picture(item, picture_items):
            continue

        provenance = _parsed_provenance(item)
        if not provenance:
            # 无法确认页码的元素不伪造为第 1 页内容。
            continue

        docling_label = _item_label(item)
        element_type = _element_type(item, docling_label)
        text = _item_text(item, document, element_type)
        if element_type == "section_header":
            raw_level = getattr(item, "level", 1)
            try:
                header_level = max(1, int(raw_level))
            except (TypeError, ValueError):
                header_level = 1
            for previous_level in list(section_levels):
                if previous_level >= header_level:
                    del section_levels[previous_level]
            section_levels[header_level] = text

        section_path = [section_levels[level] for level in sorted(section_levels)]
        bbox = provenance[0].bbox
        parsed_items.append(
            (
                item,
                ParsedElement(
                    element_id=f"element-{order:06d}",
                    element_type=element_type,
                    docling_type=type(item).__name__,
                    docling_label=docling_label,
                    text=text,
                    page_num=provenance[0].page_num,
                    order=order,
                    bbox=bbox,
                    provenance=provenance,
                    section_path=section_path,
                ),
            )
        )

    elements = _link_elements(parsed_items)
    if figure_dir is not None:
        elements = _extract_figure_images(path, elements, Path(figure_dir))
    return ParsedPdf(page_count=_page_count(document, elements), elements=elements)


def extract_body_text(parsed_pdf: ParsedPdf, *, include_formulas: bool = True) -> str:
    """按 Docling 顺序派生正文，省略图、图注和表格等非正文元素。"""
    included_types = set(_BODY_ELEMENT_TYPES)
    if not include_formulas:
        included_types.remove("formula")
    return "\n\n".join(
        element.text
        for element in sorted(parsed_pdf.elements, key=lambda candidate: candidate.order)
        if element.element_type in included_types and element.text
    )
