from __future__ import annotations

import re

from app.documents.chunker import Chunk
from app.retrieval.retrieval_filters import RetrievalFilters
from app.storage.milvus_store import MilvusChunkStore


class FakeSchema:
    def __init__(self) -> None:
        self.fields: list[dict[str, object]] = []

    def add_field(self, **kwargs) -> None:
        self.fields.append(kwargs)


class FakeIndexParams:
    def __init__(self) -> None:
        self.indexes: list[dict[str, object]] = []

    def add_index(self, **kwargs) -> None:
        self.indexes.append(kwargs)


class FakeMilvusClient:
    def __init__(self) -> None:
        self.collections: dict[str, dict[str, dict[str, object]]] = {}
        self.schemas: dict[str, FakeSchema] = {}
        self.indexes: list[tuple[str, FakeIndexParams]] = []
        self.search_filter = ""

    def has_collection(self, collection_name: str) -> bool:
        return collection_name in self.collections

    def list_collections(self):
        return list(self.collections)

    def create_schema(self, **_kwargs) -> FakeSchema:
        return FakeSchema()

    def prepare_index_params(self) -> FakeIndexParams:
        return FakeIndexParams()

    def create_collection(self, collection_name, schema, **_kwargs) -> None:
        self.collections[collection_name] = {}
        self.schemas[collection_name] = schema

    def create_index(self, collection_name, index_params, **_kwargs) -> None:
        self.indexes.append((collection_name, index_params))

    def list_indexes(self, collection_name, field_name="", **_kwargs):
        if not field_name:
            return [collection_name] if any(name == collection_name for name, _ in self.indexes) else []
        return [field_name] if any(
            name == collection_name
            and any(index.get("field_name") == field_name for index in params.indexes)
            for name, params in self.indexes
        ) else []

    def load_collection(self, collection_name, **_kwargs) -> None:
        assert collection_name in self.collections

    def insert(self, collection_name, data, **_kwargs) -> None:
        rows = self.collections[collection_name]
        for row in data:
            rows[row["pk"]] = dict(row)

    def flush(self, collection_name, **_kwargs) -> None:
        assert collection_name in self.collections

    @staticmethod
    def _file_id(filter_expr: str) -> str | None:
        match = re.search(r'file_id == "([^"]+)"', filter_expr)
        return match.group(1) if match else None

    def query(self, collection_name, filter="", output_fields=None, ids=None, **_kwargs):
        rows = list(self.collections[collection_name].values())
        file_id = self._file_id(filter)
        if file_id is not None:
            rows = [row for row in rows if row["file_id"] == file_id]
        if ids is not None:
            wanted = set(ids if isinstance(ids, list) else [ids])
            rows = [row for row in rows if row["pk"] in wanted]
        return [
            {key: value for key, value in row.items() if output_fields is None or key in output_fields}
            for row in rows
        ]

    def delete(self, collection_name, filter="", **_kwargs):
        rows = self.collections[collection_name]
        file_id = self._file_id(filter)
        for key in [key for key, row in rows.items() if row["file_id"] == file_id]:
            del rows[key]

    def search(self, collection_name, data, filter="", limit=10, output_fields=None, **_kwargs):
        self.search_filter = filter
        file_id = self._file_id(filter)
        query = data[0]
        rows = [
            row for row in self.collections[collection_name].values()
            if row["file_id"] == file_id
        ]
        rows.sort(
            key=lambda row: -sum(a * b for a, b in zip(query, row["embedding"]))
        )
        return [[
            {
                "id": row["pk"],
                "distance": sum(a * b for a, b in zip(query, row["embedding"])),
                "entity": {
                    key: value for key, value in row.items()
                    if output_fields is None or key in output_fields
                },
            }
            for row in rows[:limit]
        ]]


def sample_chunks(file_id: str = "file-a") -> tuple[list[Chunk], list[Chunk]]:
    parent = Chunk(
        chunk_id="element-000001-parent",
        context="Section: Methods\n\nThe depth model uses an encoder.",
        meta={"element_types": ["paragraph"], "page_nums": [2], "section_path": ["Methods"]},
    )
    child = Chunk(
        chunk_id="element-000001-child-0",
        context="The depth model uses an encoder.",
        meta={"element_types": ["paragraph"], "page_nums": [2], "section_path": ["Methods"]},
        parent_chunk_id=parent.chunk_id,
    )
    return [parent], [child]


