"""Metadata filters shared by the dense and lexical retrievers."""

from dataclasses import dataclass
from typing import Mapping, Sequence


@dataclass(frozen=True)
class RetrievalFilters:
    """Optional element, page-range, and section-prefix constraints."""

    element_types: tuple[str, ...] = ()
    page_from: int | None = None
    page_to: int | None = None
    section_path_prefix: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value.strip()
            for value in self.element_types
        ):
            raise ValueError("element_types 不能包含空值")
        if self.page_from is not None and (
            type(self.page_from) is not int or self.page_from < 1
        ):
            raise ValueError("page_from 必须是大于等于 1 的整数")
        if self.page_to is not None and (
            type(self.page_to) is not int or self.page_to < 1
        ):
            raise ValueError("page_to 必须是大于等于 1 的整数")
        if (
            self.page_from is not None
            and self.page_to is not None
            and self.page_from > self.page_to
        ):
            raise ValueError("page_from 不能大于 page_to")
        if any(
            not isinstance(value, str) or not value.strip()
            for value in self.section_path_prefix
        ):
            raise ValueError("section_path_prefix 不能包含空值")


FilterInput = RetrievalFilters | Mapping[str, object] | None


def coerce_filters(filters: FilterInput) -> RetrievalFilters:
    """Normalize public mapping inputs into the shared immutable filter type."""
    if filters is None:
        return RetrievalFilters()
    if isinstance(filters, RetrievalFilters):
        return filters
    if not isinstance(filters, Mapping):
        raise ValueError("filters 必须是对象")

    allowed = {"element_types", "page_from", "page_to", "section_path_prefix"}
    unknown = set(filters) - allowed
    if unknown:
        raise ValueError(f"filters 包含不支持的字段: {', '.join(sorted(unknown))}")

    element_types = filters.get("element_types", ())
    section_prefix = filters.get("section_path_prefix", ())
    if isinstance(element_types, str) or not isinstance(element_types, Sequence):
        raise ValueError("element_types 必须是字符串列表")
    if isinstance(section_prefix, str) or not isinstance(section_prefix, Sequence):
        raise ValueError("section_path_prefix 必须是字符串列表")

    return RetrievalFilters(
        element_types=tuple(element_types),
        page_from=filters.get("page_from"),
        page_to=filters.get("page_to"),
        section_path_prefix=tuple(section_prefix),
    )


def matches_filters(metadata: Mapping[str, object], filters: RetrievalFilters) -> bool:
    """Return whether chunk metadata satisfies every supplied filter group.

    Multiple element types are alternatives. Page ranges use inclusive overlap,
    and section paths match complete, case-insensitive hierarchy components.
    """
    if filters.element_types:
        raw_types = metadata.get("element_types", ())
        chunk_types = (
            {value for value in raw_types if isinstance(value, str)}
            if isinstance(raw_types, Sequence) and not isinstance(raw_types, str)
            else set()
        )
        if not chunk_types.intersection(filters.element_types):
            return False

    if filters.page_from is not None or filters.page_to is not None:
        raw_pages = metadata.get("page_nums", ())
        pages = (
            [page for page in raw_pages if type(page) is int]
            if isinstance(raw_pages, Sequence) and not isinstance(raw_pages, str)
            else []
        )
        if not any(
            (filters.page_from is None or page >= filters.page_from)
            and (filters.page_to is None or page <= filters.page_to)
            for page in pages
        ):
            return False

    if filters.section_path_prefix:
        raw_path = metadata.get("section_path", ())
        if not isinstance(raw_path, Sequence) or isinstance(raw_path, str):
            return False
        path = [value for value in raw_path if isinstance(value, str)]
        prefix = filters.section_path_prefix
        if len(path) < len(prefix) or any(
            path_part.strip().casefold() != prefix_part.strip().casefold()
            for path_part, prefix_part in zip(path, prefix)
        ):
            return False

    return True
