"""Persistent parent/child chunk storage and dense search backed by Milvus."""

from __future__ import annotations

import json
import re
from typing import Any, Sequence

from pymilvus import DataType, MilvusClient

from app.documents.chunker import Chunk
from app.retrieval.retrieval_filters import (
    FilterInput,
    coerce_filters,
    matches_filters,
)
from app.retrieval.retriever import RetrievalHit


_SECTION_LEVELS = 12
_ROW_FIELDS = [
    "pk",
    "file_id",
    "chunk_id",
    "parent_chunk_id",
    "context",
    "metadata",
    "index_fingerprint",
    "parent_count",
    "child_count",
]
_FILTER_FIELDS = ["element_type", "page_start", "page_end"] + [
    f"section_{level}" for level in range(_SECTION_LEVELS)
]


def _quoted(value: str) -> str:
    """Encode a string literal accepted by Milvus filter expressions."""
    return json.dumps(value, ensure_ascii=False)


def _file_filter(file_id: str) -> str:
    return f"file_id == {_quoted(file_id)}"


def _entity_id(file_id: str, chunk_id: str) -> str:
    return f"{file_id}:{chunk_id}"


def _chunk_from_row(row: dict[str, Any]) -> Chunk:
    metadata = row.get("metadata") or {}
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    if not isinstance(metadata, dict):
        raise ValueError("Milvus chunk metadata 格式无效")
    parent_id = row.get("parent_chunk_id") or None
    return Chunk(
        chunk_id=str(row["chunk_id"]),
        context=str(row["context"]),
        meta=metadata,
        parent_chunk_id=str(parent_id) if parent_id else None,
    )


