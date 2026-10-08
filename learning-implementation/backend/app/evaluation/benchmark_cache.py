"""Persistent cache for parsed and embedded benchmark PDF indexes."""

from __future__ import annotations

from dataclasses import dataclass
import gzip
import hashlib
from importlib.metadata import PackageNotFoundError, version
import inspect
import json
import logging
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Protocol

from app.documents.chunker import ChunkingResult, create_chunks
from app.documents.pdf_parser import ParsedElement, ParsedPdf, ParsedProvenance, parse_pdf


logger = logging.getLogger(__name__)
DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "benchmark-cache"
CACHE_SCHEMA_VERSION = 1


class _Embedder(Protocol):
    model_name: str

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class CachedBenchmarkIndex:
    chunking: ChunkingResult
    vectors: list[list[float]]
    cache_hit: bool


def load_or_create_index(
    pdf_path: Path,
    *,
    figure_dir: Path,
    embedder: _Embedder,
    parser: Callable[..., ParsedPdf] = parse_pdf,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    use_cache: bool = True,
    chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> CachedBenchmarkIndex:
    """Load a compatible cached index, or parse, chunk, embed, and save it."""
    fingerprint = _cache_fingerprint(
        pdf_path,
        figure_dir=figure_dir,
        embedder=embedder,
        parser=parser,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    cache_path = _cache_path(pdf_path, cache_dir)

    if use_cache and cache_path.is_file():
        try:
            parsed_pdf, vectors = _read_cache(cache_path, fingerprint)
            chunking = create_chunks(
                parsed_pdf,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            _validate_vectors(vectors, len(chunking.children))
            return CachedBenchmarkIndex(chunking, vectors, cache_hit=True)
        except (OSError, EOFError, ValueError, TypeError, KeyError) as exc:
            logger.warning("Ignoring invalid benchmark cache %s: %s", cache_path, exc)

    parsed_pdf = parser(pdf_path, figure_dir=figure_dir)
    chunking = create_chunks(
        parsed_pdf,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    if not chunking.children:
        raise ValueError(f"没有可检索的 child chunk: {pdf_path}")
    vectors = embedder.embed_texts([child.context for child in chunking.children])
    _validate_vectors(vectors, len(chunking.children))

    if use_cache:
        try:
            _write_cache(cache_path, fingerprint, parsed_pdf, vectors)
        except OSError as exc:
            logger.warning("Could not write benchmark cache %s: %s", cache_path, exc)
    return CachedBenchmarkIndex(chunking, vectors, cache_hit=False)


def _cache_path(pdf_path: Path, cache_dir: Path) -> Path:
    """Use stable source-path identity so changed inputs replace old cache data."""
    identity = hashlib.sha256(
        str(pdf_path.resolve()).casefold().encode("utf-8")
    ).hexdigest()[:16]
    return cache_dir / f"{pdf_path.stem[:80]}-{identity}.json.gz"


def _cache_fingerprint(
    pdf_path: Path,
    *,
    figure_dir: Path,
    embedder: _Embedder,
    parser: Callable[..., ParsedPdf],
    chunk_size: int,
    chunk_overlap: int,
) -> dict[str, object]:
    model_name = getattr(embedder, "model_name", None)
    if not isinstance(model_name, str) or not model_name.strip():
        model_name = f"{type(embedder).__module__}.{type(embedder).__qualname__}"
    return {
        "schema_version": CACHE_SCHEMA_VERSION,
        "pdf_sha256": _sha256_file(pdf_path),
        "figure_dir": str(figure_dir.resolve()),
        "embedding_model": model_name,
        "parser_source_sha256": _source_sha256(parser),
        "chunker_source_sha256": _source_sha256(create_chunks),
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "dependency_versions": {
            name: _package_version(name)
            for name in (
                "docling",
                "docling-core",
                "langchain-text-splitters",
                "sentence-transformers",
            )
        },
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_sha256(function: Callable[..., Any]) -> str:
    source_path = inspect.getsourcefile(function)
    if source_path is None:
        return "unknown"
    return _sha256_file(Path(source_path))


def _package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "not-installed"


def _read_cache(
    cache_path: Path,
    expected_fingerprint: dict[str, object],
) -> tuple[ParsedPdf, list[list[float]]]:
    with gzip.open(cache_path, "rt", encoding="utf-8") as compressed:
        payload = json.load(compressed)
    if not isinstance(payload, dict):
        raise ValueError("缓存根节点必须是对象")
    if payload.get("fingerprint") != expected_fingerprint:
        raise ValueError("缓存指纹已过期")
    parsed_pdf = _parsed_pdf_from_dict(payload["parsed_pdf"])
    vectors = payload["vectors"]
    if not isinstance(vectors, list):
        raise ValueError("缓存 vectors 必须是数组")
    normalized_vectors = [
        [float(value) for value in vector]
        if isinstance(vector, list)
        else []
        for vector in vectors
    ]
    return parsed_pdf, normalized_vectors


def _parsed_pdf_from_dict(value: object) -> ParsedPdf:
    if not isinstance(value, dict):
        raise ValueError("缓存 parsed_pdf 必须是对象")
    elements = value.get("elements")
    if not isinstance(elements, list):
        raise ValueError("缓存 elements 必须是数组")
    parsed_elements = []
    for raw in elements:
        if not isinstance(raw, dict):
            raise ValueError("缓存 element 必须是对象")
        provenance = raw.get("provenance", [])
        if not isinstance(provenance, list):
            raise ValueError("缓存 provenance 必须是数组")
        parsed_provenance = [
            ParsedProvenance(
                page_num=int(item["page_num"]),
                bbox=_bbox(item.get("bbox")),
            )
            for item in provenance
        ]
        parsed_elements.append(
            ParsedElement(
                element_id=str(raw["element_id"]),
                element_type=str(raw["element_type"]),
                docling_type=str(raw["docling_type"]),
                docling_label=(
                    str(raw["docling_label"])
                    if raw.get("docling_label") is not None
                    else None
                ),
                text=str(raw["text"]),
                page_num=int(raw["page_num"]),
                order=int(raw["order"]),
                bbox=_bbox(raw.get("bbox")),
                image_path=(
                    str(raw["image_path"])
                    if raw.get("image_path") is not None
                    else None
                ),
                provenance=parsed_provenance,
                section_path=[str(item) for item in raw.get("section_path", [])],
                related_ids=[str(item) for item in raw.get("related_ids", [])],
            )
        )
    return ParsedPdf(page_count=int(value["page_count"]), elements=parsed_elements)


def _bbox(value: object) -> tuple[float, float, float, float] | None:
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError("缓存 bbox 必须包含四个坐标")
    return tuple(float(coordinate) for coordinate in value)


def _validate_vectors(vectors: list[list[float]], expected_count: int) -> None:
    if len(vectors) != expected_count:
        raise ValueError("缓存向量数量与 child chunk 数量不匹配")
    dimensions = {len(vector) for vector in vectors}
    if not vectors or dimensions == {0} or len(dimensions) != 1:
        raise ValueError("缓存向量维度无效")
    if any(not math.isfinite(value) for vector in vectors for value in vector):
        raise ValueError("缓存向量包含非有限数值")


def _write_cache(
    cache_path: Path,
    fingerprint: dict[str, object],
    parsed_pdf: ParsedPdf,
    vectors: list[list[float]],
) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fingerprint": fingerprint,
        "parsed_pdf": parsed_pdf.to_dict(),
        "vectors": vectors,
    }
    serialized = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f"{cache_path.stem}.", suffix=".tmp", dir=cache_path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as raw_file:
            with gzip.GzipFile(fileobj=raw_file, mode="wb", mtime=0) as compressed:
                compressed.write(serialized)
            raw_file.flush()
            os.fsync(raw_file.fileno())
        os.replace(temporary_path, cache_path)
    finally:
        temporary_path.unlink(missing_ok=True)
