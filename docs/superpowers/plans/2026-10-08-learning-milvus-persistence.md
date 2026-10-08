# Learning Milvus Persistence Implementation Plan

> **For agentic workers:** execute inline with test-first checkpoints; retain existing uncommitted generation and documentation changes.

**Goal:** Persist learning-project parent and child chunks in Milvus and use them for upload-time indexing and retrieval across backend restarts.

**Architecture:** Add a small Milvus storage adapter with separate dimension-scoped parent and child collections. Each record is scoped by `file_id`, stores the chunk context/metadata and indexing fingerprint, and child records also store vectors and parent IDs. RetrievalService keeps its current in-memory path when Milvus is disabled; when enabled, it restores parent/child text from Milvus, rebuilds BM25, searches child vectors in Milvus, and preserves existing RRF/reranking/related-context behavior. Upload indexes after saving the PDF and PostgreSQL metadata; delete removes Milvus records before deleting metadata.

**Tech Stack:** FastAPI, PyMilvus `MilvusClient`, existing SentenceTransformers embeddings, PostgreSQL metadata, Docker Compose.

**Spec:** Prior user-approved parent/child Milvus design in the conversation; preserve existing `/api/retrieve` response and ranking behavior.

## Global Constraints

- Do not modify the original project's Compose, backend, or Milvus data.
- Keep the learning Milvus host port distinct from the original project's port: `19531:19530`.
- Do not remove or recreate existing Docker volumes.
- Keep current uncommitted answer-generation changes intact.
- Existing BM25, RRF, reranking, metadata filtering, related figure expansion, and benchmark behavior remain in the retrieval pipeline.

---

### Task 1: Settings and Milvus Compose service

**Files:** `learning-implementation/backend/app/config.py`, `backend/.env.example`, `learning-implementation/docker-compose.yml`, `backend/requirements.txt`, config tests.

- [x] Add opt-in `MILVUS_ENABLED`, URI default `http://localhost:19531`, and collection prefix setting.
- [x] Add the standalone Milvus 2.5 service using persistent `learning_milvus_data`, internal `19530`, host `19531`, health check on `9091`, without touching PostgreSQL volume.
- [x] Pin a compatible PyMilvus 2.5 dependency.
- [x] Add configuration assertions and run config tests.

### Task 2: Milvus parent/child storage adapter

**Files:** create `learning-implementation/backend/app/storage/milvus_store.py`; create `backend/tests/test_milvus_store.py`.

- [x] Test collection schema, namespaced IDs, indexing fingerprint, search filtering, parent fetch, file load, and file deletion using an injected fake MilvusClient.
- [x] Implement idempotent collections and vector indexes; store parent and child entities separately; dimension-scope collection names.
- [x] Keep all IDs scoped by file ID so identical Docling chunk IDs across PDFs cannot collide.
- [x] Run the new storage tests before integration.

### Task 3: Persist and restore retrieval indexes

**Files:** `backend/app/retrieval/retrieval_service.py`, `backend/tests/test_retrieval_service.py`.

- [x] Test first indexing persists both chunk layers; repeated calls restore without parsing/embedding; stale fingerprint reindexes; Dense queries use Milvus while BM25/RRF/reranker and related figure expansion remain unchanged.
- [x] Add `index_file(...)` and `delete_file(...)` service methods.
- [x] On restore, reconstruct `Chunk` objects from persisted records and build BM25 locally; on query, dense-search children in Milvus and fetch unique parent records.
- [x] Preserve the in-memory implementation when Milvus is disabled or a test injects no store.
- [x] Run retrieval-service tests and relevant existing tests.

### Task 4: Upload/delete lifecycle

**Files:** `backend/app/routers/files.py`, `backend/app/routers/retrieval.py`, `backend/tests/test_files.py`.

- [x] Test upload indexes after file and metadata persistence; index failure rolls back file and metadata; delete clears vector records before metadata.
- [x] Expose shared index/delete hooks from retrieval router and invoke them from file lifecycle using worker threads.
- [x] Keep error responses explicit and retain existing API response shape.
- [x] Run file and retrieval API tests.

### Task 5: Documentation and verification

**Files:** `learning-implementation/README.md`, `learning-implementation/rag学习文档.md`, `.agent-handoff/*`.

- [x] Document startup, host-side local API URI, `.env` enablement, two collection roles, restart persistence, and non-destructive stop commands.
- [x] Run full learning backend tests, compile checks, Compose config validation, diff check, and a real Milvus smoke test if Docker is available.
- [x] Update handoff snapshot, decisions, work log, validation, backlog, and risks.
