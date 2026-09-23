"""Embedding-based retrieval cache.

Instead of exact key matching, caches query embeddings and returns results
for semantically similar queries above a cosine similarity threshold.
"""

import logging
import threading
from collections import OrderedDict
from typing import Optional
import numpy as np
from langchain_core.documents import Document

logger = logging.getLogger(__name__)


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom > 0 else 0.0


class RetrievalCache:
    """LRU cache keyed by query embedding similarity.

    On get(): computes the query embedding, finds the most similar cached
    embedding; if cosine similarity >= threshold, returns cached results.

    On put(): stores the embedding alongside results; evicts LRU when full.
    """

    def __init__(
        self,
        embeddings,
        max_size: int = 1000,
        similarity_threshold: float = 0.95,
    ):
        """
        Args:
            embeddings: HuggingFaceEmbeddings instance (shared singleton).
            max_size: Max number of cached queries.
            similarity_threshold: Cosine similarity cutoff for a cache hit.
        """
        self.embeddings = embeddings
        self.max_size = max_size
        self.threshold = similarity_threshold
        self._lock = threading.RLock()
        # OrderedDict: (query, scope) -> (embedding, results, scope)
        # A similar query must not cross a paper or retrieval-filter boundary.
        self._store: OrderedDict[
            tuple[str, str], tuple[np.ndarray, list[Document], str]
        ] = OrderedDict()

    def _embed(self, query: str) -> np.ndarray:
        vec = self.embeddings.embed_query(query)
        return np.array(vec, dtype=np.float32)

    def _find_best(
        self, vec: np.ndarray, scope: str
    ) -> Optional[tuple[tuple[str, str], float]]:
        """Return (key, similarity) of the best matching cache entry, or None."""
        best_key, best_sim = None, -1.0
        for key, (cached_vec, _, cached_scope) in self._store.items():
            if cached_scope != scope:
                continue
            sim = _cosine(vec, cached_vec)
            if sim > best_sim:
                best_sim, best_key = sim, key
        if best_key is not None and best_sim >= self.threshold:
            return best_key, best_sim
        return None

    def get(self, query: str, scope: str = "") -> Optional[list[Document]]:
        """Return cached results if a similar query exists, else None."""
        with self._lock:
            if not self._store:
                return None
            vec = self._embed(query)
            match = self._find_best(vec, scope)
            if match:
                key, sim = match
                self._store.move_to_end(key)
                logger.debug(f"Cache hit (sim={sim:.3f}): {query[:60]}")
                return self._store[key][1]
            return None

    def put(self, query: str, results: list[Document], scope: str = "") -> None:
        """Cache results for query; evict LRU entry if at capacity."""
        with self._lock:
            vec = self._embed(query)
            key = (query, scope)
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (vec, results, scope)
            if len(self._store) > self.max_size:
                self._store.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
