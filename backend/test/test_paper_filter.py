from langchain_core.documents import Document

from rag.cache import RetrievalCache
from rag.retrieval import Retriever


class FakeEmbeddings:
    def embed_query(self, query: str) -> list[float]:
        return [1.0, 0.0]


def test_cache_does_not_cross_paper_scopes():
    cache = RetrievalCache(FakeEmbeddings())
    results = [Document(page_content="paper one")]

    cache.put("What is PredRNet?", results, scope="paper:one")

    assert cache.get("What is PredRNet?", scope="paper:one") == results
    assert cache.get("What is PredRNet?", scope="paper:two") is None


def test_paper_filter_is_combined_with_existing_filters():
    retriever = Retriever.__new__(Retriever)

    expr = retriever._build_expr(
        node_type_filter=["table"],
        section_type_filter=["experiment"],
        paper_id='paper "one"',
    )

    assert expr == 'paper_id == "paper \\"one\\"" && (node_type == "table") && (section_type == "experiment")'