def test_milvus_store_persists_and_restores_parent_child_chunks() -> None:
    client = FakeMilvusClient()
    store = MilvusChunkStore(client=client, collection_prefix="learning", dimension=2)
    parents, children = sample_chunks()

    store.replace_file_index(
        "file-a", parents, children, [[1.0, 0.0]], fingerprint="pdf-v1-model-v1"
    )
    restored = store.load_file_index("file-a")

    assert restored is not None
    restored_parents, restored_children, fingerprint = restored
    assert restored_parents == parents
    assert restored_children == children
    assert fingerprint == "pdf-v1-model-v1"
    assert store.parent_collection == "learning_parents_2d"
    assert store.child_collection == "learning_children_2d"
    assert len(client.indexes) == 2


def test_milvus_primary_keys_are_scoped_by_file_id() -> None:
    client = FakeMilvusClient()
    store = MilvusChunkStore(client=client, collection_prefix="learning", dimension=2)
    parents_a, children_a = sample_chunks("file-a")
    parents_b, children_b = sample_chunks("file-b")

    store.replace_file_index("file-a", parents_a, children_a, [[1.0, 0.0]], fingerprint="a")
    store.replace_file_index("file-b", parents_b, children_b, [[0.0, 1.0]], fingerprint="b")

    assert len(client.collections[store.parent_collection]) == 2
    assert len(client.collections[store.child_collection]) == 2
    assert store.load_file_index("file-a")[2] == "a"
    assert store.load_file_index("file-b")[2] == "b"


def test_milvus_child_search_applies_file_and_metadata_filters() -> None:
    client = FakeMilvusClient()
    store = MilvusChunkStore(client=client, collection_prefix="learning", dimension=2)
    parents, children = sample_chunks()
    store.replace_file_index("file-a", parents, children, [[1.0, 0.0]], fingerprint="v1")

    hits = store.search_children(
        "file-a",
        [1.0, 0.0],
        top_k=5,
        filters=RetrievalFilters(
            element_types=("paragraph",),
            page_from=1,
            page_to=3,
            section_path_prefix=("Methods",),
        ),
    )

    assert [hit.chunk.chunk_id for hit in hits] == ["element-000001-child-0"]
    assert 'file_id == "file-a"' in client.search_filter
    assert 'element_type in ["paragraph"]' in client.search_filter
    assert "page_start <= 3" in client.search_filter
    assert 'section_0 == "Methods"' in client.search_filter


def test_milvus_store_fetches_parents_and_deletes_only_one_file() -> None:
    client = FakeMilvusClient()
    store = MilvusChunkStore(client=client, collection_prefix="learning", dimension=2)
    parents_a, children_a = sample_chunks("file-a")
    parents_b, children_b = sample_chunks("file-b")
    store.replace_file_index("file-a", parents_a, children_a, [[1.0, 0.0]], fingerprint="a")
    store.replace_file_index("file-b", parents_b, children_b, [[0.0, 1.0]], fingerprint="b")

    fetched = store.fetch_parents("file-a", ["element-000001-parent"])
    store.delete_file("file-a")

    assert fetched == parents_a
    assert store.load_file_index("file-a") is None
    assert store.load_file_index("file-b")[0] == parents_b


def test_delete_file_cleans_its_old_embedding_dimension_collections() -> None:
    client = FakeMilvusClient()
    parents, children = sample_chunks()
    old_store = MilvusChunkStore(client=client, collection_prefix="learning", dimension=2)
    new_store = MilvusChunkStore(client=client, collection_prefix="learning", dimension=3)
    old_store.replace_file_index("file-a", parents, children, [[1.0, 0.0]], fingerprint="old")
    new_store.replace_file_index("file-a", parents, children, [[1.0, 0.0, 0.0]], fingerprint="new")

    new_store.delete_file("file-a")

    assert client.collections[old_store.parent_collection] == {}
    assert client.collections[old_store.child_collection] == {}
    assert new_store.load_file_index("file-a") is None