class MilvusChunkStore:
    """Store complete parent contexts and searchable child vectors separately."""

    def __init__(
        self,
        *,
        uri: str = "http://localhost:19531",
        collection_prefix: str = "learning_rag",
        dimension: int,
        client: Any | None = None,
    ) -> None:
        if dimension <= 0:
            raise ValueError("dimension 必须大于 0")
        if not collection_prefix.strip():
            raise ValueError("collection_prefix 不能为空")
        self.dimension = dimension
        self.collection_prefix = collection_prefix
        self.parent_collection = f"{collection_prefix}_parents_{dimension}d"
        self.child_collection = f"{collection_prefix}_children_{dimension}d"
        self._client = client or MilvusClient(uri=uri)
        self._ready = False

    def _ensure_collections(self) -> None:
        if self._ready:
            return
        for collection_name, with_vector in (
            (self.parent_collection, False),
            (self.child_collection, True),
        ):
            created = not self._client.has_collection(collection_name)
            if created:
                schema = self._client.create_schema(
                    auto_id=False,
                    enable_dynamic_field=False,
                )
                schema.add_field(
                    field_name="pk",
                    datatype=DataType.VARCHAR,
                    is_primary=True,
                    max_length=512,
                )
                schema.add_field(field_name="file_id", datatype=DataType.VARCHAR, max_length=128)
                schema.add_field(field_name="chunk_id", datatype=DataType.VARCHAR, max_length=256)
                schema.add_field(
                    field_name="parent_chunk_id", datatype=DataType.VARCHAR, max_length=256
                )
                schema.add_field(field_name="context", datatype=DataType.VARCHAR, max_length=65535)
                schema.add_field(field_name="metadata", datatype=DataType.JSON)
                schema.add_field(
                    field_name="index_fingerprint", datatype=DataType.VARCHAR, max_length=128
                )
                schema.add_field(field_name="parent_count", datatype=DataType.INT64)
                schema.add_field(field_name="child_count", datatype=DataType.INT64)
                schema.add_field(field_name="element_type", datatype=DataType.VARCHAR, max_length=64)
                schema.add_field(field_name="page_start", datatype=DataType.INT64)
                schema.add_field(field_name="page_end", datatype=DataType.INT64)
                for level in range(_SECTION_LEVELS):
                    schema.add_field(
                        field_name=f"section_{level}",
                        datatype=DataType.VARCHAR,
                        max_length=512,
                    )
                if with_vector:
                    schema.add_field(
                        field_name="embedding",
                        datatype=DataType.FLOAT_VECTOR,
                        dim=self.dimension,
                    )
                else:
                    # Milvus requires every collection to define a vector field.
                    # Parent contexts are never searched by vector, so this field
                    # is deliberately unindexed and only stores zero placeholders.
                    schema.add_field(
                        field_name="storage_anchor",
                        datatype=DataType.FLOAT_VECTOR,
                        dim=self.dimension,
                    )
                self._client.create_collection(collection_name, schema=schema)
            vector_field = "embedding" if with_vector else "storage_anchor"
            if not self._client.list_indexes(collection_name, field_name=vector_field):
                index_params = self._client.prepare_index_params()
                index_params.add_index(
                    field_name=vector_field,
                    index_type="AUTOINDEX",
                    metric_type="COSINE",
                )
                self._client.create_index(collection_name, index_params=index_params)
            self._client.load_collection(collection_name)
        self._ready = True

    def _row(
        self,
        file_id: str,
        chunk: Chunk,
        fingerprint: str,
        parent_count: int,
        child_count: int,
        vector: Sequence[float] | None = None,
    ) -> dict[str, Any]:
        row: dict[str, Any] = {
            "pk": _entity_id(file_id, chunk.chunk_id),
            "file_id": file_id,
            "chunk_id": chunk.chunk_id,
            "parent_chunk_id": chunk.parent_chunk_id or "",
            "context": chunk.context,
            "metadata": chunk.meta,
            "index_fingerprint": fingerprint,
            "parent_count": parent_count,
            "child_count": child_count,
            "element_type": next(iter(chunk.meta.get("element_types", [])), "unknown"),
            "page_start": min(chunk.meta.get("page_nums", [1]) or [1]),
            "page_end": max(chunk.meta.get("page_nums", [1]) or [1]),
        }
        section_path = chunk.meta.get("section_path", [])
        for level in range(_SECTION_LEVELS):
            row[f"section_{level}"] = (
                section_path[level] if level < len(section_path) else ""
            )
        if vector is not None:
            if len(vector) != self.dimension:
                raise ValueError("chunk embedding 维度与 Milvus collection 不匹配")
            row["embedding"] = [float(value) for value in vector]
        return row

    def replace_file_index(
        self,
        file_id: str,
        parents: Sequence[Chunk],
        children: Sequence[Chunk],
        child_vectors: Sequence[Sequence[float]],
        *,
        fingerprint: str,
    ) -> None:
        """Replace both layers for a file, cleaning partial writes on failure."""
        if len(children) != len(child_vectors):
            raise ValueError("children 和 child_vectors 的数量必须一致")
        if not file_id.strip() or not fingerprint:
            raise ValueError("file_id 和 fingerprint 不能为空")
        parent_ids = {parent.chunk_id for parent in parents}
        if any(
            child.parent_chunk_id is not None and child.parent_chunk_id not in parent_ids
            for child in children
        ):
            raise ValueError("child 引用的 parent_chunk_id 不存在")
        self._ensure_collections()
        self.delete_file(file_id)
        try:
            if parents:
                parent_rows = [
                    self._row(
                        file_id, chunk, fingerprint, len(parents), len(children)
                    )
                    for chunk in parents
                ]
                for row in parent_rows:
                    row["storage_anchor"] = [0.0] * self.dimension
                self._client.insert(
                    self.parent_collection,
                    parent_rows,
                )
            if children:
                self._client.insert(
                    self.child_collection,
                    [
                        self._row(
                            file_id,
                            chunk,
                            fingerprint,
                            len(parents),
                            len(children),
                            vector,
                        )
                        for chunk, vector in zip(children, child_vectors)
                    ],
                )
            self._client.flush(self.parent_collection)
            self._client.flush(self.child_collection)
        except Exception:
            try:
                self.delete_file(file_id)
            except Exception:
                pass
            raise

    def load_file_index(
        self, file_id: str
    ) -> tuple[list[Chunk], list[Chunk], str] | None:
        """Restore both text layers if they have one consistent fingerprint."""
        self._ensure_collections()
        parents = self._client.query(
            self.parent_collection,
            filter=_file_filter(file_id),
            output_fields=_ROW_FIELDS,
        )
        children = self._client.query(
            self.child_collection,
            filter=_file_filter(file_id),
            output_fields=_ROW_FIELDS,
        )
        if not parents or not children:
            return None
        fingerprints = {
            row.get("index_fingerprint") for row in [*parents, *children]
        }
        expected_counts = {
            (row.get("parent_count"), row.get("child_count"))
            for row in [*parents, *children]
        }
        if len(fingerprints) != 1 or len(expected_counts) != 1:
            return [], [], ""
        expected_parent_count, expected_child_count = next(iter(expected_counts))
        if expected_parent_count != len(parents) or expected_child_count != len(children):
            return [], [], ""
        return (
            sorted(
                (_chunk_from_row(row) for row in parents),
                key=lambda chunk: (chunk.meta.get("orders", [0])[0], 0),
            ),
            sorted(
                (_chunk_from_row(row) for row in children),
                key=lambda chunk: (
                    chunk.meta.get("orders", [0])[0],
                    chunk.meta.get("child_index", 0),
                ),
            ),
            str(next(iter(fingerprints))),
        )

    def _filter_expression(self, file_id: str, filters: FilterInput) -> str:
        resolved = coerce_filters(filters)
        terms = [_file_filter(file_id)]
        if resolved.element_types:
            types = ", ".join(_quoted(value) for value in resolved.element_types)
            terms.append(f"element_type in [{types}]")
        if resolved.page_to is not None:
            terms.append(f"page_start <= {resolved.page_to}")
        if resolved.page_from is not None:
            terms.append(f"page_end >= {resolved.page_from}")
        terms.extend(
            f"section_{level} == {_quoted(value)}"
            for level, value in enumerate(resolved.section_path_prefix)
        )
        return " and ".join(terms)

    def search_children(
        self,
        file_id: str,
        query_vector: Sequence[float],
        *,
        top_k: int,
        min_score: float = -1.0,
        filters: FilterInput = None,
    ) -> list[RetrievalHit]:
        """Search child vectors and return matching child chunks with cosine scores."""
        if top_k <= 0:
            raise ValueError("top_k 必须大于 0")
        if len(query_vector) != self.dimension:
            raise ValueError("查询向量维度与 Milvus collection 不匹配")
        self._ensure_collections()
        results = self._client.search(
            self.child_collection,
            data=[[float(value) for value in query_vector]],
            anns_field="embedding",
            filter=self._filter_expression(file_id, filters),
            limit=top_k,
            output_fields=_ROW_FIELDS,
            search_params={"metric_type": "COSINE", "params": {}},
        )
        resolved_filters = coerce_filters(filters)
        hits = []
        for result in results[0] if results else []:
            score = float(result.get("distance", result.get("score", 0.0)))
            row = result.get("entity", result)
            chunk = _chunk_from_row(row)
            if score >= min_score and matches_filters(chunk.meta, resolved_filters):
                hits.append(RetrievalHit(chunk=chunk, score=score))
        return hits

    def fetch_parents(self, file_id: str, parent_chunk_ids: Sequence[str]) -> list[Chunk]:
        """Fetch exact parent contexts without mixing same IDs from other PDFs."""
        if not parent_chunk_ids:
            return []
        self._ensure_collections()
        rows = self._client.query(
            self.parent_collection,
            ids=[_entity_id(file_id, chunk_id) for chunk_id in parent_chunk_ids],
            output_fields=_ROW_FIELDS,
        )
        chunks_by_id = {str(row["chunk_id"]): _chunk_from_row(row) for row in rows}
        return [chunks_by_id[chunk_id] for chunk_id in parent_chunk_ids if chunk_id in chunks_by_id]

    def delete_file(self, file_id: str) -> None:
        """Remove both collections' records for a single uploaded PDF."""
        self._ensure_collections()
        expression = _file_filter(file_id)
        parent_pattern = re.compile(
            rf"^{re.escape(self.collection_prefix)}_parents_\d+d$"
        )
        child_pattern = re.compile(
            rf"^{re.escape(self.collection_prefix)}_children_\d+d$"
        )
        for collection_name in self._client.list_collections():
            if parent_pattern.fullmatch(collection_name) or child_pattern.fullmatch(
                collection_name
            ):
                self._client.delete(collection_name, filter=expression)
                self._client.flush(collection_name)
