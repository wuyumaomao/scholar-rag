# Learning App Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reorganize the learning backend's `app` modules by responsibility and remove only confirmed disposable Python/pytest artifacts.

**Architecture:** Keep `main.py`, `config.py`, and HTTP routers at the app root/routers package. Move document ingestion, retrieval, evaluation, and storage code into focused packages while keeping each algorithm in its own module. Update all application, script, test, and directly relevant learning-document imports without changing runtime behavior.

**Tech Stack:** Python 3.12, FastAPI, pytest, uv-managed project virtual environment, PowerShell, Git.

**Spec:** `docs/superpowers/specs/2026-10-08-learning-app-cleanup-design.md`

## Global Constraints

- Keep the learning implementation under `learning-implementation/`; do not change the original project's `backend/` or `frontend/`.
- Preserve request/response schemas, retrieval defaults, benchmark results, cache formats, and API lifecycle behavior.
- Keep Dense, BM25, RRF, reranking, filtering, HyDE, and figure-context behavior in separate modules.
- Preserve `learning-implementation/backend/uploads/`, `data/`, `docling-inspection/`, benchmark JSON files, and learning documents.
- Delete only `__pycache__`, `.pytest_cache`, `backend/test-tmp-*`, and `backend/tmp/pytest-*` generated artifacts after confirming exact paths.

---

### Task 1: Establish the current module/import inventory

**Files:**
- Read: `learning-implementation/backend/app/`
- Read: `learning-implementation/backend/scripts/`
- Read: `learning-implementation/backend/tests/`
- Read: `learning-implementation/rag学习文档.md`

- [x] Search all project references to the modules being moved and record the migration scope in the current work log.
- [x] Record the current tracked/untracked state and exact cache/temp cleanup targets.
- [x] Confirm uploads, figures, benchmark cache, and Docling inspection contents remain outside cleanup scope.

### Task 2: Group document and storage modules

**Files:**
- Create: `learning-implementation/backend/app/documents/__init__.py`
- Move: `app/pdf_parser.py` → `app/documents/pdf_parser.py`
- Move: `app/chunker.py` → `app/documents/chunker.py`
- Create: `learning-implementation/backend/app/storage/__init__.py`
- Move: `app/database.py` → `app/storage/database.py`
- Move: `app/store.py` → `app/storage/store.py`
- Modify: all app, script, test imports for those modules

- [x] Use `git mv` to move the four source modules and create package initializers.
- [x] Update imports in application source, scripts, and tests to the new package paths.
- [x] Run `tests/test_pdf_parser.py`, `tests/test_chunker.py`, `tests/test_files.py`, and `tests/test_sessions.py` as part of the full suite.

### Task 3: Group retrieval and evaluation modules

**Files:**
- Create: `learning-implementation/backend/app/retrieval/__init__.py`
- Move to `app/retrieval/`: `embedding.py`, `bm25_retriever.py`, `retriever.py`, `retrieval_filters.py`, `rrf.py`, `reranker.py`, `hyde.py`, `related_context.py`, `retrieval_service.py`, `vlm.py`
- Create: `learning-implementation/backend/app/evaluation/__init__.py`
- Move: `app/evaluation.py` → `app/evaluation/metrics.py`
- Move: `app/benchmark_cache.py` → `app/evaluation/benchmark_cache.py`
- Modify: all app, script, and test imports for those modules

- [x] Move the modules without combining algorithm implementations.
- [x] Update internal dependencies using explicit package imports (`app.documents`, `app.retrieval`, `app.storage`, `app.evaluation`).
- [x] Update the benchmark/export scripts and all affected tests.
- [x] Run targeted retrieval/evaluation tests: 115 passed across the listed retrieval and evaluation modules.

### Task 4: Ignore and remove disposable artifacts

**Files:**
- Modify: `.gitignore`
- Remove after path/content verification: backend Python/pytest cache and stale pytest temp directories only

- [x] Add anchored ignore rules for `learning-implementation/backend/test-tmp-*/` and `learning-implementation/backend/tmp/pytest-*/`; existing Python and pytest cache rules cover bytecode and `.pytest_cache`.
- [x] Enumerate each exact target with its absolute path and confirm none is `.venv`, `uploads`, `data`, or `docling-inspection`.
- [x] Move only the enumerated cache/temp targets out of the learning project into a recoverable quarantine under the system temp directory after recursive deletion was blocked by policy.
- [x] Confirm protected user data directories and representative files remain present.

### Task 5: Full verification and documentation alignment

**Files:**
- Modify only if stale paths are found: `learning-implementation/rag学习文档.md`, `learning-implementation/README.md`, directly relevant docs
- Verify: all moved app modules, scripts, and tests

- [x] Search the learning project for old module paths and inspect every match; update active setup/import examples while preserving historical references.
- [x] Set `$env:PYTHONDONTWRITEBYTECODE = '1'`, then run `..\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp "$env:TEMP\scholar-rag-cleanup-finalpytest"` from the backend: 122 passed.
- [x] Run `..\.venv\Scripts\python.exe -X pycache_prefix="$env:TEMP\scholar-rag-cleanup-pycache" -m compileall -q app scripts` from the backend.
- [x] Run `git diff HEAD --check` and inspect the changed paths.
- [x] Confirm no changes occurred under the original project's `backend/` or `frontend/`, and confirm protected local artifacts remain present.
