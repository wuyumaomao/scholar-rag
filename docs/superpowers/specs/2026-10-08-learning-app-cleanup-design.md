# Learning App Cleanup and Package Design

## Goal

Make the learning backend easier to navigate by grouping modules by responsibility and removing only disposable test/runtime artifacts. Preserve the learning project's behavior, useful local data, benchmark outputs, and the separation between its core algorithms.

## Current findings

- `learning-implementation/backend/app` contains 19 Python modules. Source search found them referenced by application code, benchmark/export scripts, or tests; no clearly unused application module was identified.
- The backend also contains generated `__pycache__`, `.pytest_cache`, dated `test-tmp-*` directories, and `tmp/pytest-*` folders.
- `uploads/` contains user PDF files. `data/` contains benchmark caches and extracted figure crops. `docling-inspection/` contains diagnostic scripts and reports. These are local user data or useful learning artifacts and are explicitly out of cleanup scope.
- The root `learning-implementation` folder contains benchmark JSON reports and learning notes; these remain in place.

## Package layout

Keep `app/main.py` and `app/config.py` at the application root. Group implementation modules as follows:

```text
app/
  main.py
  config.py
  routers/
  documents/
    pdf_parser.py
    chunker.py
  retrieval/
    embedding.py
    bm25_retriever.py
    retriever.py
    retrieval_filters.py
    rrf.py
    reranker.py
    hyde.py
    related_context.py
    retrieval_service.py
    vlm.py
  evaluation/
    metrics.py
    benchmark_cache.py
  storage/
    database.py
    store.py
```

Keep each retrieval technique in its own module so learners can inspect and test Dense, BM25, RRF, reranking, filtering, HyDE, and figure-context behavior independently. `evaluation.py` becomes `evaluation/metrics.py` to make room for the benchmark cache without creating an ambiguous package/module name.

## Import and behavior compatibility

- Update application, scripts, and tests to import from the new package paths.
- Preserve public classes/functions and runtime behavior; do not change request/response schemas, retrieval parameters, cache formats, or benchmark metrics.
- Keep router URLs and lifecycle behavior unchanged. Avoid introducing compatibility re-export modules; update all in-repository callers to the new paths.
- Preserve file deletion's retrieval-index invalidation behavior. Only adjust the import path needed by the package move; do not add a new runtime abstraction in this cleanup.

## Cleanup scope

Remove only generated Python bytecode/cache directories and the identified stale pytest work directories: `backend/__pycache__`, nested `__pycache__`, `.pytest_cache`, `backend/test-tmp-*`, and `backend/tmp/pytest-*`. Add appropriate ignore rules so these do not return as visible repository clutter.

Preserve `.venv`, all files under `uploads/`, `data/`, and `docling-inspection/`, all benchmark JSON results, and all learning documents. Do not delete or consolidate application source modules unless repository-wide references prove them unused.

## Validation

- Run the complete learning-backend test suite.
- Compile `app` and `scripts`.
- Run `git diff --check`.
- Search for old `app.<module>` imports and stale module paths; inspect all remaining results.
- Confirm the exact cleanup targets are absent and excluded user data is still present.

## Out of scope

No change to retrieval algorithms, API behavior, environment settings, benchmark data, PDF processing, model configuration, persistence architecture, or frontend. No deletion of uploaded/source PDFs, parser reports, figure crops, or benchmark caches.
